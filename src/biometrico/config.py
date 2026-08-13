"""
Central place for environment loading and external connection factories.

Marimo notebooks should call these functions to obtain ready-to-use
connections/clients, rather than embedding credential handling, secret
strings, or endpoint sanitization inline in notebook cells. This keeps the
notebook readable as a sequence of high-level steps.

Design notes:
- Each `init_*` function is a plain factory: call it, get a fresh object.
  No caching/memoization is done here -- marimo's own reactive cell graph
  is what "caches" these values (a cell only reruns when its inputs change),
  so caching in this module too would risk stale connections surviving a
  .env edit or reactive update.
- Required env vars are validated eagerly with `_require_env`, so a missing
  var fails loudly and immediately with a clear message, instead of a bare
  KeyError bubbling up from deep inside a factory.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import duckdb
import ibis
import pymongo
from dotenv import load_dotenv

from gdrive_utils import GDriveConfig

load_dotenv()


def _require_env(*names: str) -> dict:
    """Fetch required env vars, raising a single clear error if any are missing."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Check your .env file."
        )
    return {n: os.environ[n] for n in names}


def _clean_endpoint(raw: str) -> str:
    """DuckDB's S3 ENDPOINT secret param wants a bare host, not a full URL.
    Strips scheme (e.g. https://) if present so we don't end up with
    https://https://... style errors."""
    parsed = urlparse(raw)
    return parsed.netloc if parsed.netloc else raw


# ---------------------------------------------------------------------------
# DuckDB / MotherDuck
# ---------------------------------------------------------------------------

def init_duckdb(database: str = "md:biometrico") -> duckdb.DuckDBPyConnection:
    """Connect to MotherDuck (or any DuckDB-compatible database string)."""
    return duckdb.connect(database)


# ---------------------------------------------------------------------------
# MongoDB (Órdenes de Trabajo)
# ---------------------------------------------------------------------------

def init_mongo_collection(
    db_name: str = "eerssa", collection: str = "ot_v30"
) -> pymongo.collection.Collection:
    """Connect to MongoDB and return the OT collection handle.
    Esquema esperado: v0.3.0."""
    env = _require_env("MONGO_URI")
    client = pymongo.MongoClient(env["MONGO_URI"])
    return client[db_name][collection]


# ---------------------------------------------------------------------------
# R2 / Delta Lake (via Ibis + DuckDB backend)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class R2Settings:
    bucket: str
    key: str
    secret: str
    endpoint: str

    @classmethod
    def from_env(cls) -> "R2Settings":
        env = _require_env("R2_BUCKET", "R2_KEY", "R2_SECRET", "R2_ENDPOINT")
        return cls(
            bucket=env["R2_BUCKET"],
            key=env["R2_KEY"],
            secret=env["R2_SECRET"],
            endpoint=env["R2_ENDPOINT"],
        )


def init_delta_table(table_subpath: str = "delta_v30"):
    """Set up an Ibis-on-DuckDB backend with an R2 secret registered, and
    read the given Delta table.

    Returns:
        (ibis_con, delta_table): the Ibis backend connection (kept around
        in case downstream code needs it) and the Ibis table handle for
        the Delta table itself.
    """
    r2 = R2Settings.from_env()
    ibis_con = ibis.duckdb.connect()
    ibis_con.con.execute(f"""
        CREATE SECRET r2_secret (
            TYPE S3,
            KEY_ID '{r2.key}',
            SECRET '{r2.secret}',
            ENDPOINT '{_clean_endpoint(r2.endpoint)}',
            URL_STYLE 'path',
            REGION 'auto'
        );
    """)
    table_path = f"s3://{r2.bucket}/{table_subpath}"
    delta_table = ibis_con.read_delta(table_path)
    return ibis_con, delta_table


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def init_gdrive_config() -> GDriveConfig:
    """Build the GDriveConfig used by gdrive_utils.read_worksheet / etc.
    Kept as a thin wrapper so every external service is instantiated the
    same way from the notebook (config.init_x())."""
    return GDriveConfig()
