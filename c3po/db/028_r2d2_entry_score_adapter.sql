ALTER TABLE r2d2_experiments
    ADD COLUMN IF NOT EXISTS policy_epoch TEXT,
    ADD COLUMN IF NOT EXISTS policy_epoch_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entry_score_adapter_version TEXT,
    ADD COLUMN IF NOT EXISTS entry_score_adapter_enabled_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS r2d2_entry_score_observations (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id),
    cycle_id UUID NOT NULL REFERENCES r2d2_cycles(id),
    policy_epoch TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    valuation_basis TEXT,
    quote_as_of TIMESTAMPTZ,
    canonical_composite_score NUMERIC(12, 6),
    canonical_fundamental_score NUMERIC(12, 6),
    canonical_technical_score NUMERIC(12, 6),
    canonical_risk_score NUMERIC(12, 6),
    raw_cash_volume_usd NUMERIC(24, 6),
    spread_bps NUMERIC(18, 6),
    source_references JSONB NOT NULL,
    valuation_comparisons JSONB NOT NULL,
    candidate_context JSONB NOT NULL,
    candidate_sha256 TEXT NOT NULL CHECK (length(candidate_sha256) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, cycle_id, market, symbol)
);

CREATE INDEX IF NOT EXISTS r2d2_entry_score_observations_time
    ON r2d2_entry_score_observations (experiment_id, decision_at DESC);

CREATE OR REPLACE FUNCTION reject_r2d2_entry_score_observation_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'r2d2_entry_score_observations is append-only';
END;
$$;

DROP TRIGGER IF EXISTS r2d2_entry_score_observations_append_only
    ON r2d2_entry_score_observations;

CREATE TRIGGER r2d2_entry_score_observations_append_only
BEFORE UPDATE OR DELETE ON r2d2_entry_score_observations
FOR EACH ROW EXECUTE FUNCTION reject_r2d2_entry_score_observation_mutation();
