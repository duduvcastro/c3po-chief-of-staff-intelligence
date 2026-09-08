-- Valuation Engine V3.2 rev 7, §2.2 / §9.2: the persisted daily price series (`valuation_price_history/<M>`).
-- Labels P_real(T + h) and the realized-error panel read ONLY bars persisted here. Every run is ONE vintage: a manifest
-- in analysis_snapshots (published_at = fetched_at of the run, stamped after the last provider answer) plus the bars whose
-- CONTENT changed (bar_sha256 hashes the content, not the clock), written in the same transaction. A package cut C
-- resolves the single vintage with the greatest fetched_at < C and reproduces each symbol's series as "latest row with
-- fetched_at <= that vintage's fetched_at", verified against the per-symbol hash the manifest recorded — never a mix of
-- vintages, never a live fetch. Bars are append-only (row triggers) and cannot be truncated. Nothing here touches V1/V2/V3.

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
