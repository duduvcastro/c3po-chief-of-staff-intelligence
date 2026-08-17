ALTER TABLE r2d2_experiments
    ADD COLUMN IF NOT EXISTS checkpoint_date DATE;

UPDATE r2d2_experiments
SET checkpoint_date = end_date
WHERE checkpoint_date IS NULL;

ALTER TABLE r2d2_experiments
    ALTER COLUMN checkpoint_date SET NOT NULL;

ALTER TABLE r2d2_experiments
    ADD COLUMN IF NOT EXISTS is_continuous BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE r2d2_experiments
SET status = CASE
        WHEN status = 'paused' THEN 'paused'
        WHEN (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date < start_date THEN 'scheduled'
        ELSE 'running'
    END,
    is_continuous = TRUE,
    updated_at = now()
WHERE status = 'completed' OR is_continuous IS DISTINCT FROM TRUE;

CREATE TABLE IF NOT EXISTS r2d2_learning_states (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    effective_date DATE NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    sample_days INTEGER NOT NULL DEFAULT 0 CHECK (sample_days >= 0),
    sample_trades INTEGER NOT NULL DEFAULT 0 CHECK (sample_trades >= 0),
    parameters JSONB NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    rationale JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, effective_date),
    UNIQUE (experiment_id, version)
);

CREATE INDEX IF NOT EXISTS r2d2_learning_states_experiment_date
    ON r2d2_learning_states (experiment_id, effective_date DESC);
