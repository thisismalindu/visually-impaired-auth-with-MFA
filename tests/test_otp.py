"""Security tests for the email OTP module."""

from datetime import datetime, timedelta, timezone

import pytest
from jinja2 import DictLoader

from auth.otp import (
    OTPDeliveryError,
    OTPResendTooSoon,
    OTPService,
    OTPSettings,
    OTPVerificationError,
    ResendEmailSender,
    create_otp_blueprint,
)


class FakeRepository:
    def __init__(self):
        self.challenge = None
        self.next_id = 1
        self.invalidations = 0
        self.attempt_increments = 0

    def invalidate_active_otp_challenges(self, user_id):
        self.invalidations += 1
        if self.challenge:
            self.challenge["used"] = True

    def create_otp_challenge(self, user_id, otp_hash, expires_at, sent_at):
        self.challenge = {"id": self.next_id, "user_id": user_id, "otp_hash": otp_hash, "expires_at": expires_at, "sent_at": sent_at, "failed_attempts": 0, "used": False}
        self.next_id += 1

    def get_active_otp_challenge(self, user_id):
        if self.challenge and not self.challenge["used"] and self.challenge["user_id"] == user_id:
            return self.challenge
        return None

    def increment_otp_attempts(self, challenge_id):
        self.attempt_increments += 1
        self.challenge["failed_attempts"] += 1

    def mark_otp_used(self, challenge_id):
        self.challenge["used"] = True


class FakeSender:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def send(self, recipient, subject, body):
        if self.fail:
            raise RuntimeError("provider details")
        self.messages.append((recipient, subject, body))


def make_service(repo=None, sender=None, now=None, **kwargs):
    repo = repo or FakeRepository()
    sender = sender or FakeSender()
    now = now or datetime.now(timezone.utc)
    service = OTPService(repo, sender, OTPSettings(secret_key="test-secret", **kwargs), clock=lambda: now)
    return service, repo, sender


def test_generates_six_digit_code_and_persists_only_digest(monkeypatch):
    service, repo, sender = make_service()
    monkeypatch.setattr(service, "_new_otp", lambda: "123456")
    service.issue(7, "user@example.test")
    assert len(sender.messages[0][2].split("OTP is: ")[1].split(".")[0]) == 6
    assert repo.challenge["otp_hash"] == service._digest("123456")
    assert "123456" not in repo.challenge["otp_hash"]


def test_correct_code_succeeds_and_used_code_cannot_replay(monkeypatch):
    service, _, _ = make_service()
    monkeypatch.setattr(service, "_new_otp", lambda: "123456")
    service.issue(7, "user@example.test")
    assert service.verify(7, "123456") is True
    with pytest.raises(OTPVerificationError):
        service.verify(7, "123456")


def test_incorrect_code_fails_and_counts_attempt():
    service, repo, _ = make_service()
    service.issue(7, "user@example.test")
    with pytest.raises(OTPVerificationError):
        service.verify(7, "000000")
    assert repo.attempt_increments == 1


def test_expired_code_fails():
    service, repo, _ = make_service()
    service.issue(7, "user@example.test")
    repo.challenge["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(OTPVerificationError):
        service.verify(7, "123456")


def test_resend_invalidates_previous_code(monkeypatch):
    now = datetime.now(timezone.utc)
    service, repo, _ = make_service(now=now)
    monkeypatch.setattr(service, "_new_otp", lambda: "123456")
    service.issue(7, "user@example.test")
    first_hash = repo.challenge["otp_hash"]
    service.clock = lambda: now + timedelta(seconds=61)
    monkeypatch.setattr(service, "_new_otp", lambda: "654321")
    service.issue(7, "user@example.test")
    assert repo.invalidations == 2
    assert repo.challenge["otp_hash"] != first_hash


def test_resend_cooldown_works():
    service, _, _ = make_service()
    service.issue(7, "user@example.test")
    with pytest.raises(OTPResendTooSoon):
        service.issue(7, "user@example.test")


def test_attempt_limit_works():
    service, repo, _ = make_service(max_attempts=2)
    service.issue(7, "user@example.test")
    for _ in range(2):
        with pytest.raises(OTPVerificationError):
            service.verify(7, "000000")
    with pytest.raises(OTPVerificationError):
        service.verify(7, "123456")
    assert repo.attempt_increments == 2


def test_delivery_failure_is_safe_and_does_not_persist_code():
    repo = FakeRepository()
    service, _, _ = make_service(repo=repo, sender=FakeSender(fail=True))
    with pytest.raises(OTPDeliveryError) as error:
        service.issue(7, "user@example.test")
    assert str(error.value) == "OTP delivery failed"
    assert repo.challenge is None


def test_resend_api_sender_is_mocked_without_network_access():
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return Response()

    sender = ResendEmailSender("test-api-key", "no-reply@example.test", opener=opener)
    sender.send("user@example.test", "Your Accessible MFA OTP", "Your code is ready.")
    request, timeout = requests[0]
    assert timeout == 10
    assert request.get_header("Authorization") == "Bearer test-api-key"
    assert b"Your code is ready." in request.data


def test_otp_routes_enforce_password_stage_and_authenticate(monkeypatch):
    flask = pytest.importorskip("flask")

    repo = FakeRepository()
    service, _, _ = make_service(repo=repo)
    monkeypatch.setattr(service, "_new_otp", lambda: "123456")
    service.issue(7, "user@example.test")

    app = flask.Flask(__name__)
    app.secret_key = "test-session-key"
    app.jinja_loader = DictLoader({"otp.html": "OTP page"})

    @app.get("/login/password")
    def login_password():
        return "password"

    @app.get("/welcome")
    def welcome():
        return "welcome"

    app.register_blueprint(create_otp_blueprint(service, repo))
    client = app.test_client()

    response = client.get("/login/otp")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login/password")

    with client.session_transaction() as session:
        session["auth_stage"] = "password_verified"
        session["user_id"] = 7
    response = client.post("/login/otp", data={"otp": "123456"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/welcome")
    with client.session_transaction() as session:
        assert session["auth_stage"] == "authenticated"


def test_otp_routes_do_not_authenticate_on_wrong_code():
    flask = pytest.importorskip("flask")
    service, repo, _ = make_service()
    service._new_otp = lambda: "123456"
    service.issue(7, "user@example.test")

    app = flask.Flask(__name__)
    app.secret_key = "test-session-key"
    app.jinja_loader = DictLoader({"otp.html": "OTP page"})

    @app.get("/login/password")
    def login_password():
        return "password"

    @app.get("/welcome")
    def welcome():
        return "welcome"

    app.register_blueprint(create_otp_blueprint(service, repo))
    client = app.test_client()
    with client.session_transaction() as session:
        session["auth_stage"] = "password_verified"
        session["user_id"] = 7
    response = client.post("/login/otp", data={"otp": "000000"})
    assert response.status_code == 401
    with client.session_transaction() as session:
        assert session["auth_stage"] == "password_verified"