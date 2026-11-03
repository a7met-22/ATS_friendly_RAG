


"""PostgreSQL connection management."""

from pathlib import Path


from dotenv import load_dotenv

# Load .env before importing settings.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

import psycopg

from config.settings import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
)


def get_connection() -> psycopg.Connection:
    """Create a PostgreSQL connection.

    Transaction management is controlled by the caller.
    """
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10,
    )