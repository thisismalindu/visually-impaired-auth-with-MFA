"""Small, shared Argon2 password helpers for provisioning and login."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2 password hash; reject non-string or empty passwords."""

    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    return _PASSWORD_HASHER.hash(password)


def verify_password_hash(password_hash: str, password: str) -> bool:
    """Verify a supplied password without exposing hash-library exceptions."""

    if not isinstance(password_hash, str) or not isinstance(password, str):
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


# This alias is the contract used by the password-flow member.
verify_password = verify_password_hash
