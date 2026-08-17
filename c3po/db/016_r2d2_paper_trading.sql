CREATE TABLE IF NOT EXISTS r2d2_experiments (
    id UUID PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'running', 'paused', 'completed')),
    base_currency TEXT NOT NULL DEFAULT 'USD',
    starting_capital NUMERIC(20, 6) NOT NULL CHECK (starting_capital > 0),
    cash_balance NUMERIC(20, 6) NOT NULL CHECK (cash_balance >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    methodology_version TEXT NOT NULL,
    mandate JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS r2d2_positions (
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL,
    quantity NUMERIC(24, 8) NOT NULL CHECK (quantity >= 0),
    average_cost_local NUMERIC(20, 8) NOT NULL CHECK (average_cost_local > 0),
    average_cost_usd NUMERIC(20, 8) NOT NULL CHECK (average_cost_usd > 0),
    last_price_local NUMERIC(20, 8) NOT NULL CHECK (last_price_local > 0),
    fx_to_usd NUMERIC(20, 10) NOT NULL CHECK (fx_to_usd > 0),
    high_water_price_local NUMERIC(20, 8) NOT NULL CHECK (high_water_price_local > 0),
    stop_price_local NUMERIC(20, 8) NOT NULL CHECK (stop_price_local > 0),
    opened_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    strategy_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (experiment_id, market, symbol)
);

CREATE TABLE IF NOT EXISTS r2d2_trades (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    cycle_id UUID,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(24, 8) NOT NULL CHECK (quantity > 0),
    signal_price_local NUMERIC(20, 8) NOT NULL CHECK (signal_price_local > 0),
    fill_price_local NUMERIC(20, 8) NOT NULL CHECK (fill_price_local > 0),
    fx_to_usd NUMERIC(20, 10) NOT NULL CHECK (fx_to_usd > 0),
    gross_value_usd NUMERIC(20, 6) NOT NULL CHECK (gross_value_usd >= 0),
    fees_usd NUMERIC(20, 6) NOT NULL CHECK (fees_usd >= 0),
    slippage_usd NUMERIC(20, 6) NOT NULL CHECK (slippage_usd >= 0),
    realized_pnl_usd NUMERIC(20, 6),
    reason TEXT NOT NULL,
    decision_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    executed_at TIMESTAMPTZ NOT NULL,
    quote_as_of TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS r2d2_trades_experiment_time
    ON r2d2_trades (experiment_id, executed_at DESC);

CREATE TABLE IF NOT EXISTS r2d2_daily_snapshots (
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    session_date DATE NOT NULL,
    nav_usd NUMERIC(20, 6) NOT NULL,
    cash_usd NUMERIC(20, 6) NOT NULL,
    daily_pnl_usd NUMERIC(20, 6) NOT NULL,
    daily_return_percent NUMERIC(12, 6) NOT NULL,
    gross_exposure_usd NUMERIC(20, 6) NOT NULL,
    open_positions INTEGER NOT NULL,
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    benchmark_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (experiment_id, session_date)
);

CREATE TABLE IF NOT EXISTS r2d2_decisions (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    cycle_id UUID NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'HOLD', 'REJECT')),
    fundamental_score NUMERIC(8, 3) NOT NULL,
    technical_score NUMERIC(8, 3) NOT NULL,
    risk_score NUMERIC(8, 3) NOT NULL,
    composite_score NUMERIC(8, 3) NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    trade_id UUID REFERENCES r2d2_trades(id)
);

CREATE INDEX IF NOT EXISTS r2d2_decisions_cycle
    ON r2d2_decisions (experiment_id, cycle_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS r2d2_cycles (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed', 'market_closed', 'scheduled')),
    markets JSONB NOT NULL DEFAULT '[]'::jsonb,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    signal_count INTEGER NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS r2d2_cycles_experiment_time
    ON r2d2_cycles (experiment_id, started_at DESC);
