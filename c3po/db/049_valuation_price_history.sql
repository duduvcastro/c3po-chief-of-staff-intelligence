-- Valuation Engine V3.2 rev 7, §2.2 / §9.2: the persisted daily price series (`valuation_price_history/<M>`).
-- Labels P_real(T + h) and the realized-error panel read ONLY bars persisted here. Every run is ONE vintage in TWO facts,
-- both rows of analysis_snapshots (no new table):
--   1. the CAPTURE: the manifest (analysis_type = 'valuation_price_history', entity_key = <M>, published_at = fetched_at,
--      stamped after the last provider answer) plus the bars whose CONTENT changed (bar_sha256 hashes the content, not the
--      clock), written in the same transaction (the bars reference the manifest by FK);
--   2. the PUBLICATION, appended only after that transaction committed: analysis_type = 'valuation_price_history_publication',
--      entity_key = <M>, published_at = available_at (a clock read immediately before this insert), inputs
--      {schema_version, price_snapshot_id, fetched_at, started_at, available_at}, outputs {schema_version, bars_sha256,
--      price_snapshot_id}.
-- A package cut C resolves the single vintage by the PUBLICATIONS (the greatest available_at < C of its schema) — never by
-- the capture, so a cut between capture and availability sees nothing, now or later (§2.2: nothing is available before its
-- first persistence; availability is never retro-dated) — loads the manifest by id (attested only when it agrees with the
-- publication AND both carry parseable clocks: fetched_at/from/to and available_at; otherwise manifest_mismatch), and
-- reproduces each symbol's series as "latest row with fetched_at <= that vintage's fetched_at" inside the window MINUS the
-- sessions the manifest recorded as refused for that symbol (outputs.rows_rejected), recomputing every bar's content hash
-- and verifying the per-symbol series hash the manifest recorded: never a mix of vintages, never a live fetch.
-- Both writers serialize per market with SELECT pg_advisory_xact_lock(hashtext('valuation_price_history:' || <M>)) as the
-- first statement of their transaction, then re-read the previous manifest and publication and refuse a capture that does
-- not advance beyond both (two runs racing on the same clock leave exactly one vintage). The capture's dedupe read (the
-- latest bar_sha256 per (symbol, session_date), DISTINCT ON ... ORDER BY fetched_at DESC) runs in that same transaction,
-- after the lock, so two processes can never both see "no row yet" for the same bar. A run with no symbols to fetch, or
-- with no bars for any of them, is refused before any write: an empty vintage never hides the previous one. A publication
-- row must attest the capture it was checked against (inputs.fetched_at parseable and equal to the manifest's clock) and
-- its own availability (inputs.available_at = published_at); a previous publication whose inputs.fetched_at does not
-- parse makes every later writer refuse explicitly, by id (the clock chain cannot be proven), never fail on a parse error.
-- Bars are append-only (row triggers) and cannot be truncated. Nothing here touches V1/V2/V3.

CREATE TABLE IF NOT EXISTS valuation_price_bars (
    id UUID PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    session_date DATE NOT NULL,
    close NUMERIC NOT NULL CHECK (close > 0),
    adjusted_close NUMERIC NOT NULL CHECK (adjusted_close > 0),
    volume NUMERIC,
    currency TEXT NOT NULL,
    source TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    snapshot_id UUID NOT NULL REFERENCES analysis_snapshots(id),
    bar_sha256 TEXT NOT NULL CHECK (bar_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (market, symbol, session_date, source, fetched_at)
);
CREATE INDEX IF NOT EXISTS valuation_price_bars_lookup
    ON valuation_price_bars (market, symbol, session_date, fetched_at DESC);

CREATE OR REPLACE FUNCTION valuation_price_bars_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'valuation_price_bars is append-only (% on %)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valuation_price_bars_append_only ON valuation_price_bars;
CREATE TRIGGER valuation_price_bars_append_only
    BEFORE UPDATE OR DELETE ON valuation_price_bars
    FOR EACH ROW EXECUTE FUNCTION valuation_price_bars_append_only();

CREATE OR REPLACE FUNCTION valuation_price_bars_no_truncate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'valuation_price_bars is append-only (TRUNCATE refused)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valuation_price_bars_no_truncate ON valuation_price_bars;
CREATE TRIGGER valuation_price_bars_no_truncate
    BEFORE TRUNCATE ON valuation_price_bars
    FOR EACH STATEMENT EXECUTE FUNCTION valuation_price_bars_no_truncate();
