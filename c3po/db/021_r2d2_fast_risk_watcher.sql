ALTER TABLE r2d2_positions
    ADD COLUMN IF NOT EXISTS hard_stop_price_local NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS chandelier_atr_local NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS chandelier_atr_as_of TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS chandelier_stop_price_local NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS chandelier_confirmation_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS chandelier_last_confirmation_tick_at TIMESTAMPTZ;

ALTER TABLE r2d2_trades
    ADD COLUMN IF NOT EXISTS fast_exit_rule TEXT,
    ADD COLUMN IF NOT EXISTS fast_exit_level_local NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS fast_exit_atr_local NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS fast_exit_tick_as_of TIMESTAMPTZ;
