# AGENTS.md

## Persona
- Rol: Experto en ingestión y estructuración de datos. Salidas concisas, técnicas, bilingües (ES/EN).
- Antes de implementar/refactor, consulta `@notas_arquitectura/` (referenciado en `opencode.json`, ruta externa en OneDrive).

## Proyecto
- Procesa PDFs de marcaciones biométricas -> DuckDB/MotherDuck (`md:biometrico`).
- Entrypoint interactivo: `00_marimo_scratch.py` (marimo notebook). No hay CLI ni tests.
- Código en `src/biometrico/`:
  - `ingestion.py` — `scan_and_ingest()`, `PDFExtractor` (PyMuPDF/fitz), filtrado por regex de nombre.
  - `biometricoDB.py` — clase `BiometricoDB(connection)`, DI de conexión DuckDB. Tablas: `marcas`, `justificacion` (PK: `fecha_registro,user_id`).
- MongoDB (`pymongo`) y Delta Lake (Cloudflare R2, vía `ibis-framework`) son implementadas en clase `justificar`
- Plantillas Excel en `xlsx_templates/` (ignorado por `.opencodeignore`).

## Comandos
- Gestor de dependencias: **uv** (ver `uv.lock`, `pyproject.toml`). Python `>=3.10`.
- Instalar: `uv sync`
- Ejecutar notebook: `uv run marimo edit 00_marimo_scratch.py`
- Añadir dependencia: `uv add <pkg>` (no editar `pyproject.toml` a mano si es evitable).
- `gdrive-utils` se instala desde git (ver `[tool.uv.sources]`).

## Entorno / secretos
- `.env` y `.gdrive_creds.json` están **denied** en `opencode.json` — nunca leer ni imprimir su contenido.
- `.r2_creds.json`: credenciales Cloudflare R2 para Delta Lake (en `.gitignore`, no denied explícito — evita leerlo igualmente).
- Variables usadas: `PDF_TEST_PATH`, `PDF_FILE_PATH` (rutas base con PDFs a ingerir); `MARGEN_SUPERIOR` (offset del header del PDF en `PDFExtractor`, default `25`).
- MotherDuck: `duckdb.connect('md:biometrico')` requiere token en entorno.

## Convenciones repo
- `.opencodeignore` oculta `tests/`, `notebooks/`, `xlsx_templates/`, `LOGS/`, `.venv/`, `__marimo__/` — no asumir que no existen; solo no están indexados.
- No hay tests, lint ni CI configurados. Si añades verificación, documéntalo aquí.
- `pyproject.toml` tiene typo `[buid-system]`/`hatching.build`; no lo "arregles" sin confirmar (el proyecto no se build-ea, solo se ejecuta).

