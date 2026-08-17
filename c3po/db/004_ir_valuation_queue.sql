CREATE TABLE IF NOT EXISTS ir_valuation_queue (
    event_id UUID NOT NULL REFERENCES ir_events(id) ON DELETE CASCADE,
    market TEXT NOT NULL CHECK (market IN ('B3', 'US')),
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'applied', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, market, symbol)
);

CREATE INDEX IF NOT EXISTS ir_valuation_queue_pending
    ON ir_valuation_queue (status, queued_at)
    WHERE status IN ('queued', 'processing');

-- Existing disclosures are represented by the valuation snapshot created before
-- this migration. Only disclosures discovered after deployment enter as queued.
INSERT INTO ir_valuation_queue (event_id, market, symbol, status, processed_at)
SELECT event.id, security.market, security.symbol, 'applied', now()
FROM ir_events event
JOIN ir_security_map security ON security.company_id = event.company_id
WHERE event.valuation_relevant
ON CONFLICT (event_id, market, symbol) DO NOTHING;
