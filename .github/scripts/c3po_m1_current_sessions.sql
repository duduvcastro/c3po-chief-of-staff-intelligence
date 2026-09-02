\set ON_ERROR_STOP on

-- Enumerate only completed sessions in the frozen interim-M1 window.  This
-- query returns dates, never trade rows or identifiers.  Every substantive
-- measurement remains in the one-session-at-a-time reader whose exact source
-- is sealed with the final reduced artefact.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '5s';

SELECT DISTINCT
       (t.executed_at AT TIME ZONE 'America/New_York')::date AS session_date
FROM r2d2_trades AS t
JOIN r2d2_experiments AS e ON e.id = t.experiment_id
WHERE e.code = 'R2D2-90D-001'
  AND t.side = 'BUY'
  AND NOT coalesce(t.decision_snapshot ? 'correction', false)
  AND NOT coalesce(t.decision_snapshot ? 'operator_wind_down', false)
  AND t.executed_at >= timestamptz '2026-08-26T13:30:24.983322Z'
  AND (t.executed_at AT TIME ZONE 'America/New_York')::date <= date '2026-09-02'
ORDER BY session_date;

COMMIT;
