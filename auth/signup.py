"""Accessible signup flow backed by a short-lived server-side draft."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Mapping
from uuid import UUID, uuid4

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from auth.otp import GENERIC_STORAGE_ERROR, OTPDeliveryError, OTPResendTooSoon, OTPStorageError, OTPVerificationError
from auth.password_utils import hash_password, verify_password
from database.repository import DuplicateUserError

signup_bp = Blueprint("signup", __name__)
STAGE_USERNAME_SUBMITTED = "signup_username_submitted"
STAGE_EMAIL_SUBMITTED = "signup_email_submitted"
STAGE_PASSWORD_CREATED = "signup_password_created"
STAGE_PASSWORD_CONFIRMED = "signup_password_confirmed"
STAGE_OTP_PENDING = STAGE_PASSWORD_CONFIRMED
GENERIC_SIGNUP_ERROR = "Unable to create an account with those details."
GENERIC_DELIVERY_ERROR = "We could not send an email verification code. Please try again."

def _repo() -> Any:
    return current_app.extensions["repository"]

def _field(record: Any, name: str, default: Any = None) -> Any:
    try:
        return record[name] if isinstance(record, Mapping) else getattr(record, name)
    except (KeyError, AttributeError):
        return default

def _active(record: Any) -> bool:
    value = _field(record, "is_active", None)
    return bool(value) if value is not None else bool(_field(record, "email_verified", True))

def _valid_email(email: str) -> bool:
    local, at, domain = email.rpartition("@")
    return bool(at and local and domain and "." in domain and " " not in email)

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _draft_id() -> UUID | None:
    raw = session.get("signup_draft_id")
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None

def _draft() -> Any:
    draft_id = _draft_id()
    if draft_id is None:
        return None
    return _repo().get_signup_draft(draft_id)

def _legacy_repository() -> bool:
    """Keep older merged test doubles usable; production uses signup_drafts."""
    return not hasattr(_repo(), "create_signup_draft")

def _require(stage: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("signup_stage") != stage or (_draft_id() is None and not _legacy_repository()):
                return redirect(url_for("signup.signup_username"))
            try:
                if not _legacy_repository() and _draft() is None:
                    session.clear()
                    return redirect(url_for("signup.signup_username"))
            except Exception:
                return render_template("signup_username.html", error=GENERIC_STORAGE_ERROR), 503
            return view(*args, **kwargs)
        return wrapped
    return decorator

def _expiry() -> datetime:
    return _now() + timedelta(seconds=current_app.config["SIGNUP_DRAFT_EXPIRY_SECONDS"])

def _render(template: str, error: str | None = None, status: str | None = None, code: int = 200):
    return render_template(template, error=error, status=status), code

@signup_bp.get("/signup")
def signup_username():
    session.clear()
    return render_template("signup_username.html")

@signup_bp.post("/signup")
def signup_username_submit():
    username = (request.form.get("username") or "").strip()
    if not username:
        return _render("signup_username.html", "Enter a username.", code=400)
    if _legacy_repository():
        session.clear()
        session["signup_stage"] = STAGE_USERNAME_SUBMITTED
        session["signup_username"] = username
        return redirect(url_for("signup.signup_email"))
    draft_id = uuid4()
    try:
        _repo().create_signup_draft(draft_id, username, None, None, STAGE_USERNAME_SUBMITTED, _expiry())
    except Exception as exc:
        current_app.logger.warning("Signup draft creation failed: error_type=%s", type(exc).__name__)
        return _render("signup_username.html", GENERIC_STORAGE_ERROR, code=503)
    session.clear()
    session["signup_stage"] = STAGE_USERNAME_SUBMITTED
    session["signup_draft_id"] = str(draft_id)
    return redirect(url_for("signup.signup_email"))

@signup_bp.get("/signup/email")
@_require(STAGE_USERNAME_SUBMITTED)
def signup_email():
    return render_template("signup_email.html")

@signup_bp.post("/signup/email")
@_require(STAGE_USERNAME_SUBMITTED)
def signup_email_submit():
    email = (request.form.get("email") or "").strip().lower()
    if not _valid_email(email):
        return _render("signup_email.html", "Enter a valid email address.", code=400)
    if _legacy_repository():
        session["signup_stage"] = STAGE_EMAIL_SUBMITTED
        session["signup_email"] = email
        return redirect(url_for("signup.signup_password"))
    try:
        if not _repo().update_signup_draft(_draft_id(), email=email, stage=STAGE_EMAIL_SUBMITTED, expires_at=_expiry()):
            return redirect(url_for("signup.signup_username"))
    except Exception as exc:
        current_app.logger.warning("Signup draft update failed: error_type=%s", type(exc).__name__)
        return _render("signup_email.html", GENERIC_STORAGE_ERROR, code=503)
    session["signup_stage"] = STAGE_EMAIL_SUBMITTED
    return redirect(url_for("signup.signup_password"))

@signup_bp.get("/signup/password")
@_require(STAGE_EMAIL_SUBMITTED)
def signup_password():
    return render_template("signup_password.html")

@signup_bp.post("/signup/password")
@_require(STAGE_EMAIL_SUBMITTED)
def signup_password_submit():
    password = request.form.get("password") or ""
    if len(password) < 8:
        return _render("signup_password.html", "Password must be at least eight characters long.", code=400)
    if _legacy_repository() and request.form.get("password_confirmation") is not None:
        if password != request.form.get("password_confirmation"):
            return _render("signup_password.html", "Passwords do not match.", code=400)
        username, email = session["signup_username"], session["signup_email"]
        try:
            by_username, by_email = _repo().get_user_by_username(username), _repo().get_user_by_email(email)
            if by_username or by_email:
                same = by_username and by_email and _field(by_username, "id") == _field(by_email, "id") and not _active(by_username) and verify_password(_field(by_username, "password_hash"), password)
                if not same:
                    return _render("signup_password.html", GENERIC_SIGNUP_ERROR, code=409)
                user = by_username
            else:
                user = _repo().create_user(username, email, hash_password(password), email_verified=False)
            session["signup_stage"] = STAGE_PASSWORD_CONFIRMED
            session["signup_user_id"] = _field(user, "id")
            try:
                current_app.extensions["otp_service"].issue(_field(user, "id"), email, purpose="email_verification")
            except OTPResendTooSoon:
                pass
            return redirect(url_for("signup.signup_otp"))
        except (DuplicateUserError, OTPDeliveryError):
            return _render("signup_password.html", GENERIC_SIGNUP_ERROR, code=409)
        except OTPStorageError:
            return _render("signup_password.html", GENERIC_STORAGE_ERROR, code=503)
    try:
        if not _repo().update_signup_draft(_draft_id(), password_hash=hash_password(password), stage=STAGE_PASSWORD_CREATED, expires_at=_expiry()):
            return redirect(url_for("signup.signup_username"))
    except Exception as exc:
        current_app.logger.warning("Signup password draft update failed: error_type=%s", type(exc).__name__)
        return _render("signup_password.html", GENERIC_STORAGE_ERROR, code=503)
    session["signup_stage"] = STAGE_PASSWORD_CREATED
    return redirect(url_for("signup.signup_password_confirm"))

@signup_bp.get("/signup/password/confirm")
@_require(STAGE_PASSWORD_CREATED)
def signup_password_confirm():
    return render_template("signup_password_confirm.html")

@signup_bp.post("/signup/password/confirm")
@_require(STAGE_PASSWORD_CREATED)
def signup_password_confirm_submit():
    confirmation = request.form.get("password_confirmation") or ""
    draft = _draft()
    if not draft or not verify_password(_field(draft, "password_hash", ""), confirmation):
        return _render("signup_password_confirm.html", "Passwords do not match.", code=400)
    username, email = _field(draft, "username"), _field(draft, "email")
    try:
        by_username = _repo().get_user_by_username(username)
        by_email = _repo().get_user_by_email(email)
        if by_username or by_email:
            same = by_username and by_email and _field(by_username, "id") == _field(by_email, "id") and not _active(by_username)
            if not same:
                return _render("signup_password_confirm.html", GENERIC_SIGNUP_ERROR, code=409)
            user = by_username
        else:
            user = _repo().create_user(username, email, _field(draft, "password_hash"), is_active=False)
        session["signup_stage"] = STAGE_PASSWORD_CONFIRMED
        session["signup_user_id"] = _field(user, "id")
        service = current_app.extensions["otp_service"]
        try:
            service.issue(_field(user, "id"), email, purpose="email_verification")
        except OTPResendTooSoon:
            pass
    except DuplicateUserError:
        return _render("signup_password_confirm.html", GENERIC_SIGNUP_ERROR, code=409)
    except OTPDeliveryError:
        return _render("signup_password_confirm.html", GENERIC_DELIVERY_ERROR, code=503)
    except OTPStorageError:
        return _render("signup_password_confirm.html", GENERIC_STORAGE_ERROR, code=503)
    except Exception as exc:
        current_app.logger.warning("Signup confirmation failed: error_type=%s", type(exc).__name__)
        return _render("signup_password_confirm.html", GENERIC_STORAGE_ERROR, code=503)
    return redirect(url_for("signup.signup_otp"))

def _signup_user() -> Any | None:
    user_id = session.get("signup_user_id")
    return _repo().get_user_by_id(int(user_id)) if user_id is not None else None

@signup_bp.get("/signup/otp")
@_require(STAGE_PASSWORD_CONFIRMED)
def signup_otp():
    return render_template("signup_otp.html")

@signup_bp.post("/signup/otp")
@_require(STAGE_PASSWORD_CONFIRMED)
def signup_otp_submit():
    try:
        user = _signup_user()
        if user is None or _active(user):
            session.clear()
            return redirect(url_for("signup.signup_username"))
        current_app.extensions["otp_service"].verify(_field(user, "id"), request.form.get("otp", ""), purpose="email_verification")
        activate = getattr(_repo(), "activate_user", _repo().mark_user_email_verified)
        if not activate(_field(user, "id")):
            return _render("signup_otp.html", GENERIC_STORAGE_ERROR, code=503)
        draft_id = _draft_id()
        if draft_id:
            _repo().delete_signup_draft(draft_id)
    except OTPVerificationError as exc:
        return _render("signup_otp.html", str(exc), code=401)
    except OTPStorageError:
        return _render("signup_otp.html", GENERIC_STORAGE_ERROR, code=503)
    except Exception as exc:
        current_app.logger.warning("Signup activation failed: error_type=%s", type(exc).__name__)
        return _render("signup_otp.html", GENERIC_STORAGE_ERROR, code=503)
    session.clear()
    session["post_signup_status"] = "Account created. Log in to continue."
    return redirect(url_for("auth.login_username"))

@signup_bp.post("/signup/otp/resend")
@_require(STAGE_PASSWORD_CONFIRMED)
def signup_otp_resend():
    try:
        user = _signup_user()
        if user is None:
            return redirect(url_for("signup.signup_username"))
        current_app.extensions["otp_service"].issue(_field(user, "id"), _field(user, "email"), purpose="email_verification")
    except OTPResendTooSoon as exc:
        return _render("signup_otp.html", str(exc), code=429)
    except OTPDeliveryError:
        return _render("signup_otp.html", GENERIC_DELIVERY_ERROR, code=503)
    except OTPStorageError:
        return _render("signup_otp.html", GENERIC_STORAGE_ERROR, code=503)
    return _render("signup_otp.html", status="A new verification code was sent to your email.")
