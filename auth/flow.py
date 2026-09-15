"""Ordered username/password authentication flow.

Session stage contract (server-advanced only):

    None -> "username_submitted" -> "password_verified" -> "authenticated"

The OTP module owns the transition into "authenticated"; this module only
ever advances a session as far as "password_verified". Direct navigation to
a later route without the required prior stage redirects back to the start
of the flow instead of exposing the route.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from auth.password_utils import hash_password, verify_password

auth_bp = Blueprint("auth", __name__)

STAGE_USERNAME_SUBMITTED = "username_submitted"
STAGE_PASSWORD_VERIFIED = "password_verified"
STAGE_AUTHENTICATED = "authenticated"

_GENERIC_LOGIN_ERROR = "Incorrect username or password."

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


def _stage() -> str | None:
    return session.get("auth_stage")


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
def login_password():
    if _stage() != STAGE_USERNAME_SUBMITTED:
        return redirect(url_for("auth.login_username"))
    return render_template("password.html")


@auth_bp.post("/login/password")
def login_password_submit():
    if _stage() != STAGE_USERNAME_SUBMITTED:
        return redirect(url_for("auth.login_username"))

    submitted_password = request.form.get("password") or ""
    username = session.get("pending_username", "")

    repository = _load_repository()
    user = repository.get_user_by_username(username) if repository else None

    # Verify against a real hash when the user exists, otherwise against the
    # dummy hash, so a nonexistent username is not distinguishable by timing
    # or by a different error message.
    password_hash = _field(user, "password_hash") if user else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password_hash, submitted_password)

    if not user or not password_is_valid:
        return render_template("password.html", error=_GENERIC_LOGIN_ERROR), 401

    session.clear()
    session["auth_stage"] = STAGE_PASSWORD_VERIFIED
    session["user_id"] = _field(user, "id")
    session["username"] = _field(user, "username")
    return redirect("/login/otp")


@auth_bp.get("/welcome")
def welcome():
    if _stage() != STAGE_AUTHENTICATED:
        return redirect(url_for("auth.login_username"))
    return render_template("welcome.html", username=session.get("username"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_username"))
