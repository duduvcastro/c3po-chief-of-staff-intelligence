DROP INDEX IF EXISTS valuation_change_chronology;

CREATE INDEX valuation_change_chronology
    ON valuation_change_records (changed_at DESC, created_at DESC, id DESC);
