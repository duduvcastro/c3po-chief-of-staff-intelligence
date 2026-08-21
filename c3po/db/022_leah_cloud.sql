CREATE TABLE IF NOT EXISTS leah_pairing_codes (
    id UUID PRIMARY KEY,
    owner_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leah_pairing_codes_owner
    ON leah_pairing_codes (owner_email, created_at DESC);

CREATE TABLE IF NOT EXISTS leah_devices (
    id UUID PRIMARY KEY,
    owner_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'macOS',
    token_hash TEXT NOT NULL UNIQUE,
    calendar_authorized BOOLEAN NOT NULL DEFAULT FALSE,
    reminders_authorized BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leah_devices_owner
    ON leah_devices (owner_email, revoked_at, created_at DESC);

CREATE TABLE IF NOT EXISTS leah_items (
    id UUID PRIMARY KEY,
    owner_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('event', 'task')),
    external_id TEXT,
    container_id TEXT,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    is_all_day BOOLEAN NOT NULL DEFAULT FALSE,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL CHECK (source IN ('icloud', 'c3po')),
    source_device_id UUID REFERENCES leah_devices(id) ON DELETE SET NULL,
    source_modified_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leah_items_external
    ON leah_items (owner_email, kind, external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_leah_items_owner_updated
    ON leah_items (owner_email, updated_at DESC);
