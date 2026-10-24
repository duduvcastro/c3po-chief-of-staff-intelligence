-- Ben Kenobi Records records the SERVED official TP (Valuation V3.2 rev 7 §7-bis, the owner's "um só para tudo"): from this
-- migration on, the application appends a record when the official selection changes what it serves (Database.
-- capture_served_valuation_changes, called after every generation insert and once at the first start), stamped with the
-- generation and the source it serves — the same TP Last Jedi, Dark Side, the One Pager and R2D2 show.
-- Rows written before (tp_source NULL) are the LEGACY regime — a producer's row (our_tp: the internal TP blended with the
-- consensus) for the universe and on-demand cycles, the One Pager's row for its US records — and are NEVER backfilled: no
-- UPDATE here, no DEFAULT (a default would stamp the legacy rows). Additive and idempotent: every migration runs at every
-- start, so each column is added only when missing (later starts run no ALTER) and the index only when absent.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'valuation_change_records'::regclass AND attname = 'tp_source' AND attnum > 0 AND NOT attisdropped
    ) THEN
        ALTER TABLE valuation_change_records ADD COLUMN tp_source TEXT;  -- the served record's official source; NULL = legacy record
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'valuation_change_records'::regclass AND attname = 'generation_id' AND attnum > 0 AND NOT attisdropped
    ) THEN
        ALTER TABLE valuation_change_records
            ADD COLUMN generation_id UUID REFERENCES valuation_official_selection(generation_id);  -- 048: append-only, never deleted
    END IF;
END
$$;

-- one served record per (generation, market, symbol): two processes capturing the same generation append it once (the
-- application's ON CONFLICT names this index); legacy rows (generation_id NULL) are outside it
CREATE UNIQUE INDEX IF NOT EXISTS valuation_change_generation_symbol
    ON valuation_change_records (generation_id, market, symbol)
    WHERE generation_id IS NOT NULL;
