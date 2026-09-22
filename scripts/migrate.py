"""Apply the project's PostgreSQL schema using Neon direct connectivity.

Run with ``python -m scripts.migrate``. Migrations deliberately require
DATABASE_URL_UNPOOLED because Neon pooled connections are intended for normal
application traffic, not schema changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from collections.abc import Sequence

import psycopg
from dotenv import load_dotenv
from psycopg import OperationalError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
SCHEMA_FILE = PROJECT_ROOT / "database" / "schema.sql"


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the PostgreSQL schema")
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_FILE,
        help="Schema SQL file to apply (default: database/schema.sql)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    load_dotenv(ENV_FILE)

    database_url = os.getenv("DATABASE_URL_UNPOOLED")
    if not database_url:
        print(
            "DATABASE_URL_UNPOOLED is missing. Set Neon's direct/unpooled "
            "connection URL in .env before running migrations.",
            file=sys.stderr,
        )
        return 1

    schema_file = args.schema
    if not schema_file.is_absolute():
        schema_file = PROJECT_ROOT / schema_file
    try:
        schema_sql = schema_file.read_text(encoding="utf-8")
    except OSError:
        print(
            "The schema file could not be read. Check database/schema.sql.",
            file=sys.stderr,
        )
        return 1

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            connection.execute(schema_sql)
            connection.commit()
    except OperationalError:
        print(
            "Could not connect to PostgreSQL using DATABASE_URL_UNPOOLED. "
            "Check the direct Neon connection and database access settings.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        # Raw database errors can contain connection details or SQL internals.
        print(
            f"Migration failed ({type(exc).__name__}); database details were hidden.",
            file=sys.stderr,
        )
        return 1

    print(f"Database schema applied successfully from {schema_file.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
