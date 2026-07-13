import os
import re
from pathlib import Path
from typing import Protocol, List
import pandas as pd
from dotenv import load_dotenv
from datetime import date, datetime

import fitz   # PyMuPDF
import pandas as pd
from pathlib import Path

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# ==========================================
# 1. Interfaces & Estrategias (Dependency Injection)
# ==========================================

class FileExtractor(Protocol):
    """
    Protocolo (Interface) para los extractores de archivos.
    Cualquier clase que implemente este protocolo debe tener un método 'extract'.
    """
    def extract(self, file_path: Path) -> pd.DataFrame:
        ...

class PDFExtractor:
    """Estrategia concreta para extraer tablas de archivos PDF."""
    def extract(self, file_path: Path) -> pd.DataFrame:
        print(f"Procesando PDF: {file_path.name}")

        all_tables = []

        with fitz.open(file_path) as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # El valor óptimo encontrado es 25 para saltar el encabezado
                margen_superior = os.getenv("MARGEN_SUPERIOR",25)
                area_de_busqueda = fitz.Rect(
                    0,
                    margen_superior,
                    page.rect.width,
                    page.rect.height
                )

                tables = page.find_tables(clip=area_de_busqueda)

                if tables:
                    df_page = tables[0].to_pandas()

                    # ---------------------------------------------------------
                    # Limpieza 1: Eliminar filas fantasma (usando la 2da columna)
                    # ---------------------------------------------------------
                    if df_page.shape[1] >= 2: # Asegurar que hay al menos 2 columnas
                        # iloc[:, 1] selecciona la segunda columna
                        col_2_name = df_page.columns[1]

                        # a) Eliminar si es un valor nulo real (NaN)
                        df_page = df_page.dropna(subset=[col_2_name])

                        # b) Eliminar si dice textualmente 'None'
                        df_page = df_page[df_page[col_2_name].astype(str).str.strip() != 'None']

                    # Limpieza 2: Eliminar filas completamente vacías
                    df_page.dropna(how='all', inplace=True)

                    # Limpieza 3: Eliminar la columna 10 - Para uso en HE
                    df_page = df_page.drop(columns=df_page.columns[10])

                    # Limpieza 4: Crea la columna 'fecha_registro' a partir de la fecha
                    df_page["fecha_registro"] = pd.to_datetime(df_page["Fecha"], format='%d/%m/%Y')

                    # Para auditoria, regustro cuando fue creado y actualizado el registro.
                    df_page["creacion"] = datetime.now()
                    df_page["actualizacion"] = datetime.now()

                    # Cambiar todos los nombres de golpe
                    df_page.columns = ["Dia","Fecha","Tipo","Estado","Entrada_1","Salida_1",
                        "Entrada_2","Salida_2","Observado","Justificado","Detalle","user_id","fecha_registro",
                        "creacion","actualizacion"
                    ]

                    # Convertimos "SI" a True y todo lo demás (incluyendo "NO", NaN, o vacíos) a False
                    df_page["Observado"] = df_page["Observado"].eq("SI")
                    df_page["Justificado"] = df_page["Justificado"].eq("SI")

                    # Marcas vacias deben ser de tipo 'None'
                    time_cols = ['Entrada_1', 'Salida_1', 'Entrada_2', 'Salida_2']
                    df_page[time_cols] = df_page[time_cols].replace('', None)

                    if not df_page.empty:
                        all_tables.append(df_page)

        if not all_tables:
            raise ValueError("El directorio está vacío o no contiene tablas legibles.")

        final_df = pd.concat(all_tables, ignore_index=True)
        final_df = final_df.sort_values(by='fecha_registro')

        # ---------------------------------------------------------
        # Validación Estricta: Exactamente 13 columnas
        # ---------------------------------------------------------
        num_columnas = final_df.shape[1]
        if num_columnas != 15:
            # Lanzamos un error que será capturado por el orquestador
            raise ValueError(f"Estructura inválida. Se esperaban 15 columnas, pero se encontraron {num_columnas}.")

        return final_df

class CSVExtractor:
    """Estrategia concreta para el futuro: extraer de archivos CSV."""
    def extract(self, file_path: Path) -> pd.DataFrame:
        # Lógica futura para leer CSVs
        print(f"Procesando CSV: {file_path.name}")
        return pd.read_csv(file_path)

# ==========================================
# 2. Pattern Matching Factory
# ==========================================

def get_extractor(extension: str) -> FileExtractor:
    """
    Usa Pattern Matching para inyectar la dependencia correcta
    basada en la extensión del archivo.
    """
    match extension.lower():
        case ".pdf":
            return PDFExtractor()
        case ".csv":
            return CSVExtractor()
        case ".xlsx" | ".xls":
            # Listo para cuando agregues OpenPyXL
            raise NotImplementedError("El extractor de Excel aún no está implementado.")
        case _:
            raise ValueError(f"Extensión no soportada: {extension}")

# ==========================================
# 3. Lógica de Filtrado y Ejecución
# ==========================================

def scan_and_ingest(base_path_str: str, regex_pattern: str, ext: str) -> tuple[List[pd.DataFrame], List[str]]:
    """
    Escanea el directorio, extrae datos y lleva un registro de los archivos fallidos.
    Retorna una tupla: (lista_de_dataframes, lista_de_archivos_fallidos)
    """
    base_path = Path(base_path_str).expanduser()

    if not base_path.exists():
        raise FileNotFoundError(f"El directorio no existe: {base_path}")

    pattern = re.compile(regex_pattern)
    extractor = get_extractor(ext)

    dataframes = []
    archivos_fallidos = []

    # Iterar sobre el directorio sin recursividad
    for file_path in base_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() == ext.lower():
            if pattern.match(file_path.name):
                try:
                    df = extractor.extract(file_path)
                    dataframes.append(df)
                    print(f"  -> ¡Éxito! Importado {file_path.name}")

                # Aquí capturamos el error de "No son 13 columnas" o "No hay tablas"
                except ValueError as e:
                    print(f"  -> ERROR en {file_path.name}: {e} (Descartado)")
                    archivos_fallidos.append(file_path.name)

                except Exception as e:
                    print(f"  -> ERROR INESPERADO en {file_path.name}: {e}")
                    archivos_fallidos.append(file_path.name)

    return dataframes, archivos_fallidos
