-- Historical NASDAQ/NYSE valuation-universe snapshots were normalized to B3
-- before the application mapping was corrected. The snapshot relation is the
-- authoritative market evidence, so only those unambiguous records are fixed.
UPDATE valuation_change_records AS valuation
SET market = 'US',
    currency = CASE WHEN valuation.currency = 'BRL' THEN 'USD' ELSE valuation.currency END,
    metadata = valuation.metadata || jsonb_build_object(
        'market_correction', jsonb_build_object(
            'from', valuation.market,
            'to', 'US',
            'reason', 'Snapshot belongs to a NASDAQ or NYSE valuation universe'
        )
    )
FROM analysis_snapshots AS snapshot
WHERE valuation.snapshot_id = snapshot.id
  AND snapshot.analysis_type = 'valuation_universe'
  AND snapshot.entity_key IN ('NASDAQ_UNIVERSE', 'NYSE_UNIVERSE')
  AND valuation.market <> 'US';
