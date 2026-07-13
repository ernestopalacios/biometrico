import duckdb
import pandas as pd

class BiometricoDB:
    """
    Gestor de la base de datos 'biometrico' en MotherDuck.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        """
        Dependency injection: We pass the active DuckDB connection
        so the class doesn't need to know about credentials or tokens.
        """
        self.con = connection

    def create_tables(self):
        """
        Generates the 'marcas' and 'justificacion' tables based on the DB schema.
        """
        # Schema for 'marcas' (Base layer, populated from PDF)
        # Using BIGINT for user_id and VARCHAR for strings
        query_marcas = """
        CREATE TABLE IF NOT EXISTS marcas (
            Dia VARCHAR,
            Fecha VARCHAR,
            Tipo VARCHAR,
            Estado VARCHAR,
            Entrada_1 TIME,
            Salida_1 TIME,
            Entrada_2 TIME,
            Salida_2 TIME,
            Observado BOOLEAN,
            Justificado BOOLEAN,
            Detalle VARCHAR,
            user_id BIGINT,
            fecha_registro DATE,
            creacion DATE DEFAULT CURRENT_DATE,
            actualizacion DATE DEFAULT CURRENT_DATE,
            PRIMARY KEY (fecha_registro, user_id)
        );
        """

        # Schema for 'justificacion' (User-editable layer)
        # DuckDB uses TYPE[] for arrays/lists
        query_justificacion = """
        CREATE TABLE IF NOT EXISTS justificacion (
            fecha_registro DATE,
            user_id BIGINT,
            Iniciales VARCHAR,
            Entrada_1 TIME,
            Salida_1 TIME,
            Entrada_2 TIME,
            Salida_2 TIME,
            Observado BOOLEAN,
            Justificado BOOLEAN,
            Detalle VARCHAR,
            ots BIGINT[],
            se_labora VARCHAR[],
            lunch VARCHAR[],
            PRIMARY KEY ("Date", user_id)
        );
        """

        try:
            self.con.execute(query_marcas)
            self.con.execute(query_justificacion)
            print("Tablas 'marcas' y 'justificacion' creadas o verificadas con éxito.")
        except duckdb.Error as e:
            print(f"Error al crear las tablas: {e}")


    def upsert_marcas(self, df_marcas: pd.DataFrame):
        """
        Inserts new records into 'marcas'.
        If the record exists (fecha_registro, user_id), it updates the values
        in case the source PDF was modified, and updates 'actualizacion'.
        """
        # DuckDB can read the pandas dataframe directly from the local scope.
        # EXCLUDED refers to the incoming data that caused the conflict.

        query = """
        INSERT INTO marcas
        SELECT * FROM df_marcas
        ON CONFLICT (fecha_registro, user_id)
        DO UPDATE SET
            Dia = EXCLUDED.Dia,
            Fecha = EXCLUDED.Fecha,
            Tipo = EXCLUDED.Tipo,
            Estado = EXCLUDED.Estado,
            Entrada_1 = EXCLUDED.Entrada_1,
            Salida_1 = EXCLUDED.Salida_1,
            Entrada_2 = EXCLUDED.Entrada_2,
            Salida_2 = EXCLUDED.Salida_2,
            Observado = EXCLUDED.Observado,
            Justificado = EXCLUDED.Justificado,
            Detalle = EXCLUDED.Detalle,
            actualizacion = current_date();
        """

        try:
            # DuckDB automatically finds 'df_marcas' in the local variables
            self.con.execute(query)
            print("✅ UPSERT completado con éxito en la tabla 'marcas'.")
        except duckdb.Error as e:
            print(f"❌ Error durante el UPSERT en 'marcas': {e}")

    def insert_new_justificaciones(self, df_justificacion: pd.DataFrame):
        """
        Inserts new records into 'justificacion'.
        If the record already exists, it does NOTHING to preserve user edits.
        """
        # INSERT OR IGNORE is syntactic sugar for ON CONFLICT DO NOTHING
        query = """
        INSERT OR IGNORE INTO justificacion
        SELECT * FROM df_justificacion;
        """

        try:
            self.con.execute(query)
            print("✅ Inserción segura completada en la tabla 'justificacion'.")
        except duckdb.Error as e:
            print(f"❌ Error durante la inserción en 'justificacion': {e}")
