# Accessible MFA

A small Flask application demonstrating keyboard-accessible multifactor login for visually impaired users. The site uses browser SpeechSynthesis for brief instructions and relies on the user's existing screen reader to read email. It does not implement a screen reader.

## Authentication flow

1. The user enters a username.
2. The user enters a password. The server verifies it against an Argon2 hash.
3. The server sends a six-digit code to the registered email address. The user enters that code.
4. The server marks the session authenticated and shows the welcome page.
5. Logout clears the session.

Each sign-in step is a separate page with a labelled input, keyboard submission, automatic focus, and a spoken instruction. Error and status messages are exposed through accessible live regions. Authentication decisions and stage changes happen on the server.

## Technology

- Python 3.11+ and Flask
- Neon PostgreSQL through `psycopg[binary]`
- Argon2 through `argon2-cffi`
- Resend email API
- Plain HTML, minimal JavaScript, and browser SpeechSynthesis
- pytest

## Setup and run

Create a virtual environment and install dependencies:

```text
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set the values below. `.env` is ignored by Git. Apply `database/schema.sql` to the Neon database, then start the app:

```text
python app.py
```

`GET /health` returns `{"status": "ok"}`. The app factory can also be imported with `from app import create_app`.

Run automated tests with:

```text
python -m pytest
```

Tests use fake database and email services where needed; no live Neon or Resend account is required.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session signing key; required |
| `DATABASE_URL` | Neon PostgreSQL connection string; required |
| `RESEND_API_KEY` | Resend API credential; required |
| `RESEND_FROM_EMAIL` | Verified sender address; required |
| `APP_NAME` | Application name in the OTP email; default `Accessible MFA` |
| `OTP_EXPIRY_SECONDS` | OTP lifetime; default `300` |
| `OTP_MAX_ATTEMPTS` | Failed OTP limit; default `5` |
| `OTP_RESEND_COOLDOWN_SECONDS` | Minimum resend interval; default `60` |

The application checks that required runtime settings are present without displaying their values.

## Module ownership

| Member | Branch | Contribution |
| --- | --- | --- |
| 1 | `feature/project-foundation` | Configuration, application factory, integration, provisioning, shared contracts |
| 2 | `feature/accessibility-ui` | Accessible templates and browser speech/focus behavior |
| 3 | `feature/password-flow` | Username/password verification and session stages |
| 4 | `feature/neon-database` | PostgreSQL schema, connection, and repository |
| 5 | `feature/email-otp` | OTP generation, email delivery, verification, expiry, attempts, and cooldown |

## Shared module contracts

### Database

`database.repository` provides:

```text
get_user_by_username(username) -> user record | None
get_user_by_id(user_id) -> user record | None
create_user(username, email, password_hash) -> user record
create_otp_challenge(user_id, otp_hash, expires_at, sent_at) -> challenge record
get_active_otp_challenge(user_id) -> challenge record | None
increment_otp_attempts(challenge_id) -> bool
mark_otp_used(challenge_id) -> bool
invalidate_active_otp_challenges(user_id) -> count
```

User records expose `id`, `username`, `email`, and `password_hash`; challenge records expose `id`, `otp_hash`, `expires_at`, `sent_at`, and `failed_attempts`. Repository SQL uses parameters.

### Authentication and OTP

`auth.flow` owns the stages `username_submitted`, `password_verified`, and `authenticated`. It exposes `auth_bp`, `require_stage(stage)`, `get_verified_user_id()`, and `mark_authenticated()`. The only transition to `authenticated` occurs after successful OTP verification.

`auth.otp` exposes `OTPService.issue(user_id, recipient)` and `OTPService.verify(user_id, submitted_code)`. Its `create_otp_blueprint(service, repository)` provides `GET/POST /login/otp` and `POST /login/otp/resend`. The application factory configures and registers both authentication blueprints.

### Accessibility

The pages are `username.html`, `password.html`, `otp.html`, and `welcome.html`; shared focus and speech behavior is in `static/accessibility.js`. Fixed instructions and accessible error/status messages may be spoken. Password and OTP input values are never read by JavaScript.

## Demo users

There is no registration page. After setting `DATABASE_URL` and applying the schema, create a user with:

```text
python -m scripts.create_user
```

The script uses `getpass`, hashes the password with Argon2, and calls `database.repository.create_user`. Plaintext passwords are not stored or printed.

## Security rules

- Passwords are stored only as Argon2 hashes; plaintext passwords are never stored, logged, or printed back.
- OTP codes are generated with Python's `secrets` module; only an HMAC digest is stored.
- OTPs expire, have a failed-attempt limit and resend cooldown, and can be used only once.
- PostgreSQL queries are parameterized.
- Secrets come from environment variables and are not committed.
- Authentication decisions occur on the server.
- Session stages protect later pages from direct URL navigation.
- Production deployment assumes HTTPS; this application does not implement TLS.

Registration, password reset, SMS, authenticator apps, CAPTCHA, account management, biometrics, and custom screen-reader software are outside the project scope. Platform APIs such as WebAuthn may be future work.
