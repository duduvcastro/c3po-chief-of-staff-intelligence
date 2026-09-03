ALTER TABLE auth_sessions
    ADD COLUMN IF NOT EXISTS idle_timeout_seconds INTEGER NOT NULL DEFAULT 1800
    CHECK (idle_timeout_seconds BETWEEN 60 AND 86400);
