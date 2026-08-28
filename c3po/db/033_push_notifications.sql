CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID PRIMARY KEY,
    user_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    endpoint TEXT NOT NULL CHECK (endpoint LIKE 'https://%'),
    p256dh TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    categories TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (
        categories <@ ARRAY[
            'kill_criterion',
            'job_failure',
            'governance_critical',
            'mesa_reading'
        ]::TEXT[]
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS push_subscriptions_active_endpoint_uniq
    ON push_subscriptions(endpoint)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS push_subscriptions_active_user_idx
    ON push_subscriptions(user_email, created_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS push_notification_events (
    event_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    deep_link TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS push_delivery_events (
    id UUID PRIMARY KEY,
    event_key TEXT,
    subscription_id UUID NOT NULL REFERENCES push_subscriptions(id),
    category TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'expired')),
    response_status INTEGER,
    error_class TEXT,
    attempted_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS push_delivery_events_attempted_idx
    ON push_delivery_events(attempted_at DESC);
