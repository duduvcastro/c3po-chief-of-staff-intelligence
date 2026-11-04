-- The weekly news sentiment moves from Finnhub to Massive (owner 03/11/2026: Finnhub is cut, "usar a Massive"). The
-- "News Sentiment" and "News Mention" rows of the watched US companies are now built from Massive's news API (its
-- per-ticker article insights, in the Stocks Advanced plan already paid) under their own source code, 'massive' -- the
-- same reasoning as 020_ir_events_finnhub_source.sql (market news is neither a regulatory disclosure nor an issuer page).
-- 'finnhub' stays admitted: no row is deleted, and its rows are the history the sentiment readers keep reading
-- (Database.latest_news_sentiment / news_sentiment_at take the latest row of either source). 020 is never rewritten:
-- every start re-runs the whole chain, so this widening is idempotent -- the constraint is replaced only while it does
-- not name 'massive' yet, and 020 then finds 'finnhub' in it and leaves it alone.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'ir_events'::regclass
          AND conname = 'ir_events_source_code_check'
          AND pg_get_constraintdef(oid) NOT LIKE '%massive%'
    ) THEN
        ALTER TABLE ir_events
            DROP CONSTRAINT ir_events_source_code_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'ir_events'::regclass
          AND conname = 'ir_events_source_code_check'
    ) THEN
        ALTER TABLE ir_events
            ADD CONSTRAINT ir_events_source_code_check
            CHECK (source_code IN ('cvm', 'sec', 'ri', 'finnhub', 'massive'));
    END IF;
END
$$;
