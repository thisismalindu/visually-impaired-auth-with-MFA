from app import create_app
from auth.otp import OTPService, OTPSettings


def test_create_app_succeeds_with_test_configuration():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})

    assert app is not None


def test_health_returns_success():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_root_redirects_to_login():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    response = app.test_client().get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_testing_mode_is_enabled_when_configured():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})

    assert app.testing is True


def test_application_factory_registers_all_login_and_otp_routes():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret"})
    routes = {(rule.rule, tuple(sorted(rule.methods - {"HEAD", "OPTIONS"}))) for rule in app.url_map.iter_rules()}

    assert ("/login", ("GET",)) in routes
    assert ("/login", ("POST",)) in routes
    assert ("/login/password", ("GET",)) in routes
    assert ("/login/password", ("POST",)) in routes
    assert ("/login/otp", ("GET",)) in routes
    assert ("/login/otp", ("POST",)) in routes
    assert ("/login/otp/resend", ("POST",)) in routes
    assert ("/welcome", ("GET",)) in routes
    assert ("/logout", ("POST",)) in routes
    assert ("/health", ("GET",)) in routes
    assert "otp_service" in app.extensions


def test_full_authentication_flow_with_fake_database_and_email(monkeypatch):
    import auth.flow as flow

    class FakeRepository:
        def __init__(self):
            self.user = {
                "id": 9,
                "username": "alice",
                "email": "alice@example.test",
                "password_hash": flow.hash_password("test-password"),
            }
            self.challenge = None
            self.used = False

        def get_user_by_username(self, username):
            return self.user if username == self.user["username"] else None

        def get_user_by_id(self, user_id):
            return self.user if user_id == self.user["id"] else None

        def get_active_otp_challenge(self, user_id):
            if self.challenge and user_id == self.challenge["user_id"] and not self.used:
                return self.challenge
            return None

        def invalidate_active_otp_challenges(self, user_id):
            self.used = True

        def create_otp_challenge(self, user_id, otp_hash, expires_at, sent_at):
            self.used = False
            self.challenge = {
                "id": 1,
                "user_id": user_id,
                "otp_hash": otp_hash,
                "expires_at": expires_at,
                "sent_at": sent_at,
                "failed_attempts": 0,
            }
            return self.challenge

        def increment_otp_attempts(self, challenge_id):
            self.challenge["failed_attempts"] += 1

        def mark_otp_used(self, challenge_id):
            if self.used:
                return False
            self.used = True
            return True

    class FakeSender:
        def __init__(self):
            self.messages = []

        def send(self, recipient, subject, body):
            self.messages.append((recipient, subject, body))

    repo = FakeRepository()
    sender = FakeSender()
    service = OTPService(
        repo,
        sender,
        OTPSettings(secret_key="test-otp-secret"),
    )
    monkeypatch.setattr(service, "_new_otp", lambda: "654321")
    monkeypatch.setattr(flow, "_load_repository", lambda: repo)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret",
        "OTP_SERVICE": service,
        "OTP_REPOSITORY": repo,
    })
    client = app.test_client()

    assert client.get("/login/password").status_code == 302
    assert client.get("/login/otp").status_code == 302
    assert client.get("/welcome").status_code == 302

    assert client.post("/login", data={"username": "alice"}).status_code == 302
    assert client.post("/login/password", data={"password": "test-password"}).status_code == 302
    assert sender.messages[0][0] == "alice@example.test"
    assert "654321" in sender.messages[0][2]
    assert client.get("/login/otp").status_code == 200

    response = client.post("/login/otp", data={"otp": "654321"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/welcome")
    assert client.get("/welcome").status_code == 200

    assert client.post("/logout").status_code == 302
    assert client.get("/welcome").status_code == 302


def test_email_delivery_failure_does_not_advance_past_password_step(monkeypatch):
    import auth.flow as flow
    from auth.otp import OTPDeliveryError

    user = {
        "id": 3,
        "username": "bob",
        "email": "bob@example.test",
        "password_hash": flow.hash_password("test-password"),
    }

    class FakeRepository:
        def get_user_by_username(self, username):
            return user if username == "bob" else None

        def get_user_by_id(self, user_id):
            return user if user_id == 3 else None

    class FailingOTPService:
        def issue(self, user_id, recipient):
            raise OTPDeliveryError("provider response must remain private")

    repo = FakeRepository()
    monkeypatch.setattr(flow, "_load_repository", lambda: repo)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret",
        "OTP_SERVICE": FailingOTPService(),
        "OTP_REPOSITORY": repo,
    })
    client = app.test_client()
    client.post("/login", data={"username": "bob"})

    response = client.post("/login/password", data={"password": "test-password"})

    assert response.status_code == 503
    assert b"provider response must remain private" not in response.data
    assert b"We could not send a sign-in code" in response.data
    with client.session_transaction() as test_session:
        assert test_session["auth_stage"] == "username_submitted"
        assert "user_id" not in test_session
    assert client.get("/welcome").status_code == 302
