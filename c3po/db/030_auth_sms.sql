DO $$
DECLARE
    verification_check TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid)
      INTO verification_check
      FROM pg_constraint
     WHERE conrelid = 'auth_login_codes'::regclass
       AND conname = 'auth_login_codes_verification_method_check';

    IF verification_check IS NULL OR position('sms' IN verification_check) = 0 THEN
        ALTER TABLE auth_login_codes
            DROP CONSTRAINT IF EXISTS auth_login_codes_verification_method_check;
        ALTER TABLE auth_login_codes
            ADD CONSTRAINT auth_login_codes_verification_method_check
            CHECK (verification_method IN ('email', 'totp', 'sms'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS auth_sms_credentials (
    email TEXT PRIMARY KEY REFERENCES access_users(email) ON DELETE CASCADE,
    encrypted_phone TEXT,
    phone_last4 TEXT,
    confirmed_at TIMESTAMPTZ,
    pending_encrypted_phone TEXT,
    pending_phone_last4 TEXT,
    pending_setup_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (phone_last4 IS NULL OR phone_last4 ~ '^[0-9]{4}$'),
    CHECK (pending_phone_last4 IS NULL OR pending_phone_last4 ~ '^[0-9]{4}$'),
    CHECK (
        (confirmed_at IS NULL AND encrypted_phone IS NULL AND phone_last4 IS NULL)
        OR (confirmed_at IS NOT NULL AND encrypted_phone IS NOT NULL AND phone_last4 IS NOT NULL)
    )
);
