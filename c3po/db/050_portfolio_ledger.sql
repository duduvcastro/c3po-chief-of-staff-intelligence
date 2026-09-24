-- Personal portfolio only. No trading engine or policy changes.
CREATE TABLE IF NOT EXISTS realtime_portfolio_events (
    sequence BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3','NASDAQ','NYSE','OTC')),
    kind TEXT NOT NULL CHECK (kind IN ('position','buy','sell','dividend','split')),
    effective_date DATE NOT NULL,
    quantity NUMERIC(28,10) NOT NULL CHECK (quantity >= 0),
    total NUMERIC(28,10) NOT NULL CHECK (total >= 0),
    fees NUMERIC(28,10) NOT NULL CHECK (fees >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS realtime_portfolio_events_date
ON realtime_portfolio_events(effective_date, sequence) WHERE voided_at IS NULL;
-- No FK cascade: removing a symbol from the watchlist must not erase its financial history.

-- Runs at API/worker startup with the other schema migrations; deploy window required.
ALTER TABLE realtime_portfolio_events ADD COLUMN IF NOT EXISTS split_denominator NUMERIC(18,0) NOT NULL DEFAULT 1 CHECK (split_denominator > 0);
