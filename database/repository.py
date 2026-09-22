"""Small, parameterized PostgreSQL repository used by authentication flows."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID
from psycopg import errors
from database.db import connection

class DuplicateUserError(ValueError):
    """Raised when a username or email is already registered."""

class DuplicateDraftError(ValueError):
    """Raised when a signup draft conflicts with an existing draft."""

def _duplicate_user_error(exc: errors.UniqueViolation) -> DuplicateUserError:
    constraint = exc.diag.constraint_name
    if constraint == "users_username_key":
        return DuplicateUserError("username is already registered")
    if constraint == "users_email_key":
        return DuplicateUserError("email is already registered")
    return DuplicateUserError("user already exists")

_USER_COLUMNS = "id, username, email, password_hash, is_active, email_verified, created_at"

def get_user_by_username(username: str) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE username = %s", (username,)).fetchone()

def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()

def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE email = %s", (email,)).fetchone()

def create_user(username: str, email: str, password_hash: str, email_verified: bool = False, *, is_active: bool | None = None) -> dict[str, Any]:
    active = email_verified if is_active is None else is_active
    try:
        with connection() as conn:
            return conn.execute(
                f"INSERT INTO users (username, email, password_hash, is_active, email_verified) VALUES (%s, %s, %s, %s, %s) RETURNING {_USER_COLUMNS}",
                (username, email, password_hash, active, active),
            ).fetchone()
    except errors.UniqueViolation as exc:
        raise _duplicate_user_error(exc) from exc

def mark_user_email_verified(user_id: int) -> bool:
    return activate_user(user_id)

def activate_user(user_id: int) -> bool:
    with connection() as conn:
        result = conn.execute(
            "UPDATE users SET is_active = TRUE, email_verified = TRUE WHERE id = %s AND is_active = FALSE",
            (user_id,),
        )
        return result.rowcount == 1

def create_signup_draft(draft_id: UUID, username: str, email: str, password_hash: str, stage: str, expires_at: datetime) -> dict[str, Any]:
    try:
        with connection() as conn:
            return conn.execute(
                "INSERT INTO signup_drafts (id, username, email, password_hash, stage, expires_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, username, email, password_hash, stage, created_at, updated_at, expires_at",
                (draft_id, username, email, password_hash, stage, expires_at),
            ).fetchone()
    except errors.UniqueViolation as exc:
        raise DuplicateDraftError("signup draft already exists") from exc

def get_signup_draft(draft_id: UUID) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            "SELECT id, username, email, password_hash, stage, created_at, updated_at, expires_at FROM signup_drafts WHERE id = %s AND expires_at > CURRENT_TIMESTAMP",
            (draft_id,),
        ).fetchone()

def update_signup_draft(draft_id: UUID, *, stage: str | None = None, username: str | None = None, email: str | None = None, password_hash: str | None = None, expires_at: datetime | None = None) -> bool:
    fields = ["updated_at = CURRENT_TIMESTAMP"]
    values: list[Any] = []
    if stage is not None:
        fields.append("stage = %s")
        values.append(stage)
    if username is not None:
        fields.append("username = %s")
        values.append(username)
    if email is not None:
        fields.append("email = %s")
        values.append(email)
    if password_hash is not None:
        fields.append("password_hash = %s")
        values.append(password_hash)
    if expires_at is not None:
        fields.append("expires_at = %s")
        values.append(expires_at)
    values.append(draft_id)
    with connection() as conn:
        result = conn.execute(f"UPDATE signup_drafts SET {', '.join(fields)} WHERE id = %s AND expires_at > CURRENT_TIMESTAMP", tuple(values))
        return result.rowcount == 1

def delete_signup_draft(draft_id: UUID) -> bool:
    with connection() as conn:
        result = conn.execute("DELETE FROM signup_drafts WHERE id = %s", (draft_id,))
        return result.rowcount == 1

def cleanup_expired_signup_drafts() -> int:
    with connection() as conn:
        return conn.execute("DELETE FROM signup_drafts WHERE expires_at <= CURRENT_TIMESTAMP").rowcount

def create_otp_challenge(user_id: int, otp_hash: str, expires_at: datetime, sent_at: datetime, purpose: str = "sign_in") -> dict[str, Any]:
    with connection() as conn:
        return conn.execute(
            "INSERT INTO otp_challenges (user_id, purpose, otp_hash, expires_at, sent_at) VALUES (%s, %s, %s, %s, %s) RETURNING id, user_id, purpose, otp_hash, expires_at, used, failed_attempts, created_at, sent_at",
            (user_id, purpose, otp_hash, expires_at, sent_at),
        ).fetchone()

def get_active_otp_challenge(user_id: int, purpose: str = "sign_in") -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            "SELECT id, user_id, purpose, otp_hash, expires_at, used, failed_attempts, created_at, sent_at FROM otp_challenges WHERE user_id = %s AND purpose = %s AND used = FALSE AND expires_at > CURRENT_TIMESTAMP ORDER BY created_at DESC LIMIT 1",
            (user_id, purpose),
        ).fetchone()

def increment_otp_attempts(challenge_id: int) -> bool:
    with connection() as conn:
        result = conn.execute("UPDATE otp_challenges SET failed_attempts = failed_attempts + 1 WHERE id = %s AND used = FALSE AND expires_at > CURRENT_TIMESTAMP", (challenge_id,))
        return result.rowcount == 1

def mark_otp_used(challenge_id: int) -> bool:
    with connection() as conn:
        result = conn.execute("UPDATE otp_challenges SET used = TRUE WHERE id = %s AND used = FALSE AND expires_at > CURRENT_TIMESTAMP", (challenge_id,))
        return result.rowcount == 1

def invalidate_active_otp_challenges(user_id: int, purpose: str = "sign_in") -> int:
    with connection() as conn:
        result = conn.execute("UPDATE otp_challenges SET used = TRUE WHERE user_id = %s AND purpose = %s AND used = FALSE", (user_id, purpose))
        return result.rowcount
