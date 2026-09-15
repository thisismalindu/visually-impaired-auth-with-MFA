"""Tests for the username/password flow and its session-stage ordering.

Templates (Member 2) and the database repository (Member 4) are not merged
yet, so this module is tested against a stub template renderer and a fake
repository rather than the real integrations.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flask import session as flask_session

import auth.flow as flow
from auth.password_utils import hash_password


class FakeRepository:
    def __init__(self, users):
        self._users_by_name = {user["username"]: user for user in users}

    def get_user_by_username(self, username):
        return self._users_by_name.get(username)


def _stub_render_template(monkeypatch):
    """Replace render_template with a marker so tests don't need real templates."""

    calls = []

    def fake_render_template(template_name, **context):
        calls.append((template_name, context))
        return f"rendered:{template_name}"

    monkeypatch.setattr(flow, "render_template", fake_render_template)
    return calls


def _make_app(monkeypatch, repository=None):
    render_calls = _stub_render_template(monkeypatch)
    monkeypatch.setattr(flow, "_load_repository", lambda: repository)

    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
    app.register_blueprint(flow.auth_bp)
    app.render_calls = render_calls
    return app


def test_login_get_renders_username_page(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    response = client.get("/login")

    assert response.status_code == 200
    assert response.data == b"rendered:username.html"


def test_empty_username_is_rejected_without_advancing_stage(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    response = client.post("/login", data={"username": "  "})

    assert response.status_code == 400
    with client.session_transaction() as test_session:
        assert "auth_stage" not in test_session


def test_username_submission_advances_stage_and_redirects(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    response = client.post("/login", data={"username": "alice"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/login/password"
    with client.session_transaction() as test_session:
        assert test_session["auth_stage"] == flow.STAGE_USERNAME_SUBMITTED
        assert test_session["pending_username"] == "alice"


def test_password_page_redirects_without_prior_username_stage(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    response = client.get("/login/password")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_password_page_accessible_after_username_stage(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    client.post("/login", data={"username": "alice"})

    response = client.get("/login/password")

    assert response.status_code == 200
    assert response.data == b"rendered:password.html"


def test_correct_password_advances_to_password_verified_and_redirects_to_otp(monkeypatch):
    repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()
    client.post("/login", data={"username": "alice"})

    response = client.post("/login/password", data={"password": "correct-horse"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/login/otp"
    with client.session_transaction() as test_session:
        assert test_session["auth_stage"] == flow.STAGE_PASSWORD_VERIFIED
        assert test_session["user_id"] == 1
        assert test_session["username"] == "alice"
        assert "pending_username" not in test_session


def test_wrong_password_is_rejected_with_generic_error(monkeypatch):
    repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()
    client.post("/login", data={"username": "alice"})

    response = client.post("/login/password", data={"password": "wrong-password"})

    assert response.status_code == 401
    assert response.data == b"rendered:password.html"
    with client.session_transaction() as test_session:
        assert test_session["auth_stage"] == flow.STAGE_USERNAME_SUBMITTED


def test_unknown_username_gets_the_same_generic_error_as_wrong_password(monkeypatch):
    repository = FakeRepository([])
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()
    client.post("/login", data={"username": "nobody"})

    response = client.post("/login/password", data={"password": "anything"})

    assert response.status_code == 401
    assert response.data == b"rendered:password.html"


def test_password_step_bypass_via_direct_navigation_is_blocked(monkeypatch):
    repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()

    response = client.post("/login/password", data={"password": "correct-horse"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_wrong_password_error_message_matches_unknown_username_error_message(monkeypatch):
    known_repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    unknown_repository = FakeRepository([])

    wrong_password_app = _make_app(monkeypatch, repository=known_repository)
    client = wrong_password_app.test_client()
    client.post("/login", data={"username": "alice"})
    wrong_password_response = client.post("/login/password", data={"password": "wrong-password"})

    unknown_user_app = _make_app(monkeypatch, repository=unknown_repository)
    client = unknown_user_app.test_client()
    client.post("/login", data={"username": "nobody"})
    unknown_user_response = client.post("/login/password", data={"password": "anything"})

    assert wrong_password_response.status_code == unknown_user_response.status_code == 401

    wrong_password_error = wrong_password_app.render_calls[-1][1]["error"]
    unknown_user_error = unknown_user_app.render_calls[-1][1]["error"]
    assert wrong_password_error == unknown_user_error == flow.GENERIC_LOGIN_ERROR


def test_password_is_never_written_to_the_session(monkeypatch):
    repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()
    client.post("/login", data={"username": "alice"})

    client.post("/login/password", data={"password": "wrong-password"})
    with client.session_transaction() as test_session:
        assert "password" not in test_session
        assert "wrong-password" not in test_session.values()

    client.post("/login/password", data={"password": "correct-horse"})
    with client.session_transaction() as test_session:
        assert "password" not in test_session
        assert "correct-horse" not in test_session.values()


def test_otp_style_route_protected_by_require_stage_rejects_before_password_verification(monkeypatch):
    """Simulates Member 5's /login/otp guard without depending on their module."""

    app = _make_app(monkeypatch)

    @app.get("/login/otp")
    @flow.require_stage(flow.STAGE_PASSWORD_VERIFIED)
    def fake_otp_route():
        return "otp page"

    client = app.test_client()

    response = client.get("/login/otp")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_otp_style_route_protected_by_require_stage_allows_after_password_verification(monkeypatch):
    app = _make_app(monkeypatch)

    @app.get("/login/otp")
    @flow.require_stage(flow.STAGE_PASSWORD_VERIFIED)
    def fake_otp_route():
        return "otp page"

    client = app.test_client()
    with client.session_transaction() as test_session:
        test_session["auth_stage"] = flow.STAGE_PASSWORD_VERIFIED
        test_session["user_id"] = 1

    response = client.get("/login/otp")

    assert response.status_code == 200
    assert response.data == b"otp page"


def test_get_verified_user_id_reads_the_session(monkeypatch):
    app = _make_app(monkeypatch)

    @app.get("/probe")
    def probe():
        return str(flow.get_verified_user_id())

    client = app.test_client()
    with client.session_transaction() as test_session:
        test_session["auth_stage"] = flow.STAGE_PASSWORD_VERIFIED
        test_session["user_id"] = 42

    response = client.get("/probe")

    assert response.data == b"42"


def test_mark_authenticated_requires_password_verified_stage(monkeypatch):
    app = _make_app(monkeypatch)

    with app.test_request_context():
        flask_session["auth_stage"] = flow.STAGE_USERNAME_SUBMITTED

        with pytest.raises(RuntimeError):
            flow.mark_authenticated()


def test_mark_authenticated_advances_session_to_authenticated(monkeypatch):
    app = _make_app(monkeypatch)

    with app.test_request_context():
        flask_session["auth_stage"] = flow.STAGE_PASSWORD_VERIFIED
        flask_session["user_id"] = 1

        flow.mark_authenticated()

        assert flask_session["auth_stage"] == flow.STAGE_AUTHENTICATED


def test_welcome_redirects_without_full_authentication(monkeypatch):
    repository = FakeRepository(
        [{"id": 1, "username": "alice", "password_hash": hash_password("correct-horse")}]
    )
    app = _make_app(monkeypatch, repository=repository)
    client = app.test_client()
    client.post("/login", data={"username": "alice"})
    client.post("/login/password", data={"password": "correct-horse"})

    response = client.get("/welcome")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_welcome_is_reachable_once_session_is_authenticated(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    with client.session_transaction() as test_session:
        test_session["auth_stage"] = flow.STAGE_AUTHENTICATED
        test_session["username"] = "alice"

    response = client.get("/welcome")

    assert response.status_code == 200
    assert response.data == b"rendered:welcome.html"


def test_logout_clears_the_session(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    with client.session_transaction() as test_session:
        test_session["auth_stage"] = flow.STAGE_AUTHENTICATED
        test_session["username"] = "alice"

    response = client.post("/logout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as test_session:
        assert "auth_stage" not in test_session

    response = client.get("/welcome")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_field_helper_reads_mapping_and_attribute_records():
    assert flow._field({"id": 5}, "id") == 5

    class Record:
        id = 7

    assert flow._field(Record(), "id") == 7
