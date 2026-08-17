UPDATE ir_events
SET valuation_relevant = FALSE,
    valuation_status = 'informational'
WHERE source_code = 'ri'
  AND lower(trim(title)) IN (
      'central de resultados',
      'earnings center',
      'results center'
  );

DELETE FROM ir_valuation_queue queue
USING ir_events event
WHERE queue.event_id = event.id
  AND event.valuation_relevant = FALSE;
