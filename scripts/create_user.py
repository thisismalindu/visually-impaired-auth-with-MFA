"""Create a demo user through the shared repository.

Run with ``python -m scripts.create_user`` after Member 4's repository module
and database schema have been integrated.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from auth.password_utils import hash_password


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Argon2-backed demo user")
    parser.add_argument("--username", help="Demo username")
    parser.add_argument("--email", help="Demo user's email address")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)

    try:
        from database.repository import create_user
    except (ImportError, ModuleNotFoundError):
        print(
            "database.repository is not available yet. Merge Member 4's "
            "database module before creating demo users.",
            file=sys.stderr,
        )
        return 1

    username = args.username or input("Username: ").strip()
    email = args.email or input("Email: ").strip()
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
    except Exception:  # Repository owns database-specific error mapping/logging.
        print("Could not create demo user; the repository reported an error.", file=sys.stderr)
        return 1

    print(f"Demo user {username!r} created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
