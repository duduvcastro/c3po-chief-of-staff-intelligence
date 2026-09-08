-- Valuation Engine V3.2 rev 7, §7-bis Passo 0: one official target price for every operational consumer.
-- Two append-only structures (rev 7, TP-B):
--   * valuation_predictions        — immutable records: what a producer said for (market, symbol) at prediction_instant,
--                                    keyed by the producing cycle (analysis_snapshots.id); sources coexist.
--   * valuation_official_selection — one row per GENERATION: the set of complete, validated cycles (one per market)
--                                    whose predictions are the official TP; switching sources (Passo 1/2) or rolling
--                                    back is the INSERT of a new generation, never an UPDATE; the previous one stays readable.
-- Passo 0 changes no number: the producer is the current official engine (tp_source = official_blend_v1).
-- Nothing here touches R2D2 tables, orders, positions or the V1/V2/V3 engines.

CREATE TABLE IF NOT EXISTS valuation_predictions (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE')),
    symbol TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('universe', 'targeted')),
    session_date DATE NOT NULL,
    cycle_id UUID NOT NULL REFERENCES analysis_snapshots(id),
    prediction_instant TIMESTAMPTZ NOT NULL,   -- when the prediction was made: the ORIGINAL live evaluation's publication (its session)
    -- rev 6 (B2): the record's own publication clock — when the snapshot that contains it became available; equal to
    -- prediction_instant for a live cycle, the re-run date for a re-run (never retro-dated: the CHECK forbids it).
    -- The constraint is NAMED so the idempotent block at the end of this file can find it on a table created before the column
    published_at TIMESTAMPTZ NOT NULL CONSTRAINT valuation_predictions_published_at_check CHECK (published_at >= prediction_instant),
    tp NUMERIC NOT NULL CHECK (tp > 0),
    buy_in NUMERIC NOT NULL CHECK (buy_in > 0),
    internal_tp NUMERIC,
    consensus_tp NUMERIC,
    consensus_source TEXT,
    analyst_count INTEGER,
    consensus_weight_percent NUMERIC,
    price NUMERIC,
    currency TEXT NOT NULL,
    decomposition JSONB NOT NULL DEFAULT '{}'::jsonb,
    row_sha256 TEXT NOT NULL CHECK (row_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_version, market, symbol, cycle_id)
);
CREATE INDEX IF NOT EXISTS valuation_predictions_lookup
    ON valuation_predictions (market, symbol, source, prediction_instant DESC);
-- every served read filters by cycle (the UNIQUE above ends with cycle_id and cannot serve it): rev 4, D2
CREATE INDEX IF NOT EXISTS valuation_predictions_by_cycle
    ON valuation_predictions (cycle_id);

CREATE TABLE IF NOT EXISTS valuation_official_selection (
    generation_id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    cycles JSONB NOT NULL,
    targeted JSONB NOT NULL DEFAULT '{}'::jsonb,
    session_dates JSONB NOT NULL,
    validated_complete BOOLEAN NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    activated_by TEXT NOT NULL,
    previous_generation_id UUID REFERENCES valuation_official_selection(generation_id),
    receipt JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS valuation_official_selection_activated
    ON valuation_official_selection (activated_at DESC);
-- generations form a chain: two concurrent writers cannot both extend the same predecessor (rev 4, B2)
CREATE UNIQUE INDEX IF NOT EXISTS valuation_official_selection_chain
    ON valuation_official_selection (previous_generation_id) WHERE previous_generation_id IS NOT NULL;
-- ...and the chain has ONE root: a second bootstrap (previous_generation_id NULL) cannot escape the partial index above (rev 5, F393-9)
CREATE UNIQUE INDEX IF NOT EXISTS valuation_official_selection_root
    ON valuation_official_selection ((1)) WHERE previous_generation_id IS NULL;

-- Append-only: predictions and selections are history; the application never updates or deletes them (I-TP2, I-TP3).
CREATE OR REPLACE FUNCTION valuation_official_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'valuation official records are append-only (% on %)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valuation_predictions_append_only ON valuation_predictions;
CREATE TRIGGER valuation_predictions_append_only
    BEFORE UPDATE OR DELETE ON valuation_predictions
    FOR EACH ROW EXECUTE FUNCTION valuation_official_append_only();

DROP TRIGGER IF EXISTS valuation_official_selection_append_only ON valuation_official_selection;
CREATE TRIGGER valuation_official_selection_append_only
    BEFORE UPDATE OR DELETE ON valuation_official_selection
    FOR EACH ROW EXECUTE FUNCTION valuation_official_append_only();

-- rev 6 (B2, S9) / rev 7 (F393-11 a): published_at was added to the CREATE TABLE above after the table may already have
-- been created without it (CREATE TABLE IF NOT EXISTS never alters an existing table), and every migration runs on every
-- start. The rows of such a table are rev-5 records (VALUATION_PREDICTION_V1): their row_sha256 was computed WITHOUT
-- published_at, so filling the column in place (the rev 6 backfill published_at = prediction_instant) would relabel them
-- under an identity nobody can recompute — the historical reference is NEVER rewritten silently. The block below decides
-- by the table: column missing + rows present → the migration FAILS LOUDLY (RAISE EXCEPTION naming the row count) and the
-- table waits for an explicit, ordered operator path (export, or the column added by hand WITHOUT backfill so the rows are
-- read as V1 — see docs/VALUATION_OFFICIAL_TP_V1.md, "Linhas legadas V1"); column missing + empty table → the column is
-- added NOT NULL directly (no UPDATE, no trigger suspended — a fresh installation is the supported path of this step);
-- column present → only the named CHECK is ensured (guarded by a pg_constraint lookup) and nothing else is touched.
DO $$
DECLARE
    legacy_rows BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_attribute
        WHERE attrelid = 'valuation_predictions'::regclass
          AND attname = 'published_at'
          AND attnum > 0
          AND NOT attisdropped
    ) THEN
        SELECT count(*) INTO legacy_rows FROM valuation_predictions;
        IF legacy_rows > 0 THEN
            RAISE EXCEPTION 'valuation_predictions has no published_at column and holds % legacy VALUATION_PREDICTION_V1 row(s): migration 048 refuses to upgrade a populated table automatically (F393-11 a) — the stored row_sha256 of those rows does not cover published_at, and a backfill would relabel them under an unverifiable identity', legacy_rows
                USING HINT = 'Operator path, by explicit order only (never automatic, never an in-place rewrite): either export the legacy rows (COPY valuation_predictions TO ...) and re-establish the history as new V2 records (a re-run of each cycle with inputs.rerun_of), or add the column by hand WITHOUT NOT NULL and WITHOUT backfill (ALTER TABLE valuation_predictions ADD COLUMN published_at TIMESTAMPTZ) so the legacy rows are read, verified and served as V1. See docs/VALUATION_OFFICIAL_TP_V1.md, section "Linhas legadas V1".';
        END IF;
        ALTER TABLE valuation_predictions ADD COLUMN published_at TIMESTAMPTZ NOT NULL;  -- an empty table: nothing to backfill
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'valuation_predictions'::regclass
          AND conname = 'valuation_predictions_published_at_check'
    ) THEN
        ALTER TABLE valuation_predictions
            ADD CONSTRAINT valuation_predictions_published_at_check
            CHECK (published_at >= prediction_instant);
    END IF;
END
$$;
