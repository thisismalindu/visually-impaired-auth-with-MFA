"""Secure email OTP generation, delivery, and verification.

The repository object passed to :class:`OTPService` is intentionally small. It
is implemented by the database member and can be replaced with a fake in tests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol


class OTPRepository(Protocol):
    def invalidate_active_otp_challenges(self, user_id: int) -> None: ...
    def create_otp_challenge(self, user_id: int, otp_hash: str, expires_at: datetime, sent_at: datetime) -> Any: ...
    def get_active_otp_challenge(self, user_id: int) -> Any | None: ...
    def increment_otp_attempts(self, challenge_id: int) -> None: ...
    def mark_otp_used(self, challenge_id: int) -> None: ...


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

    def issue(self, user_id: int, recipient: str) -> None:
        """Generate, email, and persist one challenge without persisting its code."""
        now = _as_utc(self.clock())
        active = self.repository.get_active_otp_challenge(user_id)
        if active is not None:
            sent_at = _as_utc(_field(active, "sent_at"))
            if (now - sent_at).total_seconds() < self.settings.resend_cooldown_seconds:
                raise OTPResendTooSoon("Please wait before requesting another code.")

        otp = self._new_otp()
        body = (
            f"Your {self.settings.application_name} OTP is: {otp}.\n"
            f"It expires in {self.settings.lifetime_seconds // 60} minutes.\n"
            "If you did not attempt to sign in, you can ignore this email."
        )
        subject = f"Your {self.settings.application_name} OTP"
        try:
            self.email_sender.send(recipient, subject, body)
        except Exception as exc:
            # Provider details and the OTP must never reach the user or logs.
            raise OTPDeliveryError("OTP delivery failed") from exc

        self.repository.invalidate_active_otp_challenges(user_id)
        self.repository.create_otp_challenge(
            user_id=user_id,
            otp_hash=self._digest(otp),
            expires_at=now + timedelta(seconds=self.settings.lifetime_seconds),
            sent_at=now,
        )

    def verify(self, user_id: int, submitted_otp: str) -> bool:
        """Verify once, consuming the challenge after a successful comparison."""
        challenge = self.repository.get_active_otp_challenge(user_id)
        if challenge is None:
            raise OTPVerificationError("The code is invalid or expired.")

        attempts = int(_field(challenge, "failed_attempts"))
        if attempts >= self.settings.max_attempts:
            raise OTPVerificationError("The code is invalid or expired.")

        if _as_utc(_field(challenge, "expires_at")) <= _as_utc(self.clock()):
            raise OTPVerificationError("The code is invalid or expired.")

        if not isinstance(submitted_otp, str) or not submitted_otp.isdigit() or len(submitted_otp) != 6:
            self.repository.increment_otp_attempts(int(_field(challenge, "id")))
            raise OTPVerificationError("The code is invalid or expired.")

        expected = str(_field(challenge, "otp_hash"))
        if not hmac.compare_digest(self._digest(submitted_otp), expected):
            self.repository.increment_otp_attempts(int(_field(challenge, "id")))
            raise OTPVerificationError("The code is invalid or expired.")

        self.repository.mark_otp_used(int(_field(challenge, "id")))
        return True


class ResendEmailSender:
    """Minimal Resend API client using only the Python standard library."""

    endpoint = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str, opener: Any = urllib.request.urlopen) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.opener = opener

    def send(self, recipient: str, subject: str, body: str) -> None:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"from": self.from_email, "to": [recipient], "subject": subject, "text": body}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    raise OTPDeliveryError("OTP delivery failed")
        except (urllib.error.URLError, TimeoutError, OTPDeliveryError) as exc:
            raise OTPDeliveryError("OTP delivery failed") from exc


def create_otp_blueprint(service: OTPService, repository: Any, template_name: str = "otp.html") -> Any:
    """Create OTP routes using the shared ``auth_stage`` and ``user_id`` session keys."""
    from flask import Blueprint, flash, redirect, render_template, request, session, url_for

    blueprint = Blueprint("otp", __name__)

    def user_value(user: Any, name: str) -> Any:
        return user[name] if isinstance(user, Mapping) else getattr(user, name)

    def password_verified() -> bool:
        return session.get("auth_stage") == "password_verified" and session.get("user_id") is not None

    @blueprint.get("/login/otp")
    def otp_page() -> Any:
        if not password_verified():
            return redirect(url_for("login_password"))
        return render_template(template_name)

    @blueprint.post("/login/otp")
    def verify_otp() -> Any:
        if not password_verified():
            return redirect(url_for("login_password"))
        try:
            service.verify(int(session["user_id"]), request.form.get("otp", ""))
        except OTPVerificationError as exc:
            flash(str(exc), "error")
            return render_template(template_name), 401
        session["auth_stage"] = "authenticated"
        return redirect(url_for("welcome"))

    @blueprint.post("/login/otp/resend")
    def resend_otp() -> Any:
        if not password_verified():
            return redirect(url_for("login_password"))
        user = repository.get_user_by_id(int(session["user_id"]))
        try:
            service.issue(int(session["user_id"]), str(user_value(user, "email")))
        except OTPResendTooSoon:
            flash("Please wait before requesting another code.", "error")
        except OTPDeliveryError:
            flash("We could not send a new code. Please try again later.", "error")
        return redirect(url_for("otp.otp_page"))

    return blueprint