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
