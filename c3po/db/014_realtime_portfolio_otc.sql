DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'realtime_portfolio'::regclass
          AND conname = 'realtime_portfolio_market_check'
          AND pg_get_constraintdef(oid) NOT LIKE '%OTC%'
    ) THEN
        ALTER TABLE realtime_portfolio
            DROP CONSTRAINT realtime_portfolio_market_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'realtime_portfolio'::regclass
          AND conname = 'realtime_portfolio_market_check'
    ) THEN
        ALTER TABLE realtime_portfolio
            ADD CONSTRAINT realtime_portfolio_market_check
            CHECK (market IN ('B3', 'NASDAQ', 'NYSE', 'OTC'));
    END IF;
END
$$;
