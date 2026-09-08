-- Valuation Engine V3.2 rev 7, §2.2 / §9.2: the persisted daily price series (`valuation_price_history/<M>`).
-- Labels P_real(T + h) and the realized-error panel read ONLY bars persisted here; a package cut C consumes
-- exclusively bars with fetched_at < C (never a live fetch). Bars are append-only: a re-fetch of the same session
-- (adjusted_close changes after splits/dividends) is a NEW row with its own fetched_at — the reader picks the latest
-- fetched_at before its cut, so history is reproducible for any cut. Nothing here touches the V1/V2/V3 engines.

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
