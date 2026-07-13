import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium", app_title="BIOMETRICO")


@app.cell
def _():
    import marimo as mo
    import os
    import duckdb
    from dotenv import load_dotenv
    from src.biometrico.ingestion import scan_and_ingest
    from src.biometrico.biometricoDB import BiometricoDB
    from gdrive_utils import GDriveConfig, read_worksheet, get_all_data

    # Cargar las variables de entorno desde el archivo .env
    load_dotenv()
    return (
        BiometricoDB,
        GDriveConfig,
        duckdb,
        get_all_data,
        os,
        read_worksheet,
        scan_and_ingest,
    )


@app.cell
def _(duckdb):
    try:
        # Connects to MotherDuck and opens the 'biometrico' database
        db_con = duckdb.connect('md:biometrico')
        print("Conexión exitosa a MotherDuck: DB 'biometrico'")
    except Exception as e:
        print(f"Error connecting to MotherDuck: {e}")
    return (db_con,)


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
    dfs_validos[0]#["Entrada_1"][10]
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

    df_lin = read_worksheet(config)
    df_lin
    return (df_lin,)


@app.cell
def _(df_lin, get_all_data):
    _test = get_all_data('1480',"USER_ID",df_lin)
    _test
    return


if __name__ == "__main__":
    app.run()
