"""Environment-backed application configuration.

Secrets intentionally have no fallback values. Test callers can provide an
explicit test secret through ``create_app`` without putting credentials in the
repository.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when the application cannot start with safe configuration."""


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer setting without exposing its value in errors."""

    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def load_config() -> dict[str, Any]:
    """Load application settings from environment variables and ``.env``."""

    load_dotenv()
    return {
        # No development fallback is provided for secrets or credentials.
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "RESEND_API_KEY": os.getenv("RESEND_API_KEY"),
        "RESEND_FROM_EMAIL": os.getenv("RESEND_FROM_EMAIL"),
        "APP_NAME": os.getenv("APP_NAME", "Accessible MFA"),
        "OTP_EXPIRY_SECONDS": _positive_int("OTP_EXPIRY_SECONDS", 300),
        "OTP_MAX_ATTEMPTS": _positive_int("OTP_MAX_ATTEMPTS", 5),
        "OTP_RESEND_COOLDOWN_SECONDS": _positive_int(
            "OTP_RESEND_COOLDOWN_SECONDS", 60
        ),
    }


def validate_required_config(config: Mapping[str, Any]) -> None:
    """Validate settings required for a non-test application startup.

    Values are checked for presence only; secret contents are never included in
    the exception text.
    """

    required_names = (
        "SECRET_KEY",
        "DATABASE_URL",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
    )
    missing = [name for name in required_names if not config.get(name)]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(
            f"Missing required environment configuration: {names}. "
            "Copy .env.example to .env and set the values."
        )
