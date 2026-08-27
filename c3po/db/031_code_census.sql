CREATE TABLE IF NOT EXISTS code_census_daily (
    session_date DATE PRIMARY KEY,
    methodology TEXT NOT NULL,
    layers JSONB NOT NULL,
    total_lines INTEGER NOT NULL CHECK (total_lines >= 0),
    total_files INTEGER NOT NULL CHECK (total_files >= 0),
    docs_lines INTEGER NOT NULL CHECK (docs_lines >= 0),
    docs_files INTEGER NOT NULL CHECK (docs_files >= 0),
    generated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION reject_code_census_daily_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'code_census_daily is append-only';
END;
$$;

DROP TRIGGER IF EXISTS code_census_daily_append_only ON code_census_daily;
CREATE TRIGGER code_census_daily_append_only
BEFORE UPDATE OR DELETE ON code_census_daily
FOR EACH ROW EXECUTE FUNCTION reject_code_census_daily_mutation();
