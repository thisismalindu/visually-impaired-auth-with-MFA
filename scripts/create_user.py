"""Create a demo user through the shared repository.

Run with ``python -m scripts.create_user`` after Member 4's repository module
and database schema have been integrated.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from auth.password_utils import hash_password
from dotenv import load_dotenv
from psycopg import OperationalError, errors


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Argon2-backed demo user")
    parser.add_argument("--username", help="Demo username")
    parser.add_argument("--email", help="Demo user's email address")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    load_dotenv(ENV_FILE)

    if not os.getenv("DATABASE_URL"):
        print(
            "DATABASE_URL is missing. Set it in the project .env file before creating a user.",
            file=sys.stderr,
        )
        return 1

    try:
        from database.repository import DuplicateUserError, create_user
    except (ImportError, ModuleNotFoundError):
        print(
            "database.repository is not available yet. Merge Member 4's "
            "database module before creating demo users.",
            file=sys.stderr,
        )
        return 1

    username = (args.username or input("Username: ")).strip()
    email = (args.email or input("Email: ")).strip()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Password again: ")

    if not username or not email:
        print("Username and email are required.", file=sys.stderr)
        return 2
    if not password:
        print("Password must not be empty.", file=sys.stderr)
        return 2
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    password_hash = hash_password(password)
    try:
        create_user(username, email, password_hash)
    except DuplicateUserError:
        print(
            "That username or email is already registered. Choose a different one.",
            file=sys.stderr,
        )
        return 1
    except errors.UndefinedTable:
        print(
            "The database tables are missing. Apply database/schema.sql in the Neon SQL Editor, then retry.",
            file=sys.stderr,
        )
        return 1
    except OperationalError:
        print(
            "Could not connect to PostgreSQL. Check DATABASE_URL and the database's access settings.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        # Database exception details can contain connection information.
        print(
            f"Could not create the demo user ({type(exc).__name__}); details were hidden.",
            file=sys.stderr,
        )
        return 1

    print(f"Demo user {username!r} created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
