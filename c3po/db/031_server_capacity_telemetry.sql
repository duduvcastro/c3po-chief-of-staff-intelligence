ALTER TABLE server_usage_samples
    ADD COLUMN IF NOT EXISTS cpu_steal_percent NUMERIC(6, 3),
    ADD COLUMN IF NOT EXISTS load_average_1m NUMERIC(12, 4),
    ADD COLUMN IF NOT EXISTS load_average_5m NUMERIC(12, 4),
    ADD COLUMN IF NOT EXISTS load_average_15m NUMERIC(12, 4);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'server_usage_cpu_steal_range'
    ) THEN
        ALTER TABLE server_usage_samples
            ADD CONSTRAINT server_usage_cpu_steal_range
            CHECK (cpu_steal_percent IS NULL OR cpu_steal_percent BETWEEN 0 AND 100);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'server_usage_load_average_nonnegative'
    ) THEN
        ALTER TABLE server_usage_samples
            ADD CONSTRAINT server_usage_load_average_nonnegative
            CHECK (
                (load_average_1m IS NULL OR load_average_1m >= 0)
                AND (load_average_5m IS NULL OR load_average_5m >= 0)
                AND (load_average_15m IS NULL OR load_average_15m >= 0)
            );
    END IF;
END $$;
