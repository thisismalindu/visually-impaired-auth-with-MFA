from datetime import datetime, timezone

import auth.flow as flow
from app import create_app
from auth.otp import OTPService, OTPSettings
from auth.password_utils import hash_password


class FakeRepository:
    def __init__(self):
        self.users = {}
        self.next_user_id = 1
        self.challenge = None
        self.next_challenge_id = 1

    def get_user_by_username(self, username):
        return next((u for u in self.users.values() if u["username"] == username), None)

    def get_user_by_email(self, email):
        return next((u for u in self.users.values() if u["email"] == email), None)

    def get_user_by_id(self, user_id):
        return self.users.get(user_id)

    def create_user(self, username, email, password_hash, email_verified=False):
        user = {
            "id": self.next_user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "email_verified": email_verified,
        }
        self.users[self.next_user_id] = user
        self.next_user_id += 1
        return user

    def mark_user_email_verified(self, user_id):
        user = self.users[user_id]
        if user["email_verified"]:
            return False
        user["email_verified"] = True
        return True

    def invalidate_active_otp_challenges(self, user_id):
        if self.challenge and self.challenge["user_id"] == user_id:
            self.challenge["used"] = True

    def create_otp_challenge(self, user_id, otp_hash, expires_at, sent_at):
        self.challenge = {
            "id": self.next_challenge_id,
            "user_id": user_id,
            "otp_hash": otp_hash,
            "expires_at": expires_at,
            "sent_at": sent_at,
            "failed_attempts": 0,
            "used": False,
        }
        self.next_challenge_id += 1
        return self.challenge

    def get_active_otp_challenge(self, user_id):
        if self.challenge and self.challenge["user_id"] == user_id and not self.challenge["used"]:
            return self.challenge
        return None

    def increment_otp_attempts(self, challenge_id):
        self.challenge["failed_attempts"] += 1

    def mark_otp_used(self, challenge_id):
        if self.challenge["used"]:
            return False
        self.challenge["used"] = True
        return True


class FakeSender:
    def __init__(self):
        self.messages = []

    def send(self, recipient, subject, body):
        self.messages.append((recipient, subject, body))


def make_app(monkeypatch):
    repository = FakeRepository()
    sender = FakeSender()
    service = OTPService(
        repository,
        sender,
        OTPSettings(secret_key="signup-test-secret"),
    )
    codes = iter(("111111", "222222"))
    monkeypatch.setattr(service, "_new_otp", lambda: next(codes))
    monkeypatch.setattr(flow, "_load_repository", lambda: repository)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-session-key",
            "OTP_SERVICE": service,
            "OTP_REPOSITORY": repository,
        }
    )
    return app, repository, sender


def test_signup_then_login_requires_two_different_otp_steps(monkeypatch):
    app, repository, sender = make_app(monkeypatch)
    client = app.test_client()

    assert client.post("/signup", data={"username": "new-user"}).status_code == 302
    assert client.post("/signup/email", data={"email": "New.User@Example.test"}).status_code == 302
    response = client.post(
        "/signup/password",
        data={"password": "correct-password", "password_confirmation": "correct-password"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup/otp")
    assert repository.users[1]["email"] == "new.user@example.test"
    assert repository.users[1]["email_verified"] is False
    assert repository.users[1]["password_hash"].startswith("$argon2")
    assert "correct-password" not in str(repository.users[1])
    with client.session_transaction() as session:
        assert "correct-password" not in str(dict(session))
    assert "email verification" in sender.messages[0][2]

    response = client.post("/signup/otp", data={"otp": "111111"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert repository.users[1]["email_verified"] is True
    with client.session_transaction() as session:
        assert session["post_signup_status"]
        assert "password" not in session

    response = client.get("/login")
    assert b"Your email has been verified" in response.data
    assert client.post("/login", data={"username": "new-user"}).status_code == 302
    response = client.post("/login/password", data={"password": "correct-password"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login/otp")
    assert sender.messages[1][2].startswith("Your Accessible MFA OTP is: 222222")
    assert client.post("/login/otp", data={"otp": "222222"}).status_code == 302
    assert client.get("/welcome").status_code == 200


def test_signup_steps_cannot_be_bypassed_and_unverified_users_cannot_login(monkeypatch):
    app, repository, _ = make_app(monkeypatch)
    client = app.test_client()

    for path in ("/signup/email", "/signup/password", "/signup/otp"):
        assert client.get(path).status_code == 302
        assert client.get(path).headers["Location"].endswith("/signup")

    user = repository.create_user("pending", "pending@example.test", hash_password("password123"))
    assert user["email_verified"] is False
    client.post("/login", data={"username": "pending"})
    response = client.post("/login/password", data={"password": "password123"})
    assert response.status_code == 401
    assert b"Authentication failed" in response.data


def test_signup_validates_password_and_email(monkeypatch):
    app, _, _ = make_app(monkeypatch)
    client = app.test_client()
    client.post("/signup", data={"username": "new-user"})

    assert client.post("/signup/email", data={"email": "not-an-email"}).status_code == 400
    client.post("/signup/email", data={"email": "new@example.test"})
    assert client.post(
        "/signup/password",
        data={"password": "short", "password_confirmation": "short"},
    ).status_code == 400
    assert client.post(
        "/signup/password",
        data={"password": "long-enough", "password_confirmation": "different"},
    ).status_code == 400


def test_unverified_signup_can_resume_with_same_details(monkeypatch):
    app, repository, sender = make_app(monkeypatch)
    client = app.test_client()
    client.post("/signup", data={"username": "resume"})
    client.post("/signup/email", data={"email": "resume@example.test"})
    client.post(
        "/signup/password",
        data={"password": "password123", "password_confirmation": "password123"},
    )

    with client.session_transaction() as session:
        session.clear()
    client.post("/signup", data={"username": "resume"})
    client.post("/signup/email", data={"email": "RESUME@example.test"})
    response = client.post(
        "/signup/password",
        data={"password": "password123", "password_confirmation": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup/otp")
    assert len(repository.users) == 1
    assert len(sender.messages) == 1


def test_signup_accessible_templates_do_not_speak_values():
    from pathlib import Path

    root = Path(__file__).parents[1]
    for name in ("home", "signup_username", "signup_email", "signup_password", "signup_otp"):
        markup = (root / "templates" / f"{name}.html").read_text()
        assert "/static/accessibility.js" in markup
        assert 'role="alert"' in markup or name == "home"
    script = (root / "static" / "accessibility.js").read_text().lower()
    assert "input.value" not in script
    assert "password" not in script
    assert "otp" not in script
