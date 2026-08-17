CREATE TABLE IF NOT EXISTS ir_companies (
    id UUID PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('B3', 'US')),
    company_name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    regulator_id TEXT,
    tax_id TEXT,
    exchange TEXT,
    ri_url TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (market, name_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS ir_companies_regulator
    ON ir_companies (market, regulator_id)
    WHERE regulator_id IS NOT NULL AND regulator_id <> '';

CREATE TABLE IF NOT EXISTS ir_security_map (
    market TEXT NOT NULL CHECK (market IN ('B3', 'US')),
    symbol TEXT NOT NULL,
    company_id UUID NOT NULL REFERENCES ir_companies(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market, symbol)
);

CREATE INDEX IF NOT EXISTS ir_security_company
    ON ir_security_map (company_id);

CREATE TABLE IF NOT EXISTS ir_events (
    id UUID PRIMARY KEY,
    source_code TEXT NOT NULL CHECK (source_code IN ('cvm', 'sec', 'ri')),
    external_id TEXT NOT NULL,
    company_id UUID REFERENCES ir_companies(id) ON DELETE SET NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'US')),
    symbol TEXT,
    company_name TEXT NOT NULL,
    regulator_id TEXT,
    event_type TEXT NOT NULL,
    form TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ NOT NULL,
    published_time_precision TEXT NOT NULL DEFAULT 'datetime'
        CHECK (published_time_precision IN ('datetime', 'date', 'collected')),
    reference_date DATE,
    official_url TEXT NOT NULL,
    document_url TEXT,
    materiality TEXT NOT NULL DEFAULT 'medium'
        CHECK (materiality IN ('high', 'medium', 'low')),
    valuation_relevant BOOLEAN NOT NULL DEFAULT FALSE,
    valuation_status TEXT NOT NULL DEFAULT 'informational'
        CHECK (valuation_status IN ('pending_review', 'incorporated', 'informational')),
    reviewed_at TIMESTAMPTZ,
    review_note TEXT NOT NULL DEFAULT '',
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_code, external_id)
);

CREATE INDEX IF NOT EXISTS ir_events_feed
    ON ir_events (published_at DESC, source_code, market);

CREATE INDEX IF NOT EXISTS ir_events_company
    ON ir_events (company_id, valuation_relevant, published_at DESC);

CREATE INDEX IF NOT EXISTS ir_events_symbol
    ON ir_events (market, symbol, valuation_relevant, published_at DESC);

CREATE TABLE IF NOT EXISTS ir_report_exports (
    id UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    event_count INTEGER NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
