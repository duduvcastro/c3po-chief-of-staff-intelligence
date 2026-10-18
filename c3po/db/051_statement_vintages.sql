-- Valuation as-filed (owner's direction 2026-10-17): quarterly statements exactly as the regulator received them.
-- Two append-only tables, written by the US front (SEC EDGAR XBRL, app/sec_xbrl.py) and open to the B3 front (CVM):
--   * statement_filings  — one row per regulator document (SEC: an accession, immutable; an amendment is a new
--                          accession with form "…/A", so document_version is 1). accepted_at is the regulator's own
--                          acceptance instant: for SEC the <ACCEPTANCE-DATETIME> of the filing header
--                          (…/<accession>-index-headers.html, America/New_York), never the submissions JSON
--                          acceptanceDateTime, which is NOT true UTC (verified 2026-10-17: it is the real instant plus
--                          the New York UTC offset; json_accepted_raw keeps it as evidence).
--   * statement_vintages — one row per fact per document: (concept, unit, period) as that document reported it. The
--                          same fact re-reported by a later document (a comparative, a restatement) is a NEW row of that
--                          later document; nothing is ever rewritten. is_first_publication is the writer's judgement at
--                          insert time (no earlier accepted_at for the same fact identity); the writers insert each
--                          issuer's documents in acceptance order under a per-issuer advisory lock, so it holds; readers
--                          that need certainty order by accepted_at.
-- A point-in-time read (app/valuation_asfiled.as_of_fundamentals) sees only rows with accepted_at <= as_of.
-- Nothing here changes a served number: the readers are behind C3PO_VALUATION_ASFILED_ENABLED (default off).

CREATE TABLE IF NOT EXISTS statement_filings (
    id UUID PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('US', 'B3')),
    issuer_key TEXT NOT NULL CHECK (issuer_key <> ''),        -- US: the 10-digit SEC CIK
    source TEXT NOT NULL CHECK (source <> ''),                -- US: 'sec_edgar'
    doc_id TEXT NOT NULL CHECK (doc_id <> ''),                -- US: the accession number (0000320193-26-000018)
    document_version INTEGER NOT NULL DEFAULT 1 CHECK (document_version >= 1),
    form TEXT NOT NULL CHECK (form <> ''),
    items TEXT NOT NULL DEFAULT '',                           -- 8-K items as filed ('2.02,9.01'); '' otherwise
    symbols TEXT[] NOT NULL DEFAULT ARRAY[]::text[],          -- universe tickers mapped to the issuer at detection
    period_of_report DATE,
    filed_date DATE NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL,
    accepted_source TEXT NOT NULL CHECK (accepted_source <> ''),  -- US: 'sec_header'
    json_accepted_raw TEXT,                                   -- submissions JSON acceptanceDateTime, verbatim (evidence)
    header_sha256 TEXT CHECK (header_sha256 IS NULL OR header_sha256 ~ '^[0-9a-f]{64}$'),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT statement_filings_natural_key UNIQUE (market, source, doc_id, document_version)
);
CREATE INDEX IF NOT EXISTS statement_filings_issuer
    ON statement_filings (market, issuer_key, accepted_at DESC);
CREATE INDEX IF NOT EXISTS statement_filings_accepted
    ON statement_filings (market, accepted_at DESC);

CREATE TABLE IF NOT EXISTS statement_vintages (
    id UUID PRIMARY KEY,
    market TEXT NOT NULL CHECK (market IN ('US', 'B3')),
    issuer_key TEXT NOT NULL CHECK (issuer_key <> ''),
    source TEXT NOT NULL CHECK (source <> ''),                -- US: 'sec_xbrl_companyfacts'
    doc_id TEXT NOT NULL CHECK (doc_id <> ''),
    document_version INTEGER NOT NULL DEFAULT 1 CHECK (document_version >= 1),
    form TEXT NOT NULL CHECK (form <> ''),
    fiscal_year INTEGER,                                      -- the DOCUMENT's fiscal focus as the regulator reports it
    fiscal_period TEXT,                                       -- ('FY', 'Q1'…); the fact's own period: period_start/end
    period_start DATE,                                        -- NULL for an instant (balance-sheet / cover-page) fact
    period_end DATE NOT NULL,
    concept TEXT NOT NULL CHECK (concept <> ''),              -- taxonomy-qualified: 'us-gaap:Revenues', 'dei:…'
    unit TEXT NOT NULL CHECK (unit <> ''),
    value NUMERIC NOT NULL,
    filed_date DATE NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_first_publication BOOLEAN NOT NULL,
    row_hash TEXT NOT NULL CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT statement_vintages_period CHECK (period_start IS NULL OR period_start <= period_end),
    -- PostgreSQL 16: an instant fact (period_start NULL) is still ONE row per document
    CONSTRAINT statement_vintages_natural_key UNIQUE NULLS NOT DISTINCT
        (market, issuer_key, source, doc_id, document_version, concept, unit, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS statement_vintages_point_in_time
    ON statement_vintages (market, issuer_key, concept, accepted_at);
CREATE INDEX IF NOT EXISTS statement_vintages_by_doc
    ON statement_vintages (market, source, doc_id);

CREATE OR REPLACE FUNCTION statement_vintages_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'statement filings and vintages are append-only (% on %)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS statement_filings_append_only ON statement_filings;
CREATE TRIGGER statement_filings_append_only
    BEFORE UPDATE OR DELETE ON statement_filings
    FOR EACH ROW EXECUTE FUNCTION statement_vintages_append_only();

DROP TRIGGER IF EXISTS statement_filings_no_truncate ON statement_filings;
CREATE TRIGGER statement_filings_no_truncate
    BEFORE TRUNCATE ON statement_filings
    FOR EACH STATEMENT EXECUTE FUNCTION statement_vintages_append_only();

DROP TRIGGER IF EXISTS statement_vintages_append_only ON statement_vintages;
CREATE TRIGGER statement_vintages_append_only
    BEFORE UPDATE OR DELETE ON statement_vintages
    FOR EACH ROW EXECUTE FUNCTION statement_vintages_append_only();

DROP TRIGGER IF EXISTS statement_vintages_no_truncate ON statement_vintages;
CREATE TRIGGER statement_vintages_no_truncate
    BEFORE TRUNCATE ON statement_vintages
    FOR EACH STATEMENT EXECUTE FUNCTION statement_vintages_append_only();
