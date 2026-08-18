#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/chief-of-staff-digital
OUT_DIR=/tmp/r2d2_export

mkdir -p "$OUT_DIR"
cd "$APP_DIR"

run() {
  docker compose -f c3po/compose.yml exec -T db \
    psql -U c3po -d c3po -v ON_ERROR_STOP=1 -c "$1" > "$OUT_DIR/$2"
}

run "\copy (SELECT id, code, status, base_currency, starting_capital, cash_balance, start_date, end_date, checkpoint_date, methodology_version, is_continuous FROM r2d2_experiments) TO STDOUT WITH CSV HEADER" experiments.csv
run "\copy (SELECT experiment_id, session_date, nav_usd, cash_usd, daily_pnl_usd, daily_return_percent, gross_exposure_usd, open_positions, is_final FROM r2d2_daily_snapshots ORDER BY session_date) TO STDOUT WITH CSV HEADER" daily_snapshots.csv
run "\copy (SELECT id, experiment_id, cycle_id, market, symbol, side, quantity, signal_price_local, fill_price_local, fx_to_usd, gross_value_usd, fees_usd, slippage_usd, realized_pnl_usd, reason, executed_at, quote_as_of FROM r2d2_trades ORDER BY executed_at) TO STDOUT WITH CSV HEADER" trades.csv
run "\copy (SELECT id, experiment_id, cycle_id, evaluated_at, market, symbol, action, fundamental_score, technical_score, risk_score, composite_score, reasons, inputs, trade_id FROM r2d2_decisions WHERE action = 'BUY' ORDER BY evaluated_at) TO STDOUT WITH CSV HEADER" decisions_buy.csv
run "\copy (SELECT id, snapshot_id, market, symbol, company_name, changed_at, trigger_type, trigger_title, trigger_summary, source_name, source_url, currency, old_tp, new_tp, tp_change_percent, old_buy_in, new_buy_in, old_consensus_tp, new_consensus_tp, price, old_confidence, new_confidence, methodology_name, methodology_version, metadata, created_at FROM valuation_change_records ORDER BY changed_at, created_at, id) TO STDOUT WITH CSV HEADER" valuation_calls.csv

echo "Streaming bundle to stdout ($(date -u +%Y-%m-%dT%H:%M:%SZ))" >&2
tar -czf - -C /tmp r2d2_export
