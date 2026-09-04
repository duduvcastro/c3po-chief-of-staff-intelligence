CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES data_sources(id),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    records_read INTEGER NOT NULL DEFAULT 0,
    records_written INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS observations (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES data_sources(id),
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    metric TEXT NOT NULL,
    value JSONB NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    quality_score SMALLINT NOT NULL CHECK (quality_score BETWEEN 0 AND 100),
    raw_reference TEXT,
    ingestion_run_id UUID REFERENCES ingestion_runs(id),
    UNIQUE (source_id, entity_type, entity_key, metric, as_of)
);

CREATE INDEX IF NOT EXISTS observations_entity_lookup
    ON observations (entity_type, entity_key, metric, as_of DESC);

CREATE TABLE IF NOT EXISTS methodology_versions (
    id UUID PRIMARY KEY,
    methodology_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
    parameters JSONB NOT NULL,
    rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ,
    UNIQUE (methodology_key, version)
);

CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id UUID PRIMARY KEY,
    analysis_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    methodology_version_id UUID REFERENCES methodology_versions(id),
    inputs JSONB NOT NULL,
    outputs JSONB NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    supersedes_id UUID REFERENCES analysis_snapshots(id)
);

CREATE INDEX IF NOT EXISTS analysis_snapshot_lookup
    ON analysis_snapshots (analysis_type, entity_key, published_at DESC);

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT NOT NULL DEFAULT '',
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_login_codes (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0,
    max_attempts SMALLINT NOT NULL DEFAULT 5,
    used_at TIMESTAMPTZ,
    requested_ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS auth_login_codes_rate_limit
    ON auth_login_codes (email, created_at DESC);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_ip TEXT NOT NULL DEFAULT '',
    idle_timeout_seconds INTEGER NOT NULL DEFAULT 1800 CHECK (
        idle_timeout_seconds BETWEEN 60 AND 86400
    ),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS auth_sessions_lookup
    ON auth_sessions (token_hash, expires_at);

CREATE TABLE IF NOT EXISTS realtime_portfolio (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE', 'OTC')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS realtime_portfolio_market
    ON realtime_portfolio (market, symbol);
