"""
Clase `Justificar`
==================

Enriquece un `df_marcas` (filas ya extraídas de PDFs) con información de:
  - DuckDB / MotherDuck (para descartar filas ya presentes en `justificacion`)
  - Google Drive (`gdrive_utils`) para datos de personal
  - MongoDB (colección `ot_v30`) para identificar OTs en las que participa el
    trabajador (como responsable o colaborador).
  - Delta Lake (backend Ibis, R2/Cloudflare) para extraer los textos de
    `se_labora` y `lunch` (columna `Cuenta` == "se_labora" / "ALIMENTACION").

Diseño y esquema de tablas: ver `@notas_arquitectura/`
(1_Database_desing.md, 2_Clase_Justificaciones.md, 3_MongoDB schema.md,
4_Delta Lake schema.md).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import duckdb
import pandas as pd

from gdrive_utils import build_filename, get_all_data


# ==========================================
# Excepciones específicas
# ==========================================

class JustificarError(Exception):
    """Base para errores de la clase `Justificar`."""


class NoNewRowsError(JustificarError):
    """Todas las filas de `df_marcas` ya existen en la tabla `justificacion`."""


class MongoConnectionError(JustificarError):
    """Fallo al consultar MongoDB."""


class DeltaConnectionError(JustificarError):
    """Fallo al consultar Delta Lake."""


# ==========================================
# Clase principal
# ==========================================

class Justificar:
    """
    Construye `df_justif` a partir de `df_marcas` cruzando datos con
    DuckDB, MongoDB y Delta Lake.

    Parameters
    ----------
    db_con:
        Conexión activa a DuckDB / MotherDuck.
    delta_table:
        Tabla Ibis ya inicializada apuntando a la Delta Lake (R2).
        Debe exponer las columnas: `id_ot`, `Cuenta`, `Evento`, `Iniciales`.
    mongo_collection:
        Colección `pymongo` (típicamente `db_eerssa.ot_v30`).
    df_marcas:
        DataFrame producido por `scan_and_ingest()`.
    df_personal:
        Hoja de personal traída con `gdrive_utils.read_worksheet`. Se asume
        que contiene al menos: `USER_ID`, `NOMBRE`, `INICIALES`, `CUADRILLA`.
    """

    # Columnas heredadas directamente de df_marcas
    _COLS_HEREDADAS = [
        "fecha_registro", "user_id",
        "Entrada_1", "Salida_1", "Entrada_2", "Salida_2",
        "Observado", "Justificado",
    ]

    # Etiquetas usadas en la columna `Cuenta` de Delta Lake
    _TAG_SE_LABORA = "se_labora"
    _TAG_LUNCH = "lunch"

    def __init__(
        self,
        db_con: duckdb.DuckDBPyConnection,
        delta_table: Any,               # ibis.expr.types.Table
        mongo_collection: Any,          # pymongo.collection.Collection
        df_marcas: pd.DataFrame,
        df_personal: pd.DataFrame,
    ):
        self.db_con = db_con
        self.delta_table = delta_table
        self.mongo_collection = mongo_collection
        self.df_marcas = df_marcas
        self.df_personal = df_personal

        # Caches para reducir latencia en llamadas repetidas
        # MongoDB: key = fecha ISO (YYYY-MM-DD), value = lista de docs de ese día
        self._mongo_docs_by_date: dict[str, list[dict]] = {}
        # Delta Lake: key = frozenset(ots), value = (se_labora_list, lunch_list)
        self._delta_cache: dict[frozenset, tuple[list[str], list[str]]] = {}
        # Personal: key = user_id, value = dict con datos del trabajador
        self._personal_cache: dict[int, dict] = {}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build(self) -> pd.DataFrame:
        """
        Devuelve `df_justif` listo para ser insertado en la tabla
        `justificacion` mediante `BiometricoDB.insert_new_justificaciones`.

        Raises
        ------
        NoNewRowsError
            Si todas las filas de `df_marcas` ya están en `justificacion`.
        MongoConnectionError, DeltaConnectionError
            Si falla alguna fuente externa.
        """
        df_nuevos = self._filtrar_filas_nuevas(self.df_marcas)
        if df_nuevos.empty:
            raise NoNewRowsError(
                "Todas las filas de df_marcas ya existen en 'justificacion'."
            )

        # Columnas heredadas
        df_justif = df_nuevos[self._COLS_HEREDADAS].copy().reset_index(drop=True)

        # Enriquecimiento fila a fila.
        iniciales, archivo, ots_list, se_labora_list, lunch_list = [], [], [], [], []

        for _, row in df_justif.iterrows():
            user_id = int(row["user_id"])
            fecha_reg: date = pd.to_datetime(row["fecha_registro"]).date()

            personal = self._get_personal(user_id)
            nombre = personal.get("NOMBRE", "")

            iniciales.append(personal.get("INICIALES", ""))
            archivo.append(self._build_archivo(personal, fecha_reg))

            ots = self._get_ots_for_worker(nombre, fecha_reg)
            ots_list.append(ots)

            se_lab, lunch = self._get_delta_texts(ots)
            se_labora_list.append(se_lab)
            lunch_list.append(lunch)

        df_justif["Iniciales"] = iniciales
        df_justif["Detalle"] = ""            # llenado a mano en Marimo
        df_justif["ots"] = ots_list
        df_justif["se_labora"] = se_labora_list
        df_justif["lunch"] = lunch_list
        df_justif["archivo"] = archivo

        # Reordenar según schema de la tabla `justificacion`
        return df_justif[[
            "fecha_registro", "user_id", "Iniciales",
            "Entrada_1", "Salida_1", "Entrada_2", "Salida_2",
            "Observado", "Justificado", "Detalle",
            "ots", "se_labora", "lunch", "archivo",
        ]]

    # ------------------------------------------------------------------
    # Filtrado contra DuckDB
    # ------------------------------------------------------------------

    def _filtrar_filas_nuevas(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Devuelve solo filas cuyas (fecha_registro, user_id) NO existan
        aún en la tabla `justificacion`.
        """
        try:
            existentes = self.db_con.execute(
                "SELECT fecha_registro, user_id FROM justificacion"
            ).df()
        except duckdb.Error as e:
            raise JustificarError(f"Error consultando DuckDB: {e}") from e

        if existentes.empty:
            return df

        # Normalizar tipos para el merge
        df = df.copy()
        df["fecha_registro"] = pd.to_datetime(df["fecha_registro"]).dt.date
        existentes["fecha_registro"] = pd.to_datetime(
            existentes["fecha_registro"]
        ).dt.date

        merged = df.merge(
            existentes,
            on=["fecha_registro", "user_id"],
            how="left",
            indicator=True,
        )
        return merged[merged["_merge"] == "left_only"].drop(columns="_merge")

    # ------------------------------------------------------------------
    # Datos de personal (cache local)
    # ------------------------------------------------------------------

    def _get_personal(self, user_id: int) -> dict:
        if user_id not in self._personal_cache:
            try:
                self._personal_cache[user_id] = get_all_data(
                    str(user_id), "USER_ID", self.df_personal
                ) or {}
            except Exception as e:
                # No tumbamos el pipeline: log y dict vacío.
                print(f"  ⚠️  personal no encontrado para user_id={user_id}: {e}")
                self._personal_cache[user_id] = {}
        return self._personal_cache[user_id]

    def _build_archivo(self, personal: dict, fecha_reg: date) -> str:
        """Delegates in `gdrive_utils.build_filename` para producir la etiqueta."""
        try:
            data = {
                "cuadrilla": personal.get("CUADRILLA", ""),
                "responsable": [personal.get("NOMBRE", "")],
                "fecha": fecha_reg.isoformat(),
            }
            return build_filename(data, self.df_personal)
        except Exception as e:
            print(f"  ⚠️  no se pudo construir 'archivo': {e}")
            return ""

    # ------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------

    def _get_ots_for_worker(self, nombre: str, fecha_reg: date) -> list[int]:
        """
        Retorna la lista de `id_ot` donde `nombre` aparece como responsable
        o colaborador en la fecha indicada.
        """
        if not nombre:
            return []

        docs = self._get_mongo_docs_by_date(fecha_reg)
        ots: list[int] = []
        for doc in docs:
            resp = (doc.get("responsable") or [None])[0]
            if resp == nombre:
                ots.append(int(doc["id_ot"]))
                continue

            colabs = doc.get("colaboradores", {})
            total = colabs.get("total", 0)
            if not total:
                continue
            for entry in colabs.get("nombres", []):
                # entry = [nombre, cargo]
                if entry and entry[0] == nombre:
                    ots.append(int(doc["id_ot"]))
                    break
        return ots

    def _get_mongo_docs_by_date(self, fecha_reg: date) -> list[dict]:
        """
        Devuelve todos los documentos de MongoDB cuya `fecha` (campo string
        con TZ) coincide con `fecha_reg` (por su prefijo YYYY-MM-DD).
        Cachea por fecha para servir a todos los trabajadores de ese día.
        """
        key = fecha_reg.isoformat()
        if key in self._mongo_docs_by_date:
            return self._mongo_docs_by_date[key]

        try:
            # `fecha` en MongoDB es "YYYY-MM-DDTHH:MM:SS-05:00"
            # -> match por prefijo con regex anclado.
            cursor = self.mongo_collection.find(
                {"fecha": {"$regex": f"^{key}"}}
            )
            docs = list(cursor)
        except Exception as e:
            raise MongoConnectionError(
                f"Error consultando MongoDB para fecha {key}: {e}"
            ) from e

        self._mongo_docs_by_date[key] = docs
        return docs

    # ------------------------------------------------------------------
    # Delta Lake
    # ------------------------------------------------------------------

    def _get_delta_texts(
        self, ots: list[int]
    ) -> tuple[list[str], list[str]]:
        """
        Para la lista de `ots` devuelve (se_labora, lunch) formateados.
        Cachea por frozenset(ots) — filas con las mismas OTs comparten
        resultado.
        """
        if not ots:
            return [], []

        cache_key = frozenset(ots)
        if cache_key in self._delta_cache:
            return self._delta_cache[cache_key]

        try:
            t = self.delta_table
            # Ibis-agnostic: filtrar por id_ot in ots y traer a pandas
            df = (
                t.filter(t.id_ot.isin(list(ots)))
                 .select("id_ot", "Cuenta", "Evento", "Iniciales")
                 .execute()
            )
        except Exception as e:
            raise DeltaConnectionError(
                f"Error consultando Delta Lake para ots={ots}: {e}"
            ) from e

        se_labora: list[str] = []
        lunch: list[str] = []

        for _, r in df.iterrows():
            cuenta = str(r.get("Cuenta", "")).strip()
            id_ot = r.get("id_ot")
            evento = str(r.get("Evento", "")).strip()
            row_iniciales = str(r.get("Iniciales", "")).strip()

            if cuenta == self._TAG_SE_LABORA:
                se_labora.append(f"OT # {id_ot}. {evento}")
            elif cuenta == self._TAG_LUNCH:
                lunch.append(f"OT # {id_ot} = {row_iniciales} = {evento}.")

        result = (se_labora, lunch)
        self._delta_cache[cache_key] = result
        return result
