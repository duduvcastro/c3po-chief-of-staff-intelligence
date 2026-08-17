UPDATE valuation_change_records
SET trigger_summary = 'Base inicial registrada para comparação com futuras revisões de valuation.',
    source_name = 'C3PO Valuation Engine',
    source_url = NULL,
    metadata = metadata - 'event_id'
WHERE trigger_type = 'initial';
