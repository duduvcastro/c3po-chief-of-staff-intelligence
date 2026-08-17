CREATE INDEX IF NOT EXISTS audit_events_action_feed
    ON audit_events (action, occurred_at DESC);
