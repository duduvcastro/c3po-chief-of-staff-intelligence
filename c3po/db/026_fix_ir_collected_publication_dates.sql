-- RI pages without a provider publication date were historically promoted to
-- "new" on every collection. Their stable chronology is the first-seen time.
UPDATE ir_events
SET published_at = collected_at,
    updated_at = now()
WHERE published_time_precision = 'collected'
  AND published_at <> collected_at;
