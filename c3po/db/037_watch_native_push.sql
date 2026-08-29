CREATE TABLE IF NOT EXISTS watch_device_credentials (
    id UUID PRIMARY KEY,
    user_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    token_sha256 TEXT NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS watch_push_subscriptions (
    id UUID PRIMARY KEY,
    credential_id UUID NOT NULL REFERENCES watch_device_credentials(id),
    user_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    device_token TEXT NOT NULL CHECK (device_token ~ '^[0-9a-f]{64,200}$'),
    categories TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (categories <@ ARRAY[
        'kill_criterion', 'job_failure', 'governance_critical', 'mesa_reading',
        'disk_threshold', 'security_login', 'sell_win', 'hourly_win_rate'
    ]::TEXT[])
);

CREATE UNIQUE INDEX IF NOT EXISTS watch_push_subscriptions_active_credential_uniq
    ON watch_push_subscriptions(credential_id) WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS watch_push_subscriptions_active_device_uniq
    ON watch_push_subscriptions(device_token) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS watch_push_delivery_events (
    id UUID PRIMARY KEY,
    event_key TEXT,
    subscription_id UUID NOT NULL REFERENCES watch_push_subscriptions(id),
    category TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'expired')),
    response_status INTEGER,
    error_class TEXT,
    attempted_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS watch_push_delivery_events_attempted_idx
    ON watch_push_delivery_events(attempted_at DESC);
