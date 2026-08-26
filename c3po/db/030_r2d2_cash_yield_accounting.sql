CREATE TABLE IF NOT EXISTS r2d2_cash_yield_ledger (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    prior_session_date DATE NOT NULL,
    base_cash_usd NUMERIC(20, 6) NOT NULL CHECK (base_cash_usd >= 0),
    annual_coupon_equivalent_rate NUMERIC(14, 10) NOT NULL CHECK (annual_coupon_equivalent_rate >= 0),
    calendar_days INTEGER NOT NULL CHECK (calendar_days > 0),
    daily_factor NUMERIC(18, 14) NOT NULL CHECK (daily_factor >= 0),
    interest_income_usd NUMERIC(20, 6) NOT NULL CHECK (interest_income_usd >= 0),
    source_name TEXT NOT NULL,
    source_series TEXT NOT NULL,
    source_observation_date DATE NOT NULL,
    source_available_at TIMESTAMPTZ NOT NULL,
    source_fetched_at TIMESTAMPTZ NOT NULL,
    source_payload_sha256 TEXT NOT NULL CHECK (source_payload_sha256 ~ '^[0-9a-f]{64}$'),
    entry_sha256 TEXT NOT NULL CHECK (entry_sha256 ~ '^[0-9a-f]{64}$'),
    backfilled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, session_date),
    CHECK (session_date > prior_session_date),
    CHECK (source_observation_date = prior_session_date),
    CHECK (source_available_at <= source_fetched_at)
);

CREATE INDEX IF NOT EXISTS r2d2_cash_yield_ledger_experiment_date
    ON r2d2_cash_yield_ledger (experiment_id, session_date DESC);

CREATE OR REPLACE FUNCTION reject_r2d2_cash_yield_ledger_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'r2d2_cash_yield_ledger is append-only';
END;
$$;

DROP TRIGGER IF EXISTS r2d2_cash_yield_ledger_append_only ON r2d2_cash_yield_ledger;
CREATE TRIGGER r2d2_cash_yield_ledger_append_only
BEFORE UPDATE OR DELETE ON r2d2_cash_yield_ledger
FOR EACH ROW EXECUTE FUNCTION reject_r2d2_cash_yield_ledger_mutation();
