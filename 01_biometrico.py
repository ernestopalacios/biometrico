import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="BIOMETRICO")


@app.cell
def _():
    import os
    import marimo as mo
    import pandas as pd

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
        config,
        mo,
        os,
        pd,
        read_worksheet,
        scan_and_ingest,
    )


@app.cell
def _(config):
    # 1. Conexión a DuckDB (MotherDuck)
    db_con = config.init_duckdb()
    return (db_con,)


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
def _(os, scan_and_ingest):
    # ==========================================
    # Ejemplo de uso (esto iría en tu notebook Marimo o script principal)
    # ==========================================
    if __name__ == "__main__":
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
def _(dfs_validos):
    dfs_validos[3]
    return


@app.cell
def _(pd):
    #df_final = pd.concat(dfs_validos, ignore_index=True)
    #df_final.to_pickle("df_final.pkl")

    df_final = pd.read_pickle("df_final.pkl")
    return (df_final,)


@app.cell
def _(df_final):
    df_final['user_id'].unique()
    return


@app.cell
def _(BiometricoDB, db_con):
    cloud_db = BiometricoDB(db_con)
    return (cloud_db,)


@app.cell
def _(cloud_db, df_final):
    cloud_db.upsert_marcas(df_final)
    return


@app.cell
def _(config, read_worksheet):
    # 4. Configuración y hoja de personal desde Google Drive
    gdrive_config = config.init_gdrive_config()

    df_personal = read_worksheet(gdrive_config)
    df_personal["USER_ID"] = df_personal["USER_ID"].astype(str)
    df_personal
    return (df_personal,)


@app.cell
def _(
    Justificar,
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
        #cloud_db.insert_new_justificaciones(df_justif)

        result_ui = mo.vstack([
            mo.md("### ✅ Nuevas Justificaciones Generadas"),
            mo.ui.table(df_justif)
        ])

    except ValueError as e:
        result_ui = mo.md(f"ℹ️ **Aviso:** {str(e)}")
    except Exception as e:
        result_ui = mo.md(f"❌ **Error en el proceso:** {str(e)}")

    result_ui
    return (df_justif,)


@app.cell
def _(df_justif):
    df_justif.info()
    return


@app.cell
def _(cloud_db, df_justif):
    cloud_db.insert_new_justificaciones(df_justif)
    return


if __name__ == "__main__":
    app.run()
