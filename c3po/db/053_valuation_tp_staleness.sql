-- Valuation as-filed (owner's direction 2026-10-17), US revaluation trigger (app/valuation_asfiled.py, run by
-- app/ir_valuation.py and the nightly cut): an accepted 10-Q/10-K (and their amendments) or an 8-K carrying item 2.02
-- marks the official US target price of the issuer's symbols STALE when that TP was predicted before the filing's
-- acceptance or its fundamentals predate the period the filing reports (expected_period_end), and queues it for the
-- next nightly cut. Append-only: a mark is never updated — the cut that revalues it appends a 'cleared' row for the
-- same (doc_id, symbol).
--   stale     — the official TP does not reflect the filing yet; queued_for_cut_at is the next nightly cut
--   cleared   — a cycle predicted after the acceptance whose fundamentals reach expected_period_end
--   untracked — the symbol had no official TP when the filing was evaluated (not terminal: re-evaluated in the lookback)
-- Behind C3PO_VALUATION_ASFILED_ENABLED (default off); no served number reads this table.

CREATE TABLE IF NOT EXISTS valuation_tp_staleness (
    id UUID PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('US', 'NASDAQ', 'NYSE')),  -- the official market of the TP ('US' when untracked)
    symbol TEXT NOT NULL CHECK (symbol <> ''),
    issuer_key TEXT NOT NULL CHECK (issuer_key <> ''),               -- the 10-digit SEC CIK
    doc_id TEXT NOT NULL CHECK (doc_id <> ''),                       -- the accession (statement_filings.doc_id)
    form TEXT NOT NULL,
    items TEXT NOT NULL DEFAULT '',
    accepted_at TIMESTAMPTZ NOT NULL,                                -- the filing header's acceptance instant
    period_of_report DATE,
    state TEXT NOT NULL CHECK (state IN ('stale', 'cleared', 'untracked')),
    reason TEXT NOT NULL CHECK (reason <> ''),
    official_cycle_id TEXT,                                          -- the cycle whose record was compared
    prediction_instant TIMESTAMPTZ,
    fundamentals_as_of DATE,
    expected_period_end DATE,                                        -- 10-Q/10-K: filed period; 8-K 2.02: announced quarter
    covers_period BOOLEAN,                                           -- fundamentals reach expected_period_end (NULL untracked)
    queued_for_cut_at TIMESTAMPTZ,                                   -- 'stale' only: the nightly cut it waits for
    recorded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valuation_tp_staleness_once UNIQUE (doc_id, symbol, state)
);
CREATE INDEX IF NOT EXISTS valuation_tp_staleness_symbol
    ON valuation_tp_staleness (symbol, accepted_at DESC);
CREATE INDEX IF NOT EXISTS valuation_tp_staleness_recorded
    ON valuation_tp_staleness (recorded_at DESC);

CREATE OR REPLACE FUNCTION valuation_tp_staleness_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'valuation_tp_staleness is append-only (% on %)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valuation_tp_staleness_append_only ON valuation_tp_staleness;
CREATE TRIGGER valuation_tp_staleness_append_only
    BEFORE UPDATE OR DELETE ON valuation_tp_staleness
    FOR EACH ROW EXECUTE FUNCTION valuation_tp_staleness_append_only();

DROP TRIGGER IF EXISTS valuation_tp_staleness_no_truncate ON valuation_tp_staleness;
CREATE TRIGGER valuation_tp_staleness_no_truncate
    BEFORE TRUNCATE ON valuation_tp_staleness
    FOR EACH STATEMENT EXECUTE FUNCTION valuation_tp_staleness_append_only();
