CREATE TABLE IF NOT EXISTS access_users (
    email TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    CHECK (email = lower(email)),
    CHECK (jsonb_typeof(permissions) = 'array')
);

CREATE INDEX IF NOT EXISTS access_users_active
    ON access_users (is_active, email);
