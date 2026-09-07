-- R2D2 V2 paper mirror (EMENDA 2 rev 2, MIRROR_NOT_CERTIFIED): per-episode command memory.
-- The paper orders/positions themselves live in the engine's r2d2_* tables under the mirror's own
-- experiment (R2D2-V2-MIRROR-001). This table records each command (identity + payload hash,
-- registered BEFORE the paper effect and CLAIMED atomically before it), its effect receipts, skips,
-- pending exits, dispositions and the divergences versus the V2 virtual ledger (never reconciled).
-- Scope: (mirror_epoch, epoch, episode_key); command ids are unique across the table.
CREATE TABLE IF NOT EXISTS r2d2_v2_mirror_episodes (
    mirror_epoch TEXT NOT NULL,
    epoch TEXT NOT NULL,
    episode_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT,
    experiment_id UUID NOT NULL REFERENCES r2d2_experiments(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('SKIPPED', 'BUY_PENDING', 'BUY_EXECUTING', 'OPEN', 'EXIT_PENDING', 'SELL_EXECUTING', 'CLOSED', 'AWAITING_DISPOSITION', 'BLOCKED')),
    reason TEXT,
    buy_command_id TEXT CHECK (buy_command_id IS NULL OR buy_command_id ~ '^[0-9a-f]{64}$'),
    buy_command_sha TEXT CHECK (buy_command_sha IS NULL OR buy_command_sha ~ '^[0-9a-f]{64}$'),
    sell_command_id TEXT CHECK (sell_command_id IS NULL OR sell_command_id ~ '^[0-9a-f]{64}$'),
    sell_command_sha TEXT CHECK (sell_command_sha IS NULL OR sell_command_sha ~ '^[0-9a-f]{64}$'),
    command_registered_at TIMESTAMPTZ,
    claim_token TEXT,
    claimed_at TIMESTAMPTZ,
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
    PRIMARY KEY (mirror_epoch, epoch, episode_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS r2d2_v2_mirror_episodes_buy_command
    ON r2d2_v2_mirror_episodes (buy_command_id) WHERE buy_command_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS r2d2_v2_mirror_episodes_sell_command
    ON r2d2_v2_mirror_episodes (sell_command_id) WHERE sell_command_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS r2d2_v2_mirror_episodes_experiment
    ON r2d2_v2_mirror_episodes (experiment_id, status);
