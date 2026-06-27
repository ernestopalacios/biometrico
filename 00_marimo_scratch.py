import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import os
    from dotenv import load_dotenv
    from src.biometrico.ingestion import scan_and_ingest

    # Cargar las variables de entorno desde el archivo .env
    load_dotenv()
    return os, scan_and_ingest


@app.cell
def _(os, scan_and_ingest):
    # ==========================================
    # Ejemplo de uso (esto iría en tu notebook Marimo o script principal)
    # ==========================================
    if __name__ == "__main__":
        # Obtener la ruta desde .env, con un fallback de seguridad
        env_path = os.getenv("PDF_TEST_PATH", "~/OneDrive/01 JEZO/00 Asistencia Biometrico")

        try:
            # Ingestar los archivos PDF que cumplan con el patrón
            # Patrón: ^\d{2}-\d{2}\s (ej. "12-34 archivo.pdf")
            df_list = scan_and_ingest(
                base_path_str=env_path, 
                regex_pattern=r"^\d{2}-\d{2}\s", 
                ext=".pdf"
            )
            print(f"Se extrajeron {len(df_list)} DataFrames exitosamente.")
        except Exception as e:
            print(f"Error durante la ingesta: {e}")
    return (df_list,)


@app.cell
def _(df_list):
    df_list[3]
    return


if __name__ == "__main__":
    app.run()
