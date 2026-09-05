\set ON_ERROR_STOP on

-- Enumerate the complete, chronological BUY-session source population for the
-- current M1 policy epoch.  The 18:00 America/New_York cutoff keeps a live
-- session out of the formal clock even if a scheduler or recovery run starts
-- during market hours.  This query returns dates only, never trade rows or
-- identifiers.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '5s';

WITH checkpoint_clock AS (
    SELECT current_timestamp AT TIME ZONE 'America/New_York' AS local_now
), finalized_clock AS (
    SELECT CASE
               WHEN local_now::time >= time '18:00:00'
                   THEN local_now::date
               ELSE local_now::date - 1
           END AS last_finalized_session
    FROM checkpoint_clock
)
SELECT DISTINCT
       (trade.executed_at AT TIME ZONE 'America/New_York')::date AS session_date
FROM r2d2_trades AS trade
JOIN r2d2_experiments AS experiment
  ON experiment.id = trade.experiment_id
CROSS JOIN finalized_clock
WHERE experiment.code = 'R2D2-90D-001'
  AND trade.side = 'BUY'
  AND NOT coalesce(trade.decision_snapshot ? 'correction', false)
  AND NOT coalesce(trade.decision_snapshot ? 'operator_wind_down', false)
  AND trade.executed_at >= timestamptz '2026-08-26T13:30:24.983322Z'
  AND (trade.executed_at AT TIME ZONE 'America/New_York')::date
      <= finalized_clock.last_finalized_session
ORDER BY session_date;

COMMIT;
