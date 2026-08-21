DROP INDEX IF EXISTS idx_leah_items_external;

CREATE UNIQUE INDEX IF NOT EXISTS idx_leah_event_occurrences_external
    ON leah_items (owner_email, external_id, starts_at)
    WHERE external_id IS NOT NULL AND kind = 'event';

CREATE UNIQUE INDEX IF NOT EXISTS idx_leah_tasks_external
    ON leah_items (owner_email, external_id)
    WHERE external_id IS NOT NULL AND kind = 'task';
