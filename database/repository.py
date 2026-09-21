"""Parameterized persistence operations for users and email OTP challenges."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import errors

from database.db import connection


class DuplicateUserError(ValueError):
    """Raised when a username or email is already registered."""


def _duplicate_user_error(exc: errors.UniqueViolation) -> DuplicateUserError:
    constraint = exc.diag.constraint_name
    if constraint == "users_username_key":
        return DuplicateUserError("username is already registered")
    if constraint == "users_email_key":
        return DuplicateUserError("email is already registered")
    return DuplicateUserError("user already exists")


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, username, email, password_hash, created_at
            FROM users
            WHERE username = %s
            """,
            (username,),
        ).fetchone()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, username, email, password_hash, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()


def create_user(username: str, email: str, password_hash: str) -> dict[str, Any]:
    try:
        with connection() as conn:
            return conn.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, username, email, password_hash, created_at
                """,
                (username, email, password_hash),
            ).fetchone()
    except errors.UniqueViolation as exc:
        raise _duplicate_user_error(exc) from exc


def create_otp_challenge(
    user_id: int,
    otp_hash: str,
    expires_at: datetime,
    sent_at: datetime,
) -> dict[str, Any]:
    with connection() as conn:
        return conn.execute(
            """
            INSERT INTO otp_challenges (user_id, otp_hash, expires_at, sent_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, user_id, otp_hash, expires_at, used,
                      failed_attempts, created_at, sent_at
            """,
            (user_id, otp_hash, expires_at, sent_at),
        ).fetchone()


def get_active_otp_challenge(user_id: int) -> dict[str, Any] | None:
    """Return the newest unused, unexpired challenge for this user."""
    with connection() as conn:
        return conn.execute(
            """
            SELECT id, user_id, otp_hash, expires_at, used,
                   failed_attempts, created_at, sent_at
            FROM otp_challenges
            WHERE user_id = %s
              AND used = FALSE
              AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()


def increment_otp_attempts(challenge_id: int) -> bool:
    """Increment attempts only for an unused challenge and report if updated."""
    with connection() as conn:
        result = conn.execute(
            """
            UPDATE otp_challenges
            SET failed_attempts = failed_attempts + 1
            WHERE id = %s
              AND used = FALSE
              AND expires_at > CURRENT_TIMESTAMP
            """,
            (challenge_id,),
        )
        return result.rowcount == 1


def mark_otp_used(challenge_id: int) -> bool:
    """Mark an unused challenge as used and report whether it was changed."""
    with connection() as conn:
        result = conn.execute(
            """
            UPDATE otp_challenges
            SET used = TRUE
            WHERE id = %s
              AND used = FALSE
              AND expires_at > CURRENT_TIMESTAMP
            """,
            (challenge_id,),
        )
        return result.rowcount == 1


def invalidate_active_otp_challenges(user_id: int) -> int:
    """Invalidate all currently unused challenges belonging to one user."""
    with connection() as conn:
        result = conn.execute(
            """
            UPDATE otp_challenges
            SET used = TRUE
            WHERE user_id = %s
              AND used = FALSE
            """,
            (user_id,),
        )
        return result.rowcount
