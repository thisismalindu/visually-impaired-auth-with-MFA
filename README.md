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

```text
You are helping with a 5-person university Computer Security assignment.

PROJECT TITLE
Design and Implement a Multifactor Authentication System for Visually Impaired Users

PROJECT SCOPE
We are building a very small Flask web application focused only on an accessible login process.

Authentication flow:

1. Username page
   - One input only.
   - Browser text-to-speech says: "Type your username now."
   - User can type the username and press Enter.

2. Password page
   - One password input only.
   - Browser text-to-speech says: "Type your password now."
   - User can type the password and press Enter.

3. Email OTP page
   - After the password is successfully verified, the server generates a random 6-digit OTP.
   - The OTP is sent to the user's registered email address using Resend.
   - Example email:
     Subject: Your <Application Name> OTP
     Body: "Your <Application Name> OTP is: 687456. It expires in 5 minutes."
   - The user can read this email using the screen reader already available on their phone/computer.
   - Our application does NOT implement a screen reader.
   - Browser text-to-speech on the web page says: "Type the six digit code sent to your email."
   - User enters the code and presses Enter.

4. Welcome page
   - Displays: "Welcome, <username>"
   - Contains a Logout button.
   - This page must only be accessible after both password and OTP authentication succeed.

5. Logout
   - Invalidates the authenticated session.
   - User must authenticate again to return to the welcome page.

ACCESSIBILITY REQUIREMENTS
- The complete login process must work without a mouse.
- Keyboard navigation and Enter-key submission must work.
- Each authentication step is on a separate page so the user only deals with one main task at a time.
- Use semantic HTML and proper labels so existing screen readers can understand the pages.
- Automatically focus the main input when each page loads.
- Use browser SpeechSynthesis for spoken prompts and appropriate status/error messages.
- Never speak the user's password or OTP value back to them.
- Do not require visual CAPTCHA, QR codes, images, drag-and-drop, or other visual-only interactions.
- No complex visual design is required. Plain HTML is acceptable.

TECHNOLOGY STACK
- Python
- Flask
- Plain HTML
- Minimal JavaScript
- Browser SpeechSynthesis API
- Neon PostgreSQL
- Resend email API
- Password hashing using Argon2 or bcrypt
- pytest for tests
- Git/GitHub

DATABASE
At minimum, users need:
- id
- username
- email
- password_hash

OTP challenge data should support:
- user_id
- hashed OTP, not plaintext OTP
- expiry time
- used/not-used state
- failed attempt count
- creation/sent time as needed for resend cooldown

SECURITY REQUIREMENTS
- Never store plaintext passwords.
- Never store plaintext OTP codes in the database.
- OTP must be generated using Python's cryptographically secure `secrets` module.
- OTP should expire after approximately 5 minutes.
- An OTP must become unusable after successful verification.
- Limit OTP verification attempts.
- Add a sensible resend cooldown.
- Do not reveal whether a username exists through detailed authentication errors.
- Authentication decisions must happen on the server, never in JavaScript.
- A user must not bypass steps by manually visiting /login/password, /login/otp, or /welcome.
- Use server-side/session state to enforce authentication order.
- Database queries must be parameterized.
- Secrets such as DATABASE_URL, SECRET_KEY and RESEND_API_KEY must come from environment variables and must not be committed to Git.
- Production HTTPS is assumed; do not implement TLS yourself.

OUT OF SCOPE
- Registration UI
- Password reset
- Account management
- Email verification
- SMS OTP
- Authenticator/TOTP apps
- Custom screen reader software
- Admin panel
- Native mobile app
- Fingerprint/biometric authentication

Biometrics can only be mentioned as future work, possibly through platform/device APIs such as WebAuthn.

DEVELOPMENT MODEL
There are 5 members.
Each member works in their own feature branch.
Do not redesign the whole project.
Do not take ownership of another member's module unless a tiny integration change is absolutely necessary.
Keep code modular and make your module easy to merge.

Do not spend time proposing alternative architectures unless something is technically impossible.
Implement the assigned work directly.
Keep the solution simple enough for a university assignment.
Add tests for your own module.
Add concise comments only where they help explain security-sensitive behavior.

The repository will be initialized by Member 1.

Expected repository structure is approximately:

app.py
config.py
requirements.txt
.env.example
.gitignore

auth/
    password.py
    flow.py
    otp.py

database/
    db.py
    repository.py
    schema.sql

templates/
    username.html
    password.html
    otp.html
    welcome.html

static/
    accessibility.js

scripts/
    create_user.py

tests/

The exact structure may change slightly during integration, but preserve module ownership.
```

---

# Member 1 — You

**Branch:** `feature/project-foundation`

Your work is deliberately broader because you are creating the repository and defining the interfaces the other four members depend on.

1. **Create the repository and project foundation.** Initialize Git, create the Flask project structure, `.gitignore`, `requirements.txt`, `.env.example`, `README.md`, packages/directories, and a minimal `app.py` that starts successfully. Establish the five feature branches or document the branch names.

2. **Implement centralized configuration.** Create `config.py` and load `DATABASE_URL`, `SECRET_KEY`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, OTP lifetime, OTP attempt limit, and resend cooldown from environment variables. No secrets should appear in committed files.

3. **Define shared module contracts before teammates begin.** Document the functions/routes the modules are expected to expose so team members do not build incompatible code. For example, define expected repository functions such as `get_user_by_username()`, expected password verification behavior, OTP service entry points, and the session stages used by the authentication flow.

4. **Implement account provisioning because there is no registration page.** Create something such as `scripts/create_user.py` that securely creates demo users with `username`, `email`, and a hashed password. It should use Argon2/bcrypt and the shared database layer once Member 4's code is merged. Do not allow plaintext passwords to be stored.

5. **Own foundation integration and startup verification.** Register the other members' Flask blueprints/modules as they are merged, resolve only integration-level conflicts, maintain dependency versions and setup instructions, and add basic smoke tests proving the application starts and configuration is loaded correctly.

Your contribution should therefore be visible as **project architecture + configuration/security foundation + user provisioning + final module wiring**, not merely "creating the GitHub repository."

---

# Prompt for Member 2 — Accessible UI and Text-to-Speech

```text
You are Member 2.

Your branch is:

feature/accessibility-ui

Your ownership is the accessible frontend/login wizard. Do not implement password verification, database logic, or email OTP generation.

Implement these 5 responsibilities:

1. BUILD THE FOUR USER-FACING PAGES

Create plain semantic HTML templates for:

- username.html
- password.html
- otp.html
- welcome.html

The authentication pages must follow a wizard-style design where there is only one main authentication input per page.

Username page:
"Type your username now."
[username input]

Password page:
"Type your password now."
[password input]

OTP page:
"Type the six digit code sent to your email."
[OTP input]

Welcome page:
"Welcome, <username>"
[Logout button]

Do not create a registration page.

2. IMPLEMENT KEYBOARD-ONLY OPERATION

A user must be able to complete the entire interface without a mouse.

Requirements:
- Correct semantic form controls.
- Correct <label> elements.
- Main input automatically receives focus when the page loads.
- Pressing Enter submits the current authentication step.
- Natural Tab/Shift+Tab navigation.
- Do not create custom controls when a standard HTML button/input works.
- Logout must also be keyboard accessible.

Do not use JavaScript to decide whether authentication succeeded.

3. IMPLEMENT BROWSER TEXT-TO-SPEECH

Create static/accessibility.js using the browser SpeechSynthesis API.

Each page should speak its main instruction when loaded.

Examples:
- "Type your username now."
- "Type your password now."
- "Type the six digit code sent to your email."
- "Authentication successful. Welcome <username>."

Provide a reusable function rather than duplicating SpeechSynthesis code.

Important:
- Never read the password value aloud.
- Never read the OTP value aloud.
- Do not continuously speak characters as the user types.
- Do not treat text-to-speech as an authentication factor.

4. MAKE THE HTML COMPATIBLE WITH EXISTING SCREEN READERS

We are NOT implementing a screen reader.

Use:
- semantic headings
- explicit form labels
- useful page titles
- sensible button text
- aria-live/status regions where appropriate for server-returned errors
- logical DOM order

Authentication errors should be understandable both visually and through assistive technology.

Do not rely on color, images, icons, or visual placement to communicate critical information.

No significant CSS work is required.

5. TEST YOUR MODULE

Add tests or a clearly reproducible automated/basic test suite for:
- required labels existing
- input autofocus behavior where practical
- correct form actions/methods
- pages having only the expected main authentication input
- accessibility.js being included
- sensitive password/OTP values never being inserted into spoken prompt text

Coordinate only through the agreed template variables and route names.

Do not modify database or authentication algorithms unless a tiny integration change is unavoidable.

Commit your completed work to feature/accessibility-ui with clear commits.
```

---

# Prompt for Member 3 — Password Authentication and Login State

```text
You are Member 3.

Your branch is:

feature/password-flow

Your ownership is username/password authentication and enforcement of the ordered login flow. Do not implement the HTML accessibility layer, PostgreSQL internals, or Resend email logic.

Implement these 5 responsibilities:

1. IMPLEMENT THE USERNAME AND PASSWORD LOGIN ROUTES

Implement the Flask routes/blueprint needed for:

GET /login
POST /login

GET /login/password
POST /login/password

The username step should accept a username and continue to the password step without exposing whether the account exists.

The password step should use the shared database repository to obtain the user and securely verify the stored Argon2/bcrypt password hash.

Never compare plaintext stored passwords because plaintext passwords must never exist in the database.

2. IMPLEMENT A SMALL SERVER-SIDE LOGIN STATE MACHINE

Use the Flask session to enforce the wizard order.

A suitable conceptual sequence is:

start
→ username_submitted
→ password_verified
→ authenticated

Do not trust URL navigation.

Examples:
- Direct visit to /login/password without completing username step must redirect safely.
- Direct visit to /login/otp without password verification must fail/redirect.
- Direct visit to /welcome without full authentication must fail/redirect.

Store only the minimum state necessary.

Do not store plaintext passwords or OTPs in the session.

3. IMPLEMENT SAFE AUTHENTICATION ERRORS

Do not reveal account existence.

Avoid messages such as:
- "Username does not exist"
- "Correct username but wrong password"

Use a generic failure such as:
"Authentication failed. Check your credentials and try again."

After failed authentication, return the user to an appropriate safe step.

Do not leak sensitive information through logs.

4. PROVIDE CLEAN INTERFACES FOR THE OTP MODULE

After successful password verification:
- establish the verified user's internal ID in session state
- move the authentication stage to password_verified
- invoke or redirect into Member 5's OTP flow through a clean interface

Your module must not mark the user as fully authenticated until the OTP module confirms success.

Define helper functions/decorators where useful for checking authentication stages so Member 5 can reuse them.

Avoid circular imports.

5. TEST PASSWORD AND FLOW SECURITY

Write pytest tests covering at least:

- correct username/password reaches OTP stage
- wrong password does not reach OTP stage
- unknown username and wrong password receive equivalent generic errors
- direct access to password page is rejected when the username step was not completed
- direct access to OTP/welcome is rejected before the required stages
- password is never placed into Flask session
- normal session state transitions behave correctly

Use mocks/stubs for database and OTP functionality when necessary so your tests remain focused on your module.

Commit completed work to feature/password-flow with clear commits.
```

---

# Prompt for Member 4 — Neon PostgreSQL Data Layer

```text
You are Member 4.

Your branch is:

feature/neon-database

Your ownership is the Neon PostgreSQL schema and reusable database/repository layer. Do not implement accessibility UI, Flask password-flow decisions, or Resend email delivery.

Implement these 5 responsibilities:

1. CREATE THE POSTGRESQL SCHEMA

Create database/schema.sql for Neon PostgreSQL.

At minimum create a users table containing:

- id
- username
- email
- password_hash
- created_at

username should be unique.
email should be unique.

Also create an OTP challenge table suitable for email OTP verification with fields such as:

- id
- user_id
- otp_hash
- expires_at
- used
- failed_attempts
- created_at
- sent_at

Use appropriate PostgreSQL types, constraints, foreign keys, indexes and sensible defaults.

Do not store plaintext OTPs.

2. IMPLEMENT THE DATABASE CONNECTION LAYER

Create database/db.py.

Use DATABASE_URL from environment/configuration.

The code must work with a Neon PostgreSQL connection string.

Keep connection handling clean:
- open/acquire connection
- commit successful writes
- rollback failures
- close/release resources

Use the PostgreSQL driver selected by the project requirements.

Do not hardcode credentials.

3. IMPLEMENT A REPOSITORY API

Create database/repository.py exposing simple functions for the other members.

Include functions equivalent to:

get_user_by_username(username)
get_user_by_id(user_id)
create_user(username, email, password_hash)

create_otp_challenge(user_id, otp_hash, expires_at)
get_active_otp_challenge(user_id)
increment_otp_attempts(challenge_id)
mark_otp_used(challenge_id)
invalidate_active_otp_challenges(user_id)

You may adjust exact names after checking Member 1's interface contract, but preserve the same functionality.

Return simple Python structures/objects that are easy for other modules to consume.

4. MAKE ALL DATABASE OPERATIONS SAFE

Every query containing user-controlled values must be parameterized.

Do not construct SQL using string concatenation or f-strings containing usernames, emails, OTP-related values, etc.

Ensure:
- used OTPs cannot accidentally be treated as active
- expired challenges can be excluded by repository queries
- a user cannot accidentally be matched to another user's OTP challenge
- uniqueness errors are handled cleanly

Do not put DATABASE_URL into logs.

5. TEST THE DATA LAYER

Create tests for:
- user lookup
- user creation behavior
- duplicate username/email handling
- OTP challenge creation
- active OTP lookup
- OTP invalidation
- mark-as-used behavior
- failed-attempt increment behavior
- parameterized query behavior where practical

Tests should not require editing production credentials.

If integration testing against Neon is inconvenient, separate repository logic cleanly enough to mock the DB in normal tests and document one optional real-database smoke test.

Commit completed work to feature/neon-database with clear commits.
```

---

# Prompt for Member 5 — Email OTP, Resend, and MFA Security

```text
You are Member 5.

Your branch is:

feature/email-otp

Your ownership is the second authentication factor: secure email OTP delivery through Resend, OTP verification, and OTP-specific security testing.

Do not implement password authentication, the PostgreSQL repository itself, or the accessibility HTML layer except for tiny integration changes.

Implement these 5 responsibilities:

1. IMPLEMENT SECURE OTP GENERATION

Create auth/otp.py or an equivalent module.

Generate a six-digit numeric OTP using Python's cryptographically secure `secrets` module.

Do NOT use:
random.randint(...)
or any non-cryptographic random generator.

The OTP should expire after approximately 5 minutes, using the project's configuration value.

Do not store the plaintext OTP in PostgreSQL.

Store only a secure derived representation such as a keyed HMAC/hash so the entered OTP can later be verified.

A newly generated OTP should invalidate any previous active OTP for that login/user.

2. IMPLEMENT RESEND EMAIL DELIVERY

Use the Resend API.

Configuration must come from:
RESEND_API_KEY
RESEND_FROM_EMAIL

The recipient email comes from the authenticated user's database account.

Send a simple screen-reader-friendly email.

Example:

Subject:
Your <Application Name> OTP

Body:
Your <Application Name> OTP is: 687456.
It expires in 5 minutes.
If you did not attempt to sign in, you can ignore this email.

Keep the email simple and understandable as plain text.

Do not log the OTP.

Handle Resend API failures gracefully without crashing the application or exposing API details to the user.

3. IMPLEMENT OTP ROUTES AND VERIFICATION

Implement the Flask OTP portion of the flow, such as:

GET /login/otp
POST /login/otp
POST /login/otp/resend

The OTP page must only be accessible when Member 3's login state indicates password_verified.

On successful OTP verification:
- ensure challenge belongs to the current user
- ensure it is not expired
- ensure it has not been used
- compare safely against the stored OTP hash/HMAC
- mark it used
- change session stage to authenticated
- redirect to /welcome

On failure:
- increment failed attempts
- return a generic understandable error
- do not authenticate

4. IMPLEMENT OTP ABUSE CONTROLS

Implement:
- maximum OTP verification attempts, for example 5
- expiry after configured lifetime
- one-time use
- resend cooldown, for example 60 seconds
- invalidation of the old OTP when a new OTP is issued

Prevent immediate unlimited resend requests.

An OTP successfully used once must fail if submitted again.

Do not allow a code belonging to one user/session to authenticate another user.

5. IMPLEMENT MFA SECURITY TESTS

Write pytest tests covering at least:

- six-digit secure OTP generation
- correct OTP succeeds
- incorrect OTP fails
- expired OTP fails
- used OTP cannot be replayed
- previous OTP becomes invalid after resend
- resend cooldown works
- attempt limit works
- OTP page cannot be used before password verification
- successful OTP changes session state to authenticated
- Resend API is mocked in normal automated tests
- Resend failure is handled safely
- OTP plaintext is not persisted in the database

Coordinate with Member 3's authentication-stage helper and Member 4's repository API instead of duplicating their functionality.

Commit completed work to feature/email-otp with clear commits.
```

This gives each member a distinct code surface:

| Member | Primary ownership                                                |
| ------ | ---------------------------------------------------------------- |
| **1**  | Repository/project foundation, config, provisioning, integration |
| **2**  | Accessible wizard UI, keyboard operation, browser TTS            |
| **3**  | Username/password authentication, session flow enforcement       |
| **4**  | Neon PostgreSQL schema and repository/data layer                 |
| **5**  | Resend email OTP, OTP security controls and MFA tests            |

The separation also minimizes merge conflicts: each member owns mostly different directories/files, while the shared interfaces are defined by Member 1 before implementation begins.
