## Accessible MFA Authentication System

A small Flask application for demonstrating an accessible, keyboard-first multifactor login process for visually impaired users.

## Project Scope

The planned authentication flow is:

1. Enter a username.
2. Enter the password.
3. Enter the six-digit code sent to the registered email address.
4. View the authenticated welcome page.
5. Log out and invalidate the session.

The application uses the browser's built-in `SpeechSynthesis` API for prompts. It does not implement a screen reader. Users can read the OTP email with the screen reader already available on their device.

## Accessible UI Module

This branch, `feature/accessibility-ui`, contains the accessible frontend and text-to-speech module:

- `templates/username.html` - username entry page
- `templates/password.html` - password entry page
- `templates/otp.html` - email OTP entry page
- `templates/welcome.html` - authenticated welcome page and logout form
- `static/accessibility.js` - reusable browser speech and focus helper
- `tests/test_accessibility.py` - dependency-free accessibility contract tests

Each authentication page contains one main input, an explicit label, automatic focus, a standard POST form, and a keyboard-accessible submit button. Server-returned errors are placed in live regions for assistive technology.

## Expected Routes

The templates use these route contracts for integration with the Flask backend:

| Page or action | Method | Route |
| --- | --- | --- |
| Username submission | `POST` | `/login` |
| Password submission | `POST` | `/login/password` |
| OTP submission | `POST` | `/login/otp` |
| Logout | `POST` | `/logout` |

The backend is responsible for authentication decisions, session state, redirects, password verification, OTP generation, and email delivery. JavaScript does not decide whether authentication succeeds.

## Text-to-Speech Safety

Speech prompts are fixed page instructions. The accessibility script:

- speaks the page instruction once after loading;
- focuses the page's main input;
- cancels an earlier speech request before starting a new one;
- never reads password or OTP input values;
- never speaks continuously while the user types.

## Running the UI Tests

The tests use only Python's standard library and can run before Flask and database integration are added:

```bash
python3 -m unittest tests.test_accessibility -v
```

They verify labels, autofocus, form methods and actions, expected input counts, script inclusion, and the absence of sensitive input values from speech prompts.

## Planned Technology Stack

- Python and Flask
- Plain semantic HTML
- Minimal JavaScript
- Browser `SpeechSynthesis` API
- Neon PostgreSQL
- Resend email API
- Argon2 or bcrypt password hashing
- pytest for the complete project test suite

## Security Notes

The completed application must keep passwords and OTPs hashed, generate OTPs with Python's `secrets` module, expire and limit OTP attempts, enforce the authentication order server-side, parameterize database queries, and load secrets from environment variables. Production deployment assumes HTTPS.

Registration, password reset, SMS OTP, authenticator apps, biometrics, CAPTCHA, and custom screen-reader software are outside the project scope.
# Accessible MFA

Accessible MFA is a small Flask application for demonstrating a keyboard-friendly, multifactor login process for visually impaired users. The application relies on the user's existing screen reader for email, and uses the browser SpeechSynthesis API for short page instructions. It does not implement a screen reader.

The complete login flow is planned as:

1. Enter a username.
2. Enter the password after server-side username-step validation.
3. Enter the six-digit code delivered to the registered email address.
4. View the protected welcome page.
5. Log out, which clears authentication state.

The username/password, accessible templates, PostgreSQL repository, and Resend OTP service are owned by separate feature branches. This foundation branch provides the shared configuration, application factory, health check, password hashing helper, provisioning entry point, and contracts those modules use.

## Technology

- Python 3.11+
- Flask
- Neon PostgreSQL through `psycopg[binary]`
- Argon2 through `argon2-cffi`
- Resend email API
- Plain HTML and minimal JavaScript
- Browser SpeechSynthesis API
- pytest

## Setup

Create and activate a virtual environment, then install the pinned top-level dependencies:

```text
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the deployment-specific values. `.env` is ignored by Git and must never be committed. A real `DATABASE_URL` is required once the Member 4 data layer is integrated; a real Resend API key and sender address are required for email OTP delivery.

Run the foundation application locally with:

```text
python app.py
```

The application factory is also available for Flask tooling and tests:

```python
from app import create_app
app = create_app()
```

`GET /health` returns `{"status": "ok"}`. The foundation does not claim that the login flow is implemented until the other member modules are merged.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session signing key; required at runtime |
| `DATABASE_URL` | Neon PostgreSQL connection string; required at runtime |
| `RESEND_API_KEY` | Resend credential; required at runtime |
| `RESEND_FROM_EMAIL` | Verified sender address used by Resend |
| `APP_NAME` | Name used in user-facing email text |
| `OTP_EXPIRY_SECONDS` | OTP lifetime, default `300` |
| `OTP_MAX_ATTEMPTS` | Maximum failed OTP submissions, default `5` |
| `OTP_RESEND_COOLDOWN_SECONDS` | Minimum delay between sends, default `60` |

The application validates required runtime settings without printing their values. Non-secret OTP settings have development defaults; secrets do not.

## Tests

Run the foundation tests with:

```text
pytest
```

The tests use an explicit test secret and do not require a Neon database or Resend account.

## Branch and module ownership

Each member works on a separate branch to keep merges small:

| Member | Branch | Primary ownership |
| --- | --- | --- |
| 1 | `feature/project-foundation` | Factory, configuration, contracts, provisioning, integration |
| 2 | `feature/accessibility-ui` | Accessible templates, keyboard behavior, browser speech |
| 3 | `feature/password-flow` | Username/password routes and ordered session state |
| 4 | `feature/neon-database` | Neon schema, connection layer, and repository |
| 5 | `feature/email-otp` | Secure OTP generation, Resend delivery, verification, and OTP controls |

Member 1 registers the completed blueprints through the optional integration hook in `app.py`. Members should not take ownership of another member's primary files.

## Shared module contracts

These are intentionally small Python-level contracts. Exact return types may be a dictionary or a lightweight record, but callers should be able to read the named fields.

### Database / Member 4

The repository should expose:

```text
get_user_by_username(username) -> user record | None
get_user_by_id(user_id) -> user record | None
create_user(username, email, password_hash) -> user record

create_otp_challenge(user_id, otp_hash, expires_at) -> challenge record
get_active_otp_challenge(user_id) -> challenge record | None
increment_otp_attempts(challenge_id) -> None or updated challenge
mark_otp_used(challenge_id) -> None or updated challenge
invalidate_active_otp_challenges(user_id) -> None
```

All values derived from users or submitted codes must be passed as parameters to PostgreSQL queries. Active OTP lookup must exclude used and expired challenges, and challenge operations must be scoped to the supplied user/challenge ID.

### Password flow / Member 3

Password verification should use the shared behavior:

```text
verify_password(password_hash, supplied_password) -> bool
```

The expected Flask session stages are:

```text
"username_submitted" -> "password_verified" -> "authenticated"
```

Only the server may advance a stage. The session may contain the minimum non-secret identifiers needed to continue the flow, such as the user ID and username; it must never contain a plaintext password or OTP.

Expected routes are `GET/POST /login`, `GET/POST /login/password`, and the protected `GET /welcome`. Direct navigation to later routes must redirect safely unless the required prior stage is present.

### OTP / Member 5

The OTP service should expose:

```text
issue_otp(user_id)
verify_otp(user_id, submitted_code) -> bool
resend_otp(user_id)
```

`issue_otp` generates a six-digit code with Python's `secrets` module, stores only a secure derived value, sends the email through Resend, and invalidates the previous active challenge. Verification must enforce expiry, attempt limits, user ownership, and single-use behavior.

Expected routes are `GET/POST /login/otp` and `POST /login/otp/resend`. A successful verification is the only point at which the session may become `"authenticated"`.

### Accessibility / Member 2

Expected templates are `username.html`, `password.html`, `otp.html`, and `welcome.html`. Expected shared JavaScript is `static/accessibility.js`.

Each authentication page should have one main input, a semantic label, autofocus, keyboard/Enter submission, and a short spoken instruction. Password and OTP values must never be passed to SpeechSynthesis. Server-returned errors should be available to existing screen readers through semantic status markup.

## Demo-user provisioning

There is intentionally no registration UI. After Member 4 merges the repository module and applies `database/schema.sql`, create a demo user interactively:

```text
python -m scripts.create_user
```

The command prompts with `getpass`, hashes the password with Argon2, and calls `database.repository.create_user(username, email, password_hash)`. It never writes or prints the plaintext password. Until `database.repository` exists, the command exits with a clear integration message rather than duplicating database SQL.

## Security rules

- Passwords are hashed with Argon2; plaintext passwords are never stored, logged, or printed back.
- OTP plaintext is never stored in PostgreSQL.
- OTPs are generated with Python's cryptographically secure `secrets` module.
- OTPs expire, have a failed-attempt limit, a resend cooldown, and are single-use.
- PostgreSQL queries must be parameterized.
- `SECRET_KEY`, `DATABASE_URL`, and `RESEND_API_KEY` are supplied through environment variables and never committed.
- Authentication decisions happen on the server, not in JavaScript.
- Server-side session stages prevent direct URL navigation from bypassing authentication steps.
- Production HTTPS is assumed; TLS is not implemented by this application.

Registration UI, password reset, account management, email verification, SMS OTP, authenticator apps, custom screen-reader software, admin features, native mobile applications, and biometrics are out of scope. Platform APIs such as WebAuthn may be considered as future work.
