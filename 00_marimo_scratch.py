import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium", app_title="BIOMETRICO")


@app.cell
def _():
    import marimo as mo
    import duckdb
    import ibis
    import pymongo

    import os
    from urllib.parse import urlparse
    from datetime import date

    from src.biometrico.ingestion import scan_and_ingest
    from src.biometrico.biometricoDB import BiometricoDB
    from src.biometrico.justificar import Justificar
    from gdrive_utils import GDriveConfig, read_worksheet, get_all_data, build_filename

    # Cargar las variables de entorno desde el archivo .env
    from dotenv import load_dotenv
    load_dotenv()
    return (
        BiometricoDB,
        GDriveConfig,
        Justificar,
        duckdb,
        ibis,
        mo,
        os,
        pymongo,
        read_worksheet,
        scan_and_ingest,
        urlparse,
    )


@app.cell
def _(duckdb):
    # 1. Conexión a DuckDB (MotherDuck)

    try:
        # Connects to MotherDuck and opens the 'biometrico' database
        db_con = duckdb.connect('md:biometrico')
        print("Conexión exitosa a MotherDuck: DB 'biometrico'")
    except Exception as e:
        print(f"Error connecting to MotherDuck: {e}")
    return (db_con,)


@app.cell
def _(os, pymongo):
    # 2. Conexión a MongoDB (para las Órdenes de Trabajo - OTs)
    # El esquema esperado es la versión "0.3.0" [6]
    mongo_client = pymongo.MongoClient(os.environ["MONGO_URI"])
    mongo_collection = mongo_client["eerssa"]["ot_v30"]
    return (mongo_collection,)


@app.cell
def _(os):
    # 3. Conexión a Delta Lake usando Ibis
    # Pasamos un objeto 'ibis table' ya inicializado
    # Nota: Ajusta la ruta y opciones según tu configuración de R2/S3
    table_path = f"s3://{os.environ['R2_BUCKET']}/delta_v30"
    storage_options = {
        "key": os.environ["R2_KEY"],
        "secret": os.environ["R2_SECRET"],
        "endpoint_url": os.environ["R2_ENDPOINT"],
        "AWS_REGION": "auto",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true"
    }
    return (table_path,)


@app.cell
def _(ibis, os, urlparse):
    # 2. Ibis Backend con DuckDB y configuración de R2
    # Conectamos Ibis al backend de DuckDB
    ibis_con = ibis.duckdb.connect()

    # Sanitizar el endpoint: DuckDB espera solo el hostname para el parámetro ENDPOINT
    _raw_endpoint = os.environ.get("R2_ENDPOINT", "")
    # Si el usuario puso https://, lo removemos para evitar el error https://https://
    _parsed_url = urlparse(_raw_endpoint)
    _clean_endpoint = _parsed_url.netloc if _parsed_url.netloc else _raw_endpoint
    # Configuramos las credenciales de R2 
    # directamente en DuckDB usando un SECRET [2, 3]
    ibis_con.con.execute(f"""
        CREATE SECRET r2_secret (
            TYPE S3,
            KEY_ID '{os.environ["R2_KEY"]}',
            SECRET '{os.environ["R2_SECRET"]}',
            ENDPOINT '{_clean_endpoint}',
            URL_STYLE 'path',
            REGION 'auto'
        );
    """)
    return (ibis_con,)


@app.cell
def _(ibis_con, table_path):
    delta_table = ibis_con.read_delta(table_path)
    return (delta_table,)


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(f"**✅ Conectado** a las base de datos: DuckDB 🦆 MongoDB 🍃, Delta Lake: 🪣 "),
        kind="success",
    )
    return


@app.cell
def _(os, scan_and_ingest):
    # ==========================================
    # Ejemplo de uso (esto iría en tu notebook Marimo o script principal)
    # ==========================================
    if __name__ == "__main__":
        # Obtener la ruta desde .env, con un fallback de seguridad
        #                    "PDF_TEST_PATH"
        #                    "PDF_FILE_PATH"
        env_path = os.getenv("PDF_TEST_PATH", "~/OneDrive/01 JEZO/00 Asistencia Biometrico")

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
    dfs_validos[0]
    return


@app.cell
def _(BiometricoDB, db_con):
    cloud_db = BiometricoDB(db_con)
    return (cloud_db,)


@app.cell
def _(cloud_db, dfs_validos):
    cloud_db.upsert_marcas(dfs_validos[0])
    return


@app.cell
def _(GDriveConfig, read_worksheet):
    config = GDriveConfig()

    df_personal = read_worksheet(config)
    df_personal
    return (df_personal,)


@app.cell
def _(
    Justificar,
    db_con,
    delta_table,
    df_personal,
    dfs_validos,
    mo,
    mongo_collection,
):
    try:
        # Dependency Injection: Pasamos las conexiones y los DFs base [1, 8, 11]
        justificador = Justificar(
            db_con=db_con, # Conexión a MotherDuck/DuckDB para la tabla 'justificacion'
            delta_table=delta_table, # Tabla Ibis ya inicializada
            mongo_collection=mongo_collection,
            df_marcas=dfs_validos[0],
            df_personal=df_personal
        )

        # El método build() orquestra el filtrado y enriquecimiento [1, 10]
        df_justif = justificador.build()

        # UI para mostrar el resultado en Marimo [12, 13]
        result_ui = mo.vstack([
            mo.md("### ✅ Nuevas Justificaciones Generadas"),
            mo.ui.table(df_justif)
        ])

    except ValueError as e:
        # Capturamos NoNewRowsError si todas las filas ya están en la DB [1, 10, 14]
        result_ui = mo.md(f"ℹ️ **Aviso:** {str(e)}")
    except Exception as e:
        # Manejo de errores de conexión (Mongo/Delta/R2) [10, 14]
        result_ui = mo.md(f"❌ **Error en el proceso:** {str(e)}")

    result_ui
    return


if __name__ == "__main__":
    app.run()
