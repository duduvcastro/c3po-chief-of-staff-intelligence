-- Ben Kenobi Records requested classification by exchange (B3/NASDAQ/NYSE)
-- instead of a generic B3/US split. The snapshot relation names the exact
-- exchange for every bulk US screener record (NASDAQ_UNIVERSE/NYSE_UNIVERSE),
-- so only those unambiguous records are split; anything without a traceable
-- snapshot (e.g. One Pager-sourced "US" records) is left as-is.
ALTER TABLE valuation_change_records
    DROP CONSTRAINT IF EXISTS valuation_change_records_market_check;

UPDATE valuation_change_records AS valuation
SET market = CASE snapshot.entity_key
        WHEN 'NASDAQ_UNIVERSE' THEN 'NASDAQ'
        WHEN 'NYSE_UNIVERSE' THEN 'NYSE'
    END,
    metadata = valuation.metadata || jsonb_build_object(
        'exchange_classification', jsonb_build_object(
            'from', valuation.market,
            'to', CASE snapshot.entity_key
                WHEN 'NASDAQ_UNIVERSE' THEN 'NASDAQ'
                WHEN 'NYSE_UNIVERSE' THEN 'NYSE'
            END,
            'reason', 'Split generic US label into the snapshot''s real exchange'
        )
    )
FROM analysis_snapshots AS snapshot
WHERE valuation.snapshot_id = snapshot.id
  AND snapshot.analysis_type = 'valuation_universe'
  AND snapshot.entity_key IN ('NASDAQ_UNIVERSE', 'NYSE_UNIVERSE')
  AND valuation.market NOT IN ('NASDAQ', 'NYSE');

ALTER TABLE valuation_change_records
    ADD CONSTRAINT valuation_change_records_market_check
    CHECK (market IN ('B3', 'US', 'NASDAQ', 'NYSE'));
