-- O guardião append-only da 032 bloqueia UPDATE; o backfill precisa passar por
-- dentro dele. Dropar antes, recriar depois — idempotente porque a 032 recria o
-- trigger a cada boot ANTES desta migração rodar.
DROP TRIGGER IF EXISTS governance_vulnerability_daily_append_only
    ON governance_vulnerability_daily;

ALTER TABLE governance_vulnerability_daily
    ADD COLUMN IF NOT EXISTS revision INTEGER;

UPDATE governance_vulnerability_daily
SET revision = 1
WHERE revision IS NULL;

ALTER TABLE governance_vulnerability_daily
    ALTER COLUMN revision SET NOT NULL;

ALTER TABLE governance_vulnerability_daily
    DROP CONSTRAINT IF EXISTS governance_vulnerability_daily_pkey;

ALTER TABLE governance_vulnerability_daily
    ADD CONSTRAINT governance_vulnerability_daily_pkey
    PRIMARY KEY (session_date, revision);

CREATE UNIQUE INDEX IF NOT EXISTS governance_vulnerability_daily_report_sha256_idx
    ON governance_vulnerability_daily (report_sha256);

CREATE INDEX IF NOT EXISTS governance_vulnerability_daily_generated_at_idx
    ON governance_vulnerability_daily (generated_at DESC);

CREATE TRIGGER governance_vulnerability_daily_append_only
BEFORE UPDATE OR DELETE ON governance_vulnerability_daily
FOR EACH ROW EXECUTE FUNCTION reject_governance_vulnerability_daily_mutation();
