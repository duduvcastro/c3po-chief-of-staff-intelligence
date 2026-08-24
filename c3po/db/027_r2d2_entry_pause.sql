ALTER TABLE r2d2_experiments
    ADD COLUMN IF NOT EXISTS entries_paused BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS entries_paused_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entries_pause_operator TEXT,
    ADD COLUMN IF NOT EXISTS entries_pause_reason TEXT;
