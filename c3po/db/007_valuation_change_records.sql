CREATE TABLE IF NOT EXISTS valuation_change_records (
    id UUID PRIMARY KEY,
    snapshot_id UUID REFERENCES analysis_snapshots(id) ON DELETE SET NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'US')),
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN ('initial', 'financial_results', 'material_event', 'web_research', 'market_data', 'methodology')
    ),
    trigger_title TEXT NOT NULL,
    trigger_summary TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    currency TEXT NOT NULL DEFAULT 'BRL',
    old_tp NUMERIC,
    new_tp NUMERIC NOT NULL,
    tp_change_percent NUMERIC,
    old_buy_in NUMERIC,
    new_buy_in NUMERIC,
    old_consensus_tp NUMERIC,
    new_consensus_tp NUMERIC,
    price NUMERIC,
    old_confidence NUMERIC,
    new_confidence NUMERIC,
    methodology_name TEXT NOT NULL DEFAULT 'C3PO Valuation Model',
    methodology_version INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS valuation_change_snapshot_symbol
    ON valuation_change_records (snapshot_id, market, symbol)
    WHERE snapshot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS valuation_change_chronology
    ON valuation_change_records (changed_at DESC, symbol);

CREATE INDEX IF NOT EXISTS valuation_change_company_history
    ON valuation_change_records (market, symbol, changed_at DESC);
