ALTER TABLE auth_totp_credentials
    ADD COLUMN IF NOT EXISTS pending_encrypted_secret TEXT,
    ADD COLUMN IF NOT EXISTS pending_setup_expires_at TIMESTAMPTZ;
