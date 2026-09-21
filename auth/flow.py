"""Ordered username/password authentication flow.

Session stage contract (server-advanced only):

    None -> "username_submitted" -> "password_verified" -> "authenticated"

This module only ever advances a session as far as "password_verified".
The OTP module (Member 5) owns the transition into "authenticated" and
should do so exclusively through ``mark_authenticated`` below, and should
gate its own routes with ``require_stage(STAGE_PASSWORD_VERIFIED)`` the same
way this module gates ``/welcome`` with ``require_stage(STAGE_AUTHENTICATED)``.
Direct navigation to a route without the required prior stage redirects back
to the start of the flow instead of exposing the route.

Nothing here imports the OTP module, so importing this module from OTP code
cannot create a circular import.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from auth.otp import OTPDeliveryError, OTPResendTooSoon
from auth.password_utils import hash_password, verify_password

auth_bp = Blueprint("auth", __name__)

STAGE_USERNAME_SUBMITTED = "username_submitted"
STAGE_PASSWORD_VERIFIED = "password_verified"
STAGE_AUTHENTICATED = "authenticated"

# Deliberately reveals nothing about which of username/password was wrong,
# or whether the account exists at all.
GENERIC_LOGIN_ERROR = "Authentication failed. Check your credentials and try again."

# The OTP module's entry point. Referenced as a literal path rather than
# imported so this module has no compile-time dependency on Member 5's code.
OTP_LOGIN_PATH = "/login/otp"

# A precomputed Argon2 hash verified against every login attempt for a
# username that does not exist, so an unknown username takes about the same
# time to reject as a known one with a wrong password.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-placeholder")


def _load_repository() -> Any:
    """Import the repository lazily.

    Member 4's ``database.repository`` module may not be merged yet, and
    tests substitute a fake repository, so the import happens per call
    instead of at module load time.
    """

    try:
        from database import repository
    except ImportError:
        return None
    return repository


def _field(record: Any, name: str) -> Any:
    """Read a named field from a user record that may be a mapping or an object."""

    try:
        return record[name]
    except TypeError:
        return getattr(record, name)


def current_stage() -> str | None:
    """The current session's position in the login wizard, or ``None``."""

    return session.get("auth_stage")


def get_verified_user_id() -> Any:
    """The user ID established at the password step, for the OTP module to use.

    Only meaningful once ``current_stage()`` is at least ``STAGE_PASSWORD_VERIFIED``.
    """

    return session.get("user_id")


def mark_authenticated() -> None:
    """Advance the session to the final, fully authenticated stage.

    This is the *only* supported way to reach ``STAGE_AUTHENTICATED``. The
    OTP module should call this exclusively after it has itself confirmed a
    correct OTP; nothing in this module ever calls it.
    """

    if current_stage() != STAGE_PASSWORD_VERIFIED:
        raise RuntimeError("Cannot authenticate a session that has not verified its password")
    session["auth_stage"] = STAGE_AUTHENTICATED


def require_stage(stage: str) -> Callable:
    """Decorator that redirects to the start of the login flow unless at ``stage``.

    Exposed for the OTP module to protect ``/login/otp`` with
    ``require_stage(STAGE_PASSWORD_VERIFIED)``, mirroring how this module
    protects ``/welcome`` with ``require_stage(STAGE_AUTHENTICATED)``.
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if current_stage() != stage:
                return redirect(url_for("auth.login_username"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.get("/login")
def login_username():
    session.clear()
    return render_template("username.html")


@auth_bp.post("/login")
def login_username_submit():
    username = (request.form.get("username") or "").strip()
    if not username:
        return render_template("username.html", error="Enter your username."), 400

    session.clear()
    session["auth_stage"] = STAGE_USERNAME_SUBMITTED
    session["pending_username"] = username
    return redirect(url_for("auth.login_password"))


@auth_bp.get("/login/password")
@require_stage(STAGE_USERNAME_SUBMITTED)
def login_password():
    return render_template("password.html")


@auth_bp.post("/login/password")
@require_stage(STAGE_USERNAME_SUBMITTED)
def login_password_submit():
    submitted_password = request.form.get("password") or ""
    username = session.get("pending_username", "")

    repository = _load_repository()
    user = repository.get_user_by_username(username) if repository else None

    # Verify against a real hash when the user exists, otherwise against the
    # dummy hash, so a nonexistent username is not distinguishable by timing
    # or by a different error message. Deliberately no logging of username
    # or password here; only aggregate failure counters belong in logs, and
    # this module does not add any.
    password_hash = _field(user, "password_hash") if user else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password_hash, submitted_password)

    if not user or not password_is_valid:
        return render_template("password.html", error=GENERIC_LOGIN_ERROR), 401

    session.clear()
    user_id = _field(user, "id")
    username = _field(user, "username")
    session["auth_stage"] = STAGE_PASSWORD_VERIFIED
    session["user_id"] = user_id
    session["username"] = username

    otp_service = current_app.extensions["otp_service"]
    try:
        otp_service.issue(user_id, _field(user, "email"))
    except OTPResendTooSoon:
        # An unexpired challenge already exists; the user can enter that code.
        pass
    except OTPDeliveryError:
        session.clear()
        session["auth_stage"] = STAGE_USERNAME_SUBMITTED
        session["pending_username"] = username
        return render_template(
            "password.html",
            error="We could not send a sign-in code. Please try again.",
        ), 503

    return redirect(OTP_LOGIN_PATH)


@auth_bp.get("/welcome")
@require_stage(STAGE_AUTHENTICATED)
def welcome():
    return render_template("welcome.html", username=session.get("username"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_username"))
