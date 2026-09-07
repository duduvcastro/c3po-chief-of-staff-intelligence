-- R2D2 V2 paper mirror (EMENDA 2 rev 2, MIRROR_NOT_CERTIFIED): per-episode command memory.
-- The paper orders/positions themselves live in the engine's r2d2_* tables under the mirror's
-- own experiment (R2D2-V2-MIRROR-001). This table records each command (identity + payload hash,
-- registered BEFORE the paper effect), its effect receipts, skips, pending exits, dispositions and
-- the divergences versus the V2 virtual ledger (never reconciled).
CREATE TABLE IF NOT EXISTS r2d2_v2_mirror_episodes (
    epoch TEXT NOT NULL,
    episode_key TEXT NOT NULL,
    mirror_epoch TEXT,
    symbol TEXT NOT NULL,
    market TEXT,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('SKIPPED', 'BUY_PENDING', 'OPEN', 'EXIT_PENDING', 'CLOSED', 'AWAITING_DISPOSITION', 'BLOCKED')),
    reason TEXT,
    command_id TEXT CHECK (command_id IS NULL OR command_id ~ '^[0-9a-f]{64}$'),
    command_sha TEXT CHECK (command_sha IS NULL OR command_sha ~ '^[0-9a-f]{64}$'),
    command_registered_at TIMESTAMPTZ,
    buy_trade_id UUID,
    buy_at TIMESTAMPTZ,
    buy_quantity NUMERIC(24, 8),
    buy_fill_price NUMERIC(20, 8),
    ledger_entry_price NUMERIC(20, 8),
    ledger_quantity NUMERIC(24, 8),
    ledger_opened_at TIMESTAMPTZ,
    sell_trade_id UUID,
    sell_at TIMESTAMPTZ,
    sell_fill_price NUMERIC(20, 8),
    ledger_exit_price NUMERIC(20, 8),
    ledger_exit_at TIMESTAMPTZ,
    ledger_exit_cause TEXT,
    divergence JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (epoch, episode_key)
);

CREATE INDEX IF NOT EXISTS r2d2_v2_mirror_episodes_experiment
    ON r2d2_v2_mirror_episodes (experiment_id, status);

CREATE INDEX IF NOT EXISTS r2d2_v2_mirror_episodes_command
    ON r2d2_v2_mirror_episodes (command_id);
