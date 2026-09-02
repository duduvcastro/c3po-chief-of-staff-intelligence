\set ON_ERROR_STOP on

-- This query is intentionally self-contained and read-only.  It never exports
-- a trade, candidate, symbol, or price row.  PostgreSQL reduces the persisted
-- outcome log to per-session sufficient statistics; the GitHub runner applies
-- the frozen Python bootstrap afterwards.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '5s';

WITH
params AS (
    SELECT
        'R2D2-90D-001'::text AS experiment_code,
        'policy-a-resume-2026-08-26'::text AS policy_epoch,
        '2026-08-26T13:30:24.983322Z'::timestamptz AS epoch_start,
        0.005::numeric AS cent_tolerance_usd,
        0.05::numeric AS market_violation_fraction_ceiling
),
access_contract AS (
    SELECT
        current_user::text AS effective_role,
        current_setting('transaction_read_only')::text AS transaction_read_only,
        current_setting('statement_timeout')::text AS statement_timeout,
        current_setting('lock_timeout')::text AS lock_timeout,
        (
            current_user = 'pg_read_all_data'
            AND current_setting('transaction_read_only') = 'on'
            AND current_setting('statement_timeout')::interval = interval '2 minutes'
            AND current_setting('lock_timeout')::interval = interval '5 seconds'
        ) AS passed
),
experiment AS (
    SELECT e.id, e.code
    FROM r2d2_experiments e
    JOIN params p ON p.experiment_code = e.code
),
experiment_summary AS (
    SELECT count(*)::integer AS experiment_count
    FROM experiment
),
organic_all AS (
    SELECT
        t.id,
        t.experiment_id,
        t.market,
        t.symbol,
        t.quantity,
        t.signal_price_local,
        t.fill_price_local,
        t.fx_to_usd,
        t.gross_value_usd,
        t.fees_usd,
        t.slippage_usd,
        t.decision_snapshot,
        t.executed_at,
        (t.executed_at AT TIME ZONE 'America/New_York')::date AS session_date,
        t.quantity * t.fill_price_local * t.fx_to_usd AS expected_gross,
        t.signal_price_local * (
            1 + CASE WHEN t.market = 'B3' THEN 0.0015 ELSE 0.0010 END
        ) AS expected_fill,
        (t.quantity * t.fill_price_local * t.fx_to_usd) * (
            CASE WHEN t.market = 'B3' THEN 0.0006 ELSE 0.0004 END
        ) AS expected_fees,
        t.quantity * abs(t.fill_price_local - t.signal_price_local) * t.fx_to_usd
            AS expected_slippage
    FROM r2d2_trades t
    JOIN experiment e ON e.id = t.experiment_id
    WHERE t.side = 'BUY'
      AND NOT (t.decision_snapshot ? 'correction')
      AND NOT (t.decision_snapshot ? 'operator_wind_down')
),
organic_checked AS (
    SELECT
        o.*,
        (
            abs(o.gross_value_usd - o.expected_gross) <= p.cent_tolerance_usd
            AND abs(o.fees_usd - o.expected_fees) <= p.cent_tolerance_usd
            AND abs(o.slippage_usd - o.expected_slippage) <= p.cent_tolerance_usd
            AND abs(o.fill_price_local - o.expected_fill) <= 0.0000001
        ) AS g1_valid,
        o.executed_at >= p.epoch_start AS in_current_epoch,
        nullif(btrim(o.decision_snapshot ->> 'policy_epoch'), '') AS persisted_epoch
    FROM organic_all o
    CROSS JOIN params p
),
accepted_ranked AS (
    SELECT
        c.*,
        count(*) OVER (PARTITION BY c.trade_id) AS candidate_count_for_trade,
        row_number() OVER (PARTITION BY c.trade_id ORDER BY c.id) AS candidate_ordinal
    FROM r2d2_shadow_candidates c
    JOIN experiment e ON e.id = c.experiment_id
    WHERE c.decision = 'accepted'
      AND c.trade_id IS NOT NULL
),
organic_with_candidate AS (
    SELECT
        o.*,
        coalesce(c.candidate_count_for_trade, 0)::integer AS candidate_count_for_trade,
        c.id AS candidate_id,
        c.schema_version AS candidate_schema_version,
        c.session_date AS candidate_session_date,
        c.market AS candidate_market,
        c.symbol AS candidate_symbol,
        c.policy_epoch AS candidate_policy_epoch,
        c.candidate_sha256,
        out.id AS outcome_id,
        out.session_date AS outcome_session_date,
        out.coverage_classification,
        out.barrier_category,
        out.outcome_payload,
        out.outcome_sha256
    FROM organic_checked o
    LEFT JOIN accepted_ranked c
      ON c.trade_id = o.id
     AND c.candidate_ordinal = 1
    LEFT JOIN r2d2_shadow_candidate_outcomes out
      ON out.candidate_id = c.id
),
row_validation AS (
    SELECT
        x.*,
        CASE
            WHEN x.candidate_count_for_trade <> 1 OR x.candidate_id IS NULL THEN false
            WHEN x.outcome_id IS NULL THEN false
            WHEN x.candidate_schema_version IS DISTINCT FROM
                 'R2D2-SHADOW-CANDIDATE-OBSERVATION-v1' THEN false
            WHEN x.candidate_session_date IS DISTINCT FROM x.session_date THEN false
            WHEN x.candidate_market IS DISTINCT FROM x.market
                 OR x.candidate_symbol IS DISTINCT FROM x.symbol THEN false
            WHEN x.candidate_sha256 !~ '^[0-9a-f]{64}$' THEN false
            WHEN x.outcome_sha256 !~ '^[0-9a-f]{64}$' THEN false
            WHEN x.outcome_session_date IS DISTINCT FROM x.session_date THEN false
            WHEN x.outcome_payload ->> 'schema_version' IS DISTINCT FROM
                 'R2D2-SHADOW-CANDIDATE-OUTCOME-v1' THEN false
            WHEN x.outcome_payload ->> 'candidate_id' IS DISTINCT FROM
                 x.candidate_id::text THEN false
            WHEN x.outcome_payload ->> 'candidate_sha256' IS DISTINCT FROM
                 x.candidate_sha256 THEN false
            WHEN x.outcome_payload ->> 'fill_source' IS DISTINCT FROM
                 'linked_trade' THEN false
            WHEN x.outcome_payload #>> '{fill,id}' IS DISTINCT FROM x.id::text THEN false
            WHEN x.outcome_payload ->> 'market' IS DISTINCT FROM x.market THEN false
            WHEN x.outcome_payload ->> 'symbol' IS DISTINCT FROM x.symbol THEN false
            WHEN x.outcome_payload ->> 'decision' IS DISTINCT FROM 'accepted' THEN false
            WHEN x.outcome_payload ->> 'coverage_classification'
                 IS DISTINCT FROM x.coverage_classification THEN false
            WHEN coalesce(x.outcome_payload ->> 'barrier_category', '')
                 <> coalesce(x.barrier_category, '') THEN false
            WHEN x.outcome_payload #>> '{market_compatibility,classification}' IS NULL
                 OR x.outcome_payload #>> '{market_compatibility,classification}'
                    NOT IN ('contained', 'clock_extended', 'tolerance_band',
                            'bar_unavailable', 'violation') THEN false
            WHEN x.coverage_classification = 'available' AND (
                jsonb_typeof(x.outcome_payload -> 'measurement') IS DISTINCT FROM 'object'
                OR x.barrier_category IS NULL
                OR x.outcome_payload #>> '{measurement,entry_id}' IS DISTINCT FROM
                   x.id::text
                OR x.outcome_payload #>> '{measurement,session_date}' IS DISTINCT FROM
                   x.session_date::text
                OR x.outcome_payload #>> '{measurement,policy_epoch}'
                   IS DISTINCT FROM x.candidate_policy_epoch
                OR x.outcome_payload #>> '{measurement,barrier_category}'
                   IS DISTINCT FROM x.barrier_category
            ) THEN false
            WHEN x.coverage_classification <> 'available'
                 AND coalesce(jsonb_typeof(x.outcome_payload -> 'measurement'), 'null')
                     <> 'null' THEN false
            WHEN x.coverage_classification = 'market_compatibility_violation'
                 AND x.outcome_payload #>> '{market_compatibility,classification}'
                     IS DISTINCT FROM 'violation' THEN false
            WHEN x.coverage_classification = 'available'
                 AND x.outcome_payload #>> '{market_compatibility,classification}'
                     IN ('bar_unavailable', 'violation') THEN false
            ELSE true
        END AS shadow_row_valid,
        CASE
            WHEN x.in_current_epoch THEN (
                x.candidate_policy_epoch = p.policy_epoch
                AND (x.persisted_epoch IS NULL OR x.persisted_epoch = p.policy_epoch)
            )
            ELSE true
        END AS current_epoch_valid
    FROM organic_with_candidate x
    CROSS JOIN params p
),
candidate_session_counts AS (
    SELECT c.session_date, count(*)::integer AS observed_candidate_count
    FROM r2d2_shadow_candidates c
    JOIN experiment e ON e.id = c.experiment_id
    GROUP BY c.session_date
),
report_validation AS (
    SELECT
        s.session_date,
        CASE
            WHEN r.id IS NULL THEN false
            WHEN r.candidate_count IS DISTINCT FROM s.observed_candidate_count THEN false
            WHEN r.jsonl_sha256 !~ '^[0-9a-f]{64}$' THEN false
            WHEN r.report_sha256 !~ '^[0-9a-f]{64}$' THEN false
            WHEN r.report ->> 'schema_version' IS DISTINCT FROM
                 'R2D2-SHADOW-CANDIDATE-REPORT-v1'
                THEN false
            WHEN r.report ->> 'session_date' IS DISTINCT FROM s.session_date::text
                THEN false
            WHEN r.report ->> 'report_sha256' IS DISTINCT FROM r.report_sha256
                THEN false
            WHEN jsonb_typeof(r.report -> 'price_sources') IS DISTINCT FROM 'object'
                THEN false
            WHEN coalesce((r.report #>> '{price_sources,trade_bars_only}')::boolean, false)
                 IS NOT true THEN false
            WHEN coalesce((r.report #>> '{price_sources,raw_processor_invoked}')::boolean, true)
                 IS NOT false THEN false
            WHEN (r.report #>> '{cohort,candidate_count}') IS NULL
                 OR (r.report #>> '{cohort,candidate_count}') !~ '^[0-9]+$'
                THEN false
            WHEN (r.report #>> '{cohort,candidate_count}')::integer
                 <> s.observed_candidate_count THEN false
            WHEN (r.report #>> '{daily_jsonl,row_count}') IS NULL
                 OR (r.report #>> '{daily_jsonl,row_count}') !~ '^[0-9]+$'
                THEN false
            WHEN (r.report #>> '{daily_jsonl,row_count}')::integer
                 <> s.observed_candidate_count THEN false
            WHEN r.report #>> '{daily_jsonl,sha256}' IS DISTINCT FROM r.jsonl_sha256
                THEN false
            ELSE true
        END AS report_valid
    FROM candidate_session_counts s
    LEFT JOIN r2d2_shadow_candidate_reports r
      ON r.experiment_id = (SELECT id FROM experiment LIMIT 1)
     AND r.session_date = s.session_date
),
population_summary AS (
    SELECT
        count(*)::integer AS organic_buy_count,
        count(*) FILTER (WHERE in_current_epoch)::integer AS current_epoch_buy_count,
        count(*) FILTER (WHERE NOT g1_valid)::integer AS g1_failure_count,
        count(*) FILTER (WHERE candidate_count_for_trade <> 1)::integer
            AS candidate_cardinality_failure_count,
        count(*) FILTER (WHERE NOT shadow_row_valid)::integer
            AS shadow_integrity_failure_count,
        count(*) FILTER (WHERE in_current_epoch AND NOT current_epoch_valid)::integer
            AS current_epoch_failure_count,
        count(*) FILTER (
            WHERE in_current_epoch AND candidate_count_for_trade <> 1
        )::integer AS current_epoch_missing_candidate_count,
        count(*) FILTER (
            WHERE outcome_payload #>> '{market_compatibility,classification}' = 'violation'
        )::integer AS market_violation_count,
        count(*) FILTER (
            WHERE in_current_epoch
              AND coverage_classification = 'bar_unavailable'
        )::integer AS current_epoch_bar_unavailable_count,
        count(*) FILTER (
            WHERE in_current_epoch
              AND coverage_classification = 'market_compatibility_violation'
        )::integer AS current_epoch_market_violation_count,
        count(*) FILTER (
            WHERE in_current_epoch
              AND coverage_classification = 'available'
              AND shadow_row_valid
              AND current_epoch_valid
        )::integer AS current_epoch_measured_count
    FROM row_validation
),
report_summary AS (
    SELECT
        count(*)::integer AS report_session_count,
        count(*) FILTER (WHERE NOT report_valid)::integer AS report_failure_count
    FROM report_validation
),
equivalence_facts AS (
    SELECT
        a.passed AS access_contract_passed,
        e.experiment_count,
        p.*,
        r.report_session_count,
        r.report_failure_count,
        (
            p.organic_buy_count > 0
            AND p.candidate_cardinality_failure_count = 0
            AND p.shadow_integrity_failure_count = 0
            AND r.report_failure_count = 0
        ) AS source_complete,
        (
            p.organic_buy_count > 0
            AND p.market_violation_count::numeric / p.organic_buy_count
                <= q.market_violation_fraction_ceiling
        ) AS market_gate_passed
    FROM access_contract a
    CROSS JOIN experiment_summary e
    CROSS JOIN population_summary p
    CROSS JOIN report_summary r
    CROSS JOIN params q
),
equivalence_decision AS (
    SELECT
        f.*,
        (
            f.access_contract_passed
            AND f.experiment_count = 1
            AND f.source_complete
            AND f.current_epoch_buy_count > 0
            AND f.current_epoch_failure_count = 0
            AND f.g1_failure_count = 0
            AND f.market_gate_passed
        ) AS canonical_equivalent
    FROM equivalence_facts f
),
equivalence_reasons AS (
    SELECT array_remove(ARRAY[
        CASE WHEN NOT access_contract_passed THEN 'database_access_contract_failed' END,
        CASE WHEN experiment_count <> 1 THEN 'experiment_not_unique' END,
        CASE WHEN organic_buy_count = 0 THEN 'organic_population_empty' END,
        CASE WHEN current_epoch_buy_count = 0 THEN 'current_epoch_population_empty' END,
        CASE WHEN g1_failure_count > 0 THEN 'global_g1_ledger_gate_failed' END,
        CASE WHEN candidate_cardinality_failure_count > 0
             THEN 'shadow_trade_coverage_incomplete' END,
        CASE WHEN current_epoch_missing_candidate_count > 0
             THEN 'current_epoch_contains_pre_instrumentation_gap' END,
        CASE WHEN shadow_integrity_failure_count > 0
             THEN 'shadow_outcome_integrity_failed' END,
        CASE WHEN current_epoch_failure_count > 0
             THEN 'current_epoch_assignment_failed' END,
        CASE WHEN report_failure_count > 0 THEN 'daily_report_integrity_failed' END,
        CASE WHEN NOT market_gate_passed THEN 'global_market_compatibility_gate_failed' END
    ], NULL)::text[] AS reasons
    FROM equivalence_decision
),
current_measurements AS (
    SELECT
        v.session_date,
        v.id::text AS entry_id,
        v.barrier_category,
        v.outcome_payload -> 'measurement' AS measurement,
        CASE
            WHEN jsonb_typeof(v.outcome_payload #> '{measurement,composite_score}') = 'number'
            THEN (v.outcome_payload #>> '{measurement,composite_score}')::numeric
        END AS composite_score,
        CASE
            WHEN jsonb_typeof(v.outcome_payload #> '{measurement,primary_return_60m_percent}')
                 = 'number'
            THEN (v.outcome_payload #>> '{measurement,primary_return_60m_percent}')::numeric
        END AS primary_return_60m_percent,
        CASE
            WHEN jsonb_typeof(v.outcome_payload #> '{measurement,mfe_percent}') = 'number'
            THEN (v.outcome_payload #>> '{measurement,mfe_percent}')::numeric
        END AS mfe_percent,
        CASE
            WHEN jsonb_typeof(v.outcome_payload #> '{measurement,mae_percent}') = 'number'
            THEN (v.outcome_payload #>> '{measurement,mae_percent}')::numeric
        END AS mae_percent
    FROM row_validation v
    WHERE v.in_current_epoch
      AND v.shadow_row_valid
      AND v.current_epoch_valid
      AND v.coverage_classification = 'available'
),
m1_session_rows AS (
    SELECT
        session_date,
        count(*)::integer AS entry_count,
        count(*) FILTER (WHERE barrier_category = 'upper_first')::integer AS upper_first,
        count(*) FILTER (WHERE barrier_category = 'lower_first')::integer AS lower_first,
        count(*) FILTER (WHERE barrier_category = 'ambiguous_same_bar')::integer
            AS ambiguous_same_bar,
        count(*) FILTER (WHERE barrier_category = 'censored')::integer AS censored
    FROM current_measurements
    GROUP BY session_date
    ORDER BY session_date
),
scored_ranked AS (
    SELECT
        m.*,
        row_number() OVER (ORDER BY composite_score, entry_id) AS score_rank,
        count(*) OVER () AS score_count
    FROM current_measurements m
    WHERE composite_score IS NOT NULL
),
h3_membership AS (
    SELECT r.*, cell.cell
    FROM scored_ranked r
    CROSS JOIN LATERAL (
        VALUES
            ('bottom_decile'::text,
             r.score_rank <= ceil(r.score_count::numeric / 10.0)::bigint),
            ('top_decile'::text,
             r.score_rank > r.score_count - ceil(r.score_count::numeric / 10.0)::bigint)
    ) AS cell(cell, included)
    WHERE cell.included
),
h3_session_rows AS (
    SELECT
        cell,
        session_date,
        count(*)::integer AS entry_count,
        count(*) FILTER (WHERE barrier_category = 'upper_first')::integer AS upper_first,
        count(*) FILTER (WHERE barrier_category = 'lower_first')::integer AS lower_first,
        count(*) FILTER (WHERE barrier_category = 'ambiguous_same_bar')::integer
            AS ambiguous_same_bar,
        count(*) FILTER (WHERE barrier_category = 'censored')::integer AS censored,
        count(primary_return_60m_percent)::integer AS primary_observed_count,
        coalesce(sum(primary_return_60m_percent), 0)::numeric AS primary_sum,
        count(mfe_percent)::integer AS mfe_observed_count,
        coalesce(sum(mfe_percent), 0)::numeric AS mfe_sum,
        count(mae_percent)::integer AS mae_observed_count,
        coalesce(sum(mae_percent), 0)::numeric AS mae_sum
    FROM h3_membership
    GROUP BY cell, session_date
    ORDER BY cell, session_date
),
h3_cell_rows AS (
    SELECT
        cell,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY primary_return_60m_percent)
            FILTER (WHERE primary_return_60m_percent IS NOT NULL) AS primary_median
    FROM h3_membership
    GROUP BY cell
)
SELECT jsonb_build_object(
    'schema', 'C3PO_ENTRY_QUALITY_M1_SERVER_AGGREGATE-v1',
    'generated_at', to_char(
        clock_timestamp() AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
    ),
    'database_access', jsonb_build_object(
        'effective_role', a.effective_role,
        'transaction_read_only', a.transaction_read_only,
        'statement_timeout', a.statement_timeout,
        'lock_timeout', a.lock_timeout,
        'ddl_or_dml_executed', false
    ),
    'ruler', jsonb_build_object(
        'policy_epoch', p.policy_epoch,
        'epoch_start', p.epoch_start,
        'bootstrap_seed', 20260824,
        'bootstrap_iterations', 10000,
        'percentile_method', 'nearest_rank_ceil_qn_minus_1',
        'central_denominator', 'upper_first + lower_first',
        'conservative_denominator',
            'upper_first + lower_first + ambiguous_same_bar',
        'current_epoch_only', true,
        'cross_epoch_pooling', false
    ),
    'equivalence', jsonb_build_object(
        'canonical_equivalent', d.canonical_equivalent,
        'source_complete', d.source_complete,
        'reasons', to_jsonb(er.reasons),
        'contract',
            'every organic BUY must have exactly one append-only linked shadow outcome and a valid daily source report before persisted outcomes may substitute for a fresh bar rebuild'
    ),
    'cohort', jsonb_build_object(
        'organic_buy_count_all_epochs', d.organic_buy_count,
        'current_epoch_constructed_count', d.current_epoch_buy_count,
        'current_epoch_measured_count', d.current_epoch_measured_count,
        'current_epoch_bar_unavailable_count', d.current_epoch_bar_unavailable_count,
        'current_epoch_market_compatibility_violation_count',
            d.current_epoch_market_violation_count,
        'missing_linked_candidate_count_all_epochs',
            d.candidate_cardinality_failure_count,
        'missing_linked_candidate_count_current_epoch',
            d.current_epoch_missing_candidate_count,
        'g1_failure_count', d.g1_failure_count,
        'shadow_integrity_failure_count', d.shadow_integrity_failure_count,
        'report_failure_count', d.report_failure_count,
        'market_compatibility_violation_count_all_epochs', d.market_violation_count,
        'market_compatibility_gate_passed', d.market_gate_passed
    ),
    'session_stats', CASE
        WHEN d.canonical_equivalent THEN coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'session_date', session_date,
                'entry_count', entry_count,
                'upper_first', upper_first,
                'lower_first', lower_first,
                'ambiguous_same_bar', ambiguous_same_bar,
                'censored', censored
            ) ORDER BY session_date)
            FROM m1_session_rows
        ), '[]'::jsonb)
        ELSE '[]'::jsonb
    END,
    'h3', jsonb_build_object(
        'session_stats', CASE
            WHEN d.canonical_equivalent THEN coalesce((
                SELECT jsonb_agg(jsonb_build_object(
                    'cell', cell,
                    'session_date', session_date,
                    'entry_count', entry_count,
                    'upper_first', upper_first,
                    'lower_first', lower_first,
                    'ambiguous_same_bar', ambiguous_same_bar,
                    'censored', censored,
                    'primary_observed_count', primary_observed_count,
                    'primary_sum', primary_sum,
                    'mfe_observed_count', mfe_observed_count,
                    'mfe_sum', mfe_sum,
                    'mae_observed_count', mae_observed_count,
                    'mae_sum', mae_sum
                ) ORDER BY cell, session_date)
                FROM h3_session_rows
            ), '[]'::jsonb)
            ELSE '[]'::jsonb
        END,
        'cell_totals', CASE
            WHEN d.canonical_equivalent THEN coalesce((
                SELECT jsonb_object_agg(
                    cell,
                    jsonb_build_object('primary_median', primary_median)
                    ORDER BY cell
                )
                FROM h3_cell_rows
            ), '{}'::jsonb)
            ELSE '{}'::jsonb
        END
    ),
    'fallback', jsonb_build_object(
        'required', NOT d.canonical_equivalent,
        'method', 'github_runner_session_streaming_rebuild',
        'baseline_run_id', 33022905030,
        'baseline_report_sha256',
            '23ede14e5d76cdd70bd1df58fcde62ad9445291eacae4872174b835ac4b94756',
        'steps', jsonb_build_array(
            'download and verify the sealed baseline report before using it as an anchor',
            'stream ordered organic BUY rows to runner scratch through read-only psql COPY',
            'stream and verify one immutable Day-D session source at a time over SSH',
            'run the frozen measurement code on the GitHub runner and discard each raw session before the next',
            'recompute the global gate, current-epoch M1, H3 and all source hashes from the complete population',
            'publish only the reduced artifact; never start a second API container on production'
        ),
        'partial_shadow_result_must_not_be_published', true
    )
)::text
FROM access_contract a
CROSS JOIN params p
CROSS JOIN equivalence_decision d
CROSS JOIN equivalence_reasons er;

ROLLBACK;
