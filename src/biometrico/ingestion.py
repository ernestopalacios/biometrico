import os
import re
from pathlib import Path
from typing import Protocol, List
import pandas as pd
from dotenv import load_dotenv

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
                
                # ==========================================
                # Definir el área de búsqueda (Bounding Box)
                # ==========================================
                margen_superior = 25  #14 con titulo y a veces error, 
                
                # page.rect nos da las dimensiones reales (ej. 842 x 1191 para A3)
                area_de_busqueda = fitz.Rect(
                    0,                   # x0: Izquierda 
                    margen_superior,     # y0: Bajar 80 puntos desde el tope
                    page.rect.width,     # x1: Derecha (ancho total)
                    page.rect.height     # y1: Abajo (alto total)
                )
                
                # Extraer usando el parámetro clip
                tables = page.find_tables(clip=area_de_busqueda)
                
                if tables:
                    table = tables[0]
                    df_page = table.to_pandas()
                    df_page.dropna(how='all', inplace=True)
                    all_tables.append(df_page)
                else:
                    print(f"  -> Advertencia: No se encontró tabla en la pág {page_num + 1}")
        
        if not all_tables:
            print(f"Advertencia: El archivo {file_path.name} está vacío o sin tablas legibles.")
            return pd.DataFrame()
            
        final_df = pd.concat(all_tables, ignore_index=True)
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

def scan_and_ingest(base_path_str: str, regex_pattern: str, ext: str) -> List[pd.DataFrame]:
    """
    Escanea un directorio sin recursividad, filtra por regex y extensión, 
    y extrae los datos usando la estrategia inyectada.
    """
    # Resolver la ruta de forma OS-Agnostic
    # expanduser() convierte '~' a la ruta correcta en Windows o Linux
    base_path = Path(base_path_str).expanduser()

    if not base_path.exists():
        raise FileNotFoundError(f"El directorio no existe: {base_path}")

    # Compilar el regex para filtrar los nombres de archivo
    pattern = re.compile(regex_pattern)
    
    # Obtener el extractor adecuado (Inyección de Dependencia)
    extractor = get_extractor(ext)

    dataframes = []

    # Iterar sobre el directorio sin recursividad
    for file_path in base_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() == ext.lower():
            # Verificar si el nombre del archivo coincide con el patrón regex
            if pattern.match(file_path.name):
                # Extraer los datos y agregarlos a la lista
                df = extractor.extract(file_path)
                dataframes.append(df)

    return dataframes
