-- Finnhub news/sentiment is genuinely different in kind from the existing
-- ir_events sources: 'cvm'/'sec' are official regulatory disclosures, 'ri'
-- is issuer-controlled but still official; general market news/sentiment is
-- neither. Reusing "sec" for it (as the earlier insider-transactions PR did,
-- correctly, since that data *is* SEC Form 3/4/5-derived) would misrepresent
-- authority here -- feed()'s own methodology text says "CVM Dados Abertos
-- and SEC EDGAR are authoritative". So this widens the check constraint
-- instead of reusing an existing value, learned from the 2026-08-18 outage:
-- verify every constraint on a column before writing a new value into it.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'ir_events'::regclass
          AND conname = 'ir_events_source_code_check'
          AND pg_get_constraintdef(oid) NOT LIKE '%finnhub%'
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
            CHECK (source_code IN ('cvm', 'sec', 'ri', 'finnhub'));
    END IF;
END
$$;
