import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="BIOMETRICO")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # JUSTIFICACIÓN DE ASISTENCIAS
    >Ernesto Palacios / junio-2026
    """)
    return


@app.cell
def _():
    import os
    import calendar
    import locale
    import marimo as mo
    import pandas as pd

    from datetime import date as toDate
    from datetime import datetime, time, timedelta

    from src.biometrico import config
    from src.biometrico.ingestion import scan_and_ingest
    from src.biometrico.biometricoDB import BiometricoDB
    from src.biometrico.justificar import Justificar
    from gdrive_utils import read_worksheet, get_all_data, build_filename, calendario

    from gdrive_utils.permisos import read_permisos
    from gdrive_utils.calendario import read_calendario

    return (
        BiometricoDB,
        Justificar,
        calendar,
        config,
        locale,
        mo,
        os,
        pd,
        read_worksheet,
        scan_and_ingest,
        timedelta,
        toDate,
    )


@app.cell
def _(BiometricoDB, config):
    # 1. Conexión a DuckDB (MotherDuck)
    db_con = config.init_duckdb()
    cloud_db = BiometricoDB(db_con)
    return cloud_db, db_con


@app.cell
def _(config):
    # 2. Conexión a MongoDB (para las Órdenes de Trabajo - OTs)
    mongo_collection = config.init_mongo_collection()
    return (mongo_collection,)


@app.cell
def _(config):
    # 3. Conexión a Delta Lake (Ibis + DuckDB backend, secret R2 registrado)
    ibis_con, delta_table = config.init_delta_table()
    return (delta_table,)


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md("**✅ Conectado** a las base de datos: DuckDB 🦆 MongoDB 🍃, Delta Lake: 🪣 "),
        kind="success",title="CONEXION CON LA NUBE"
    )
    return


@app.cell
def _2_ingesta(os, scan_and_ingest):
    env_path = os.getenv("PDF_FILE_PATH", "~/OneDrive/01 JEZO/00 Asistencia Biometrico")

    dfs_validos, archivos_malos = scan_and_ingest(
        base_path_str=env_path,
        regex_pattern=r"^\d{2}-\d{2}\s",
        ext=".pdf"
    )

    print("\n--- RESUMEN DE LA INGESTA ---")
    print(f"Total de archivos procesados exitosamente: {len(dfs_validos)}")

    if archivos_malos:
        print(f"\n⚠️ ATENCIÓN: Hubo {len(archivos_malos)} archivos fallidos/descartados:")
        for malo in archivos_malos:
            print(f" - {malo}")
    return (dfs_validos,)


@app.cell
def _(dfs_validos, pd):
    df_marcas = pd.concat(dfs_validos, ignore_index=True)
    df_marcas.to_pickle("df_marcas.pkl")

    #df_marcas = pd.read_pickle("df_marcas.pkl")
    return (df_marcas,)


@app.cell
def subir_marcas(cloud_db, df_marcas):
    cloud_db.upsert_marcas(df_marcas)
    return


@app.cell
def _(config, e, mo, read_worksheet):
    # 4. Configuración y hoja de personal desde Google Drive
    try:
        gdrive_config = config.init_gdrive_config()
        df_personal = read_worksheet(gdrive_config)
        df_personal["USER_ID"] = df_personal["USER_ID"].astype(str)
        _result_ui = mo.callout(mo.md("✅ Cargado los datos del personal desde GDrive"),kind="success")
    except:
        _result_ui = mo.md(f"❌ **No se pudo leer desde Google Drive > Iniciales: ** {str(e)}")

    _result_ui
    return (df_personal,)


@app.cell
def _(
    Justificar,
    cloud_db,
    db_con,
    delta_table,
    df_final,
    df_personal,
    mo,
    mongo_collection,
):
    # Dependency Injection: Pasamos las conexiones y los DFs base
    justificador = Justificar(
        db_con=db_con,
        delta_table=delta_table,
        mongo_collection=mongo_collection,
        df_marcas=df_final,
        df_personal=df_personal
    )
    try:
        df_justif = justificador.build()
        cloud_db.insert_new_justificaciones(df_justif)

        _result_ui = mo.vstack([
            mo.md("### ✅ Nuevas Justificaciones Generadas"),
            mo.ui.table(df_justif)
        ])

    except ValueError as e:
        _result_ui = mo.md(f"ℹ️ **Aviso:** {str(e)}")
    except Exception as e:
        _result_ui = mo.md(f"❌ **Error en el proceso:** {str(e)}")

    _result_ui
    return


@app.cell
def _(calendar, mo, timedelta, toDate):
    # Defaults: first and last day of current month
    _today = toDate.today()
    _first_day = _today.replace(day=1)
    _prev_month_first = (_first_day - timedelta(days=1)).replace(day=1)
    _last_day = _today.replace(day=calendar.monthrange(_today.year, _today.month)[1])

    date_picker = mo.ui.date_range(
        start=_first_day,
        stop=_last_day,
        value=(_first_day, _last_day),
        label="📅 Rango del Reporte",
    )

    mo.md(f"## 1. Seleccione el rango de fechas para el Informe\n{date_picker}")
    return (date_picker,)


@app.cell
def _(date_picker, locale, mo):
    ecuador = locale.setlocale(locale.LC_TIME, "es_EC.UTF-8")
    reporte_inicia, reporte_finaliza = date_picker.value
    mo.callout(
        mo.md(
            f"**Reporte desde el:** <br>| _`{reporte_inicia:%A, %d %B %Y}`_ |<br> hasta el → <br>| _`{reporte_finaliza:%A, %d %B %Y}`_ | 📅"
        ),
        kind="neutral"
    )
    return (reporte_inicia,)


@app.cell
def _(reporte_inicia):
    type(reporte_inicia)
    return


if __name__ == "__main__":
    app.run()
