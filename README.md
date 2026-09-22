# Accessible MFA

Small Flask demonstration for accessible, email-based multifactor authentication. The browser provides semantic keyboard forms, focus, SpeechSynthesis prompts, and optional Web Audio feedback. The server makes every authentication decision.

## Implemented flow

Home (`/`) offers **Log in** and **Sign up**. Login is:

```text
Home -> username -> password -> login OTP -> welcome -> logout -> home
```

Signup is:

```text
Home -> username -> email -> password -> confirm password -> signup OTP -> login
```

Signup creates an inactive user and never creates an authenticated session. A later login requires a new password check and a separate login-purpose OTP.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set secret values in `.env`. Do not commit `.env`. `DATABASE_URL` is the pooled Neon URL used by application requests. `DATABASE_URL_UNPOOLED` is the direct Neon URL used only by migrations.

Run the schema before using signup or provisioning:

```powershell
python -m scripts.migrate
python app.py
```

Open <http://127.0.0.1:5000/>. Normal users sign up in the browser. `scripts/create_user.py` remains an optional administrator/testing tool and creates an already active demo account.

## Environment variables

```text
SECRET_KEY=
DATABASE_URL=
DATABASE_URL_UNPOOLED=
RESEND_API_KEY=
RESEND_FROM_EMAIL=
APP_NAME=Accessible MFA
OTP_EXPIRY_SECONDS=300
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=60
SIGNUP_DRAFT_EXPIRY_SECONDS=900
```

`RESEND_FROM_EMAIL` must use a sender address from a verified Resend domain. Provider errors are hidden from the browser and secrets/OTP values are not logged.

## Database migration

Use the direct/unpooled Neon connection for schema changes:

```powershell
python -m scripts.migrate
```

The migration is idempotent and creates or updates `users`, `signup_drafts`, and `otp_challenges`. Existing users are treated as active during the backfill. Apply it before the first browser signup. Never run migrations with the pooled URL.

## Contracts

`database.repository` exposes parameterized operations including `get_user_by_username`, `get_user_by_id`, `get_user_by_email`, `create_user`, `create_signup_draft`, `get_signup_draft`, `update_signup_draft`, `delete_signup_draft`, `create_otp_challenge`, `get_active_otp_challenge(user_id, purpose)`, `increment_otp_attempts`, `mark_otp_used`, `invalidate_active_otp_challenges`, and `activate_user`.

`auth.otp.OTPService.issue(user_id, recipient, purpose="sign_in")` and `verify(user_id, submitted_code, purpose="sign_in")` support `sign_in` and `email_verification`. OTPs are six digits generated with `secrets`, stored only as HMAC digests, expire after five minutes, are attempt-limited, purpose-bound, and single-use.

Login stages are `login_username_submitted`, `login_password_verified`, and `authenticated`. Signup stages are `signup_username_submitted`, `signup_email_submitted`, `signup_password_created`, and `signup_password_confirmed`. The session contains only flow identifiers and stages; signup password hashes and OTP data remain server-side.

## Route ownership

| Area | Module | Status |
| --- | --- | --- |
| Factory/configuration/provisioning/integration | Member 1 | Implemented |
| Accessible templates, focus, SpeechSynthesis, audio cues | Member 2 | Implemented |
| Username/password and ordered login stages | Member 3 | Implemented |
| Neon schema, migrations, drafts, repository | Member 4 | Implemented |
| OTP generation, purpose binding, Resend, verification | Member 5 | Implemented |

Main routes are `/`, `/login`, `/login/password`, `/login/otp`, `/login/otp/resend`, `/signup`, `/signup/email`, `/signup/password`, `/signup/password/confirm`, `/signup/otp`, `/signup/otp/resend`, `/welcome`, `/logout`, and `/health`.

## Security and accessibility rules

- Passwords use Argon2; plaintext passwords are never stored, printed, or put in the session.
- OTP plaintext is never stored. Codes use Python `secrets`, HMAC storage, expiry, attempt limits, purpose binding, cooldown, and atomic single-use consumption.
- Login errors are generic and inactive accounts cannot sign in.
- PostgreSQL queries are parameterized. Authentication and activation decisions are server-side.
- Direct URL navigation cannot bypass a required session stage.
- Runtime secrets come from environment variables and are excluded by `.gitignore`.
- Every task has labels, autofocus, Enter submission, live-region errors/status, keyboard navigation, and visible fallback text. The application does not implement a screen reader.
- Passwords and OTP values are never spoken. OTP audio feedback is a digit-independent confirmation tone only.
- Production deployment requires HTTPS and secure HTTP-only SameSite cookies.

Out of scope: password reset, account management, SMS OTP, authenticator apps, CAPTCHA, social login, native mobile software, and biometric data collection. WebAuthn/passkeys are future work.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

The test suite covers the factory, configuration, repository contracts, provisioning, OTP security, route guards, accessibility markup, migration command, signup validation, and login/logout behavior. A live run additionally requires a migrated Neon database, verified Resend sender, API key, and a mailbox for OTP delivery.
