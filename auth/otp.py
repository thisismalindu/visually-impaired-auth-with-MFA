"""Secure email OTP generation, delivery, and verification.

The repository object passed to :class:`OTPService` is intentionally small. It
is implemented by the database member and can be replaced with a fake in tests.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol

import resend


logger = logging.getLogger(__name__)

GENERIC_STORAGE_ERROR = "Sign-in is temporarily unavailable. Please try again."


class OTPRepository(Protocol):
    def invalidate_active_otp_challenges(self, user_id: int, purpose: str = "sign_in") -> None: ...
    def create_otp_challenge(self, user_id: int, otp_hash: str, expires_at: datetime, sent_at: datetime, purpose: str = "sign_in") -> Any: ...
    def get_active_otp_challenge(self, user_id: int, purpose: str = "sign_in") -> Any | None: ...
    def increment_otp_attempts(self, challenge_id: int) -> None: ...
    def mark_otp_used(self, challenge_id: int) -> bool: ...


class OTPEmailSender(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class OTPSettings:
    secret_key: str
    application_name: str = "Accessible MFA"
    lifetime_seconds: int = 300
    max_attempts: int = 5
    resend_cooldown_seconds: int = 60


class OTPError(Exception):
    """Base class for expected OTP flow failures."""


class OTPResendTooSoon(OTPError):
    """A new challenge was requested before the cooldown elapsed."""


class OTPDeliveryError(OTPError):
    """The email provider did not accept the message."""


class OTPStorageError(OTPError):
    """OTP persistence is unavailable or failed."""


class OTPVerificationError(OTPError):
    """The submitted code cannot authenticate the current user."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _field(challenge: Any, name: str) -> Any:
    if isinstance(challenge, Mapping):
        return challenge[name]
    return getattr(challenge, name)


class OTPService:
    """Own the security decisions for an email OTP challenge."""

    def __init__(self, repository: OTPRepository, email_sender: OTPEmailSender, settings: OTPSettings, clock: Callable[[], datetime] = _utc_now) -> None:
        if not settings.secret_key:
            raise ValueError("OTP secret key must not be empty")
        self.repository = repository
        self.email_sender = email_sender
        self.settings = settings
        self.clock = clock

    def _digest(self, otp: str) -> str:
        return hmac.new(self.settings.secret_key.encode("utf-8"), otp.encode("ascii"), hashlib.sha256).hexdigest()

    def _new_otp(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _storage_call(self, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run one repository operation without exposing database details."""
        try:
            return operation(*args, **kwargs)
        except Exception as exc:
            if isinstance(exc, TypeError):
                # Allows older test doubles and merged modules to omit the
                # optional purpose argument while the real repository remains
                # purpose-bound.
                raise
            logger.warning(
                "OTP storage operation failed: operation=%s error_type=%s",
                getattr(operation, "__name__", "unknown"),
                type(exc).__name__,
            )
            raise OTPStorageError("OTP storage failed") from exc

    def issue(self, user_id: int, recipient: str, purpose: str = "sign_in") -> None:
        """Persist a hashed challenge, then send its plaintext code by email."""
        if purpose not in {"sign_in", "email_verification"}:
            raise ValueError("Unsupported OTP purpose")
        now = _as_utc(self.clock())
        try:
            active = self._storage_call(self.repository.get_active_otp_challenge, user_id, purpose)
        except TypeError:
            active = self._storage_call(self.repository.get_active_otp_challenge, user_id)
        if active is not None:
            sent_at = _as_utc(_field(active, "sent_at"))
            if (now - sent_at).total_seconds() < self.settings.resend_cooldown_seconds:
                raise OTPResendTooSoon("Please wait before requesting another code.")

        otp = self._new_otp()
        if purpose == "email_verification":
            subject = f"Verify your {self.settings.application_name} email"
            body = (
                f"Your {self.settings.application_name} email verification code is: {otp}.\n"
                f"It expires in {self.settings.lifetime_seconds // 60} minutes.\n"
                "If you did not create an account, you can ignore this email."
            )
        else:
            subject = f"Your {self.settings.application_name} OTP"
            body = (
                f"Your {self.settings.application_name} OTP is: {otp}.\n"
                f"It expires in {self.settings.lifetime_seconds // 60} minutes.\n"
                "If you did not attempt to sign in, you can ignore this email."
            )

        # The usable challenge must exist before an email can be delivered.
        # Only the HMAC digest is stored; the six-digit code stays in memory.
        try:
            self._storage_call(self.repository.invalidate_active_otp_challenges, user_id, purpose)
        except TypeError:
            self._storage_call(self.repository.invalidate_active_otp_challenges, user_id)
        try:
            challenge = self._storage_call(
                self.repository.create_otp_challenge,
                user_id=user_id, otp_hash=self._digest(otp),
                expires_at=now + timedelta(seconds=self.settings.lifetime_seconds),
                sent_at=now, purpose=purpose,
            )
        except TypeError:
            challenge = self._storage_call(
                self.repository.create_otp_challenge,
                user_id=user_id, otp_hash=self._digest(otp),
                expires_at=now + timedelta(seconds=self.settings.lifetime_seconds),
                sent_at=now,
            )
        if challenge is None:
            raise OTPStorageError("OTP storage returned no challenge")

        try:
            self.email_sender.send(recipient, subject, body)
        except Exception as exc:
            # A failed delivery must not leave an active authentication code.
            try:
                self._storage_call(
                    self.repository.mark_otp_used,
                    int(_field(challenge, "id")),
                )
            except OTPStorageError:
                logger.error(
                    "Could not invalidate OTP after delivery failure: error_type=OTPStorageError"
                )
            if isinstance(exc, OTPDeliveryError):
                raise
            raise OTPDeliveryError("OTP delivery failed") from exc

    def verify(self, user_id: int, submitted_otp: str, purpose: str = "sign_in") -> bool:
        """Verify once, consuming the challenge after a successful comparison."""
        try:
            challenge = self._storage_call(self.repository.get_active_otp_challenge, user_id, purpose)
        except TypeError:
            challenge = self._storage_call(self.repository.get_active_otp_challenge, user_id)
        if challenge is None:
            raise OTPVerificationError("The code is incorrect or expired. Try again.")

        attempts = int(_field(challenge, "failed_attempts"))
        if attempts >= self.settings.max_attempts:
            raise OTPVerificationError("The code is incorrect or expired. Try again.")

        if _as_utc(_field(challenge, "expires_at")) <= _as_utc(self.clock()):
            raise OTPVerificationError("The code is incorrect or expired. Try again.")

        if not isinstance(submitted_otp, str) or not submitted_otp.isdigit() or len(submitted_otp) != 6:
            self._storage_call(
                self.repository.increment_otp_attempts,
                int(_field(challenge, "id")),
            )
            raise OTPVerificationError("The code is incorrect or expired. Try again.")

        expected = str(_field(challenge, "otp_hash"))
        if not hmac.compare_digest(self._digest(submitted_otp), expected):
            self._storage_call(
                self.repository.increment_otp_attempts,
                int(_field(challenge, "id")),
            )
            raise OTPVerificationError("The code is incorrect or expired. Try again.")

        if not self._storage_call(
            self.repository.mark_otp_used,
            int(_field(challenge, "id")),
        ):
            raise OTPVerificationError("The code is incorrect or expired. Try again.")
        return True


class ResendEmailSender:
    """Resend SDK adapter that preserves the application's sender contract."""

    def __init__(
        self,
        api_key: str,
        from_email: str,
        send_email: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.send_email = send_email or resend.Emails.send

    def send(self, recipient: str, subject: str, body: str) -> None:
        # The SDK applies its standard User-Agent and Authorization headers.
        resend.api_key = self.api_key
        try:
            self.send_email(
                {
                    "from": self.from_email,
                    "to": [recipient],
                    "subject": subject,
                    "text": body,
                }
            )
        except Exception as exc:
            status_code = getattr(exc, "status_code", getattr(exc, "code", "unknown"))
            logger.warning(
                "Resend delivery failed: error_type=%s status=%s",
                type(exc).__name__,
                status_code,
            )
            raise OTPDeliveryError("OTP delivery failed") from exc


def create_otp_blueprint(service: OTPService, repository: Any, template_name: str = "otp.html") -> Any:
    """Create OTP routes using the shared ``auth_stage`` and ``user_id`` session keys."""
    from flask import Blueprint, redirect, render_template, request, session, url_for

    from auth.flow import (
        STAGE_PASSWORD_VERIFIED,
        mark_authenticated,
        require_stage,
    )

    blueprint = Blueprint("otp", __name__)

    def user_value(user: Any, name: str) -> Any:
        return user[name] if isinstance(user, Mapping) else getattr(user, name)

    def current_user() -> Any | None:
        user_id = session.get("user_id")
        if user_id is None:
            return None
        try:
            return repository.get_user_by_id(int(user_id))
        except Exception as exc:
            logger.warning(
                "User lookup failed during OTP flow: error_type=%s",
                type(exc).__name__,
            )
            raise OTPStorageError("User lookup failed") from exc

    def require_existing_user() -> Any | None:
        user = current_user()
        if user is None:
            session.clear()
        return user

    @blueprint.get("/login/otp")
    @require_stage(STAGE_PASSWORD_VERIFIED)
    def otp_page() -> Any:
        try:
            user = require_existing_user()
        except OTPStorageError:
            return render_template(template_name, error=GENERIC_STORAGE_ERROR), 503
        if user is None:
            return redirect(url_for("auth.login_username"))
        return render_template(template_name)

    @blueprint.post("/login/otp")
    @require_stage(STAGE_PASSWORD_VERIFIED)
    def verify_otp() -> Any:
        try:
            user = require_existing_user()
        except OTPStorageError:
            return render_template(template_name, error=GENERIC_STORAGE_ERROR), 503
        if user is None:
            return redirect(url_for("auth.login_username"))
        try:
            service.verify(int(session["user_id"]), request.form.get("otp", ""), purpose="sign_in")
        except OTPStorageError:
            return render_template(template_name, error=GENERIC_STORAGE_ERROR), 503
        except OTPVerificationError as exc:
            return render_template(template_name, error=str(exc)), 401
        mark_authenticated()
        return redirect(url_for("auth.welcome"))

    @blueprint.post("/login/otp/resend")
    @require_stage(STAGE_PASSWORD_VERIFIED)
    def resend_otp() -> Any:
        try:
            user = require_existing_user()
        except OTPStorageError:
            return render_template(template_name, error=GENERIC_STORAGE_ERROR), 503
        if user is None:
            return redirect(url_for("auth.login_username"))
        try:
            service.issue(int(session["user_id"]), str(user_value(user, "email")))
        except OTPResendTooSoon as exc:
            return render_template(template_name, error=str(exc)), 429
        except OTPStorageError:
            return render_template(template_name, error=GENERIC_STORAGE_ERROR), 503
        except OTPDeliveryError:
            return render_template(
                template_name,
                error="We could not send a new code. Please try again later.",
            ), 503
        return render_template(template_name, status="A new code was sent to your email.")

    return blueprint
