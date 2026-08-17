CREATE TABLE IF NOT EXISTS alert_reads (
    user_email TEXT NOT NULL REFERENCES access_users(email) ON DELETE CASCADE,
    alert_id TEXT NOT NULL,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_email, alert_id)
);

CREATE INDEX IF NOT EXISTS alert_reads_user_time
    ON alert_reads (user_email, read_at DESC);
