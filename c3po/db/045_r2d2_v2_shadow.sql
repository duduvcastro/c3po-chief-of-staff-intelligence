-- V2 is isolated from R2D2 positions, orders, V1 candidate logs and controls.
-- Runtime collector never executes schema migrations or changes V1 state.
CREATE TABLE IF NOT EXISTS r2d2_v2_shadow_epochs (
    epoch TEXT PRIMARY KEY CHECK (epoch ~ '^R2D2-V2-(SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}$'),
    manifest_sha TEXT NOT NULL CHECK (manifest_sha ~ '^[0-9a-f]{64}$'),
    state JSONB NOT NULL,
    state_sha TEXT NOT NULL CHECK (state_sha ~ '^[0-9a-f]{64}$'),
    version BIGINT NOT NULL DEFAULT 0,
    journal_head TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS r2d2_v2_shadow_journal (
    epoch TEXT NOT NULL REFERENCES r2d2_v2_shadow_epochs(epoch),
    sequence BIGINT NOT NULL,
    journal_key TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    previous_sha TEXT NOT NULL,
    record_sha TEXT NOT NULL CHECK (record_sha ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (epoch, sequence),
    UNIQUE (epoch, journal_key)
);
CREATE INDEX IF NOT EXISTS r2d2_v2_shadow_journal_recorded
    ON r2d2_v2_shadow_journal(epoch, recorded_at);
