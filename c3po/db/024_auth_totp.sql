ALTER TABLE auth_login_codes
    ADD COLUMN IF NOT EXISTS verification_method TEXT NOT NULL DEFAULT 'email'
    CHECK (verification_method IN ('email', 'totp'));

CREATE TABLE IF NOT EXISTS auth_totp_credentials (
    email TEXT PRIMARY KEY REFERENCES access_users(email) ON DELETE CASCADE,
    encrypted_secret TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ,
    setup_expires_at TIMESTAMPTZ NOT NULL,
    last_used_step BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

