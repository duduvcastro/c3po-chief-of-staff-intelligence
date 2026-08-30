CREATE TABLE IF NOT EXISTS r2d2_shadow_candidates (
    id UUID PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (
        schema_version = 'R2D2-SHADOW-CANDIDATE-OBSERVATION-v1'
    ),
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id),
    cycle_id UUID NOT NULL REFERENCES r2d2_cycles(id),
    session_date DATE NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL CHECK (length(btrim(symbol)) > 0),
    policy_epoch TEXT NOT NULL CHECK (length(btrim(policy_epoch)) > 0),
    cascade_step TEXT NOT NULL CHECK (
        cascade_step IN (
            'technical_review_capacity',
            'daily_order_capacity',
            'portfolio_capacity',
            'session_reentry_policy',
            'entry_quality',
            'entry_execution'
        )
    ),
    reason_id TEXT NOT NULL CHECK (length(btrim(reason_id)) > 0),
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    rejection_class TEXT NOT NULL CHECK (
        rejection_class IN ('quality', 'capacity', 'none')
    ),
    quality_rejected BOOLEAN NOT NULL,
    capacity_rejected BOOLEAN NOT NULL,
    reason_detail JSONB NOT NULL DEFAULT '[]'::jsonb,
    point_in_time JSONB NOT NULL,
    trade_id UUID REFERENCES r2d2_trades(id),
    candidate_sha256 TEXT NOT NULL CHECK (length(candidate_sha256) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (decision = 'accepted'
            AND rejection_class = 'none'
            AND NOT quality_rejected
            AND NOT capacity_rejected
            AND trade_id IS NOT NULL)
        OR
        (decision = 'rejected'
            AND rejection_class IN ('quality', 'capacity')
            AND quality_rejected = (rejection_class = 'quality')
            AND capacity_rejected = (rejection_class = 'capacity')
            AND trade_id IS NULL)
    ),
    UNIQUE (experiment_id, session_date, market, symbol, policy_epoch, decision)
);

CREATE INDEX IF NOT EXISTS r2d2_shadow_candidates_session
    ON r2d2_shadow_candidates (experiment_id, session_date, observed_at, market, symbol);

CREATE TABLE IF NOT EXISTS r2d2_shadow_candidate_outcomes (
    id UUID PRIMARY KEY,
    candidate_id UUID NOT NULL UNIQUE REFERENCES r2d2_shadow_candidates(id),
    session_date DATE NOT NULL,
    coverage_classification TEXT NOT NULL CHECK (
        coverage_classification IN (
            'available', 'bar_unavailable', 'market_compatibility_violation'
        )
    ),
    barrier_category TEXT CHECK (
        barrier_category IN ('upper_first', 'lower_first', 'ambiguous_same_bar', 'censored')
    ),
    counterfactual_r NUMERIC(8, 4),
    outcome_payload JSONB NOT NULL,
    outcome_sha256 TEXT NOT NULL CHECK (length(outcome_sha256) = 64),
    measured_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (coverage_classification = 'available' AND barrier_category IS NOT NULL)
        OR
        (coverage_classification <> 'available'
            AND barrier_category IS NULL
            AND counterfactual_r IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS r2d2_shadow_candidate_outcomes_session
    ON r2d2_shadow_candidate_outcomes (session_date, coverage_classification, barrier_category);

CREATE TABLE IF NOT EXISTS r2d2_shadow_candidate_reports (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id),
    session_date DATE NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    jsonl_sha256 TEXT NOT NULL CHECK (length(jsonl_sha256) = 64),
    report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
    output_path TEXT NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, session_date)
);

CREATE OR REPLACE FUNCTION reject_r2d2_shadow_candidate_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS r2d2_shadow_candidates_append_only
    ON r2d2_shadow_candidates;
CREATE TRIGGER r2d2_shadow_candidates_append_only
BEFORE UPDATE OR DELETE ON r2d2_shadow_candidates
FOR EACH ROW EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();

DROP TRIGGER IF EXISTS r2d2_shadow_candidates_no_truncate
    ON r2d2_shadow_candidates;
CREATE TRIGGER r2d2_shadow_candidates_no_truncate
BEFORE TRUNCATE ON r2d2_shadow_candidates
FOR EACH STATEMENT EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();

DROP TRIGGER IF EXISTS r2d2_shadow_candidate_outcomes_append_only
    ON r2d2_shadow_candidate_outcomes;
CREATE TRIGGER r2d2_shadow_candidate_outcomes_append_only
BEFORE UPDATE OR DELETE ON r2d2_shadow_candidate_outcomes
FOR EACH ROW EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();

DROP TRIGGER IF EXISTS r2d2_shadow_candidate_outcomes_no_truncate
    ON r2d2_shadow_candidate_outcomes;
CREATE TRIGGER r2d2_shadow_candidate_outcomes_no_truncate
BEFORE TRUNCATE ON r2d2_shadow_candidate_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();

DROP TRIGGER IF EXISTS r2d2_shadow_candidate_reports_append_only
    ON r2d2_shadow_candidate_reports;
CREATE TRIGGER r2d2_shadow_candidate_reports_append_only
BEFORE UPDATE OR DELETE ON r2d2_shadow_candidate_reports
FOR EACH ROW EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();

DROP TRIGGER IF EXISTS r2d2_shadow_candidate_reports_no_truncate
    ON r2d2_shadow_candidate_reports;
CREATE TRIGGER r2d2_shadow_candidate_reports_no_truncate
BEFORE TRUNCATE ON r2d2_shadow_candidate_reports
FOR EACH STATEMENT EXECUTE FUNCTION reject_r2d2_shadow_candidate_mutation();
