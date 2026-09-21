"""PostgreSQL connection helpers for the Neon database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


def get_database_url() -> str:
    """Return the database URL without exposing it in logs or exceptions."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not configured")
    return database_url


def get_connection() -> Connection[Any]:
    """Open a connection to PostgreSQL using the configured Neon URL."""
    return psycopg.connect(get_database_url(), row_factory=dict_row)


@contextmanager
def connection() -> Iterator[Connection[Any]]:
    """Yield a connection and commit or roll back its transaction.

    The connection is always closed when the operation finishes. Read-only
    operations are committed too, which keeps transaction handling consistent.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
