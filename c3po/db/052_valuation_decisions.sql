-- Valuation Decisor V1 (shadow) — owner's direction of 2026-10-17: the Valuation becomes the buy/no-buy decider.
-- One IMMUTABLE record per (decision run, market, symbol): COMPRA_PERMITIDA / OBSERVAR / VETO with its reason codes, the
-- official TP record it read (generation, cycle, row hash, prediction instant — the served row, internal when served),
-- the measured error and the market hurdle it applied, the hash of the thresholds block (frozen by the PREREG) and the
-- provenance of every input (inputs JSONB + inputs_sha256). Same discipline as valuation_predictions (048):
--   * two clocks — prediction_instant (when the verdict was made) and published_at (when the record became available,
--     read immediately before the insert; never before the verdict: the CHECK forbids it);
--   * the canonical row_sha256 of every other column, recomputed and verified by every reader (a row that does not
--     verify is never served);
--   * append-only: no UPDATE, DELETE or TRUNCATE (row and statement triggers).
-- mode is 'shadow' only: a verdict that ACTS needs a new migration and a new order. Nothing here touches R2D2 tables,
-- orders, positions or the official selection; the decisor reads the selection and never writes it.

CREATE TABLE IF NOT EXISTS valuation_decisions (
    id UUID PRIMARY KEY,
    record_schema TEXT NOT NULL,
    decisor_version TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('shadow')),
    run_id UUID NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    session_date DATE NOT NULL,                -- the last COMPLETED session of the market's calendar at prediction_instant
    prediction_instant TIMESTAMPTZ NOT NULL,   -- when the verdict was made (the run's clock)
    published_at TIMESTAMPTZ NOT NULL CONSTRAINT valuation_decisions_published_at_check CHECK (published_at >= prediction_instant),
    verdict TEXT NOT NULL CHECK (verdict IN ('COMPRA_PERMITIDA', 'OBSERVAR', 'VETO')),
    reason_codes JSONB NOT NULL CHECK (jsonb_typeof(reason_codes) = 'array'),
    generation_id UUID NOT NULL REFERENCES valuation_official_selection(generation_id),
    tp_source TEXT NOT NULL,
    tp_cycle_id UUID NOT NULL REFERENCES analysis_snapshots(id),
    tp_row_sha256 TEXT NOT NULL CHECK (tp_row_sha256 ~ '^[0-9a-f]{64}$'),
    tp_prediction_instant TIMESTAMPTZ NOT NULL,
    tp NUMERIC NOT NULL CHECK (tp > 0),
    buy_in NUMERIC NOT NULL CHECK (buy_in > 0),
    price NUMERIC CHECK (price > 0),
    e_profile NUMERIC CHECK (e_profile >= 0),
    h_market NUMERIC,
    thresholds_sha256 TEXT NOT NULL CHECK (thresholds_sha256 ~ '^[0-9a-f]{64}$'),
    inputs JSONB NOT NULL,
    inputs_sha256 TEXT NOT NULL CHECK (inputs_sha256 ~ '^[0-9a-f]{64}$'),
    checks JSONB NOT NULL,
    row_sha256 TEXT NOT NULL CHECK (row_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, market, symbol)
);
-- the R2D2 lab reads the latest verdict of the symbols it asks for (DISTINCT ON symbol, newest first)
CREATE INDEX IF NOT EXISTS valuation_decisions_lookup
    ON valuation_decisions (market, symbol, prediction_instant DESC, published_at DESC, created_at DESC);
-- the nightly phase asks for the latest run (its generation decides whether the night is done)
CREATE INDEX IF NOT EXISTS valuation_decisions_published
    ON valuation_decisions (published_at DESC, created_at DESC);

CREATE OR REPLACE FUNCTION valuation_decisions_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'valuation_decisions is append-only (% on %)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valuation_decisions_append_only ON valuation_decisions;
CREATE TRIGGER valuation_decisions_append_only
    BEFORE UPDATE OR DELETE ON valuation_decisions
    FOR EACH ROW EXECUTE FUNCTION valuation_decisions_append_only();

DROP TRIGGER IF EXISTS valuation_decisions_no_truncate ON valuation_decisions;
CREATE TRIGGER valuation_decisions_no_truncate
    BEFORE TRUNCATE ON valuation_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION valuation_decisions_append_only();
