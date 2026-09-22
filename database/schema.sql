-- Apply this file with scripts/migrate.py using DATABASE_URL_UNPOOLED.
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN;
UPDATE users SET is_active = COALESCE(is_active, email_verified, TRUE);
UPDATE users SET email_verified = COALESCE(email_verified, is_active, TRUE);
ALTER TABLE users ALTER COLUMN is_active SET DEFAULT FALSE;
ALTER TABLE users ALTER COLUMN email_verified SET DEFAULT FALSE;
ALTER TABLE users ALTER COLUMN is_active SET NOT NULL;
ALTER TABLE users ALTER COLUMN email_verified SET NOT NULL;

CREATE TABLE IF NOT EXISTS signup_drafts (
    id UUID PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(320),
    password_hash TEXT,
    stage VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS signup_drafts_expiry_idx ON signup_drafts (expires_at);
ALTER TABLE signup_drafts ALTER COLUMN email DROP NOT NULL;
ALTER TABLE signup_drafts ALTER COLUMN password_hash DROP NOT NULL;

CREATE TABLE IF NOT EXISTS otp_challenges (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose VARCHAR(32) NOT NULL DEFAULT 'sign_in' CHECK (purpose IN ('sign_in', 'email_verification')),
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);
ALTER TABLE otp_challenges ADD COLUMN IF NOT EXISTS purpose VARCHAR(32);
UPDATE otp_challenges SET purpose = 'sign_in' WHERE purpose IS NULL;
ALTER TABLE otp_challenges ALTER COLUMN purpose SET DEFAULT 'sign_in';
ALTER TABLE otp_challenges ALTER COLUMN purpose SET NOT NULL;
CREATE INDEX IF NOT EXISTS otp_challenges_active_idx ON otp_challenges (user_id, purpose, created_at DESC) WHERE used = FALSE;
CREATE INDEX IF NOT EXISTS otp_challenges_expiry_idx ON otp_challenges (expires_at) WHERE used = FALSE;
