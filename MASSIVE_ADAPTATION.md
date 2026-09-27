# Massive adaptation — offline working branch

Owner requested immediate adaptation without merge. Deadline: Saturday 26 September 2026, 18:00 UTC / 15:00 BRT, for Fable review.

Measurement B completed: all 580 symbol-minute pairs observed in a 20-symbol, 29-minute sample. This is evidence for proceeding with development, not certification of the full universe or authorization to merge. Publication of the comparison remains blocked by automatic review; do not claim Fable received it.

Implemented: Massive REST unadjusted aggregate envelope adapter through the existing XNYS calendar and motor event validator. Exact original bytes remain the receipt hash source. Reject delayed/non-OK responses, wrong symbols, adjusted series, pagination, count mismatch, malformed OHLC/volume, duplicate/out-of-order and open minutes. Missing minutes remain DATA_GAP. The 90-second rule is unchanged. Provider fractional volume is preserved.

Verification: 44 focused tests pass (25 existing EODHD plus 19 Massive). No production mutation or merge.

Still required: bounded authenticated transport; durable raw/receipt persistence; idempotent spool and conflict handling; actual motor integration; end-to-end tests and Fable review. Converter alone is not a functioning production generator. If further coverage findings are adverse, retain code offline and proceed only with the approved Monday rehearsal package.

## Fable disposition 5838569796

Independent sample readback accepted; BAR development restored with Massive. Deadline and Sunday signature unchanged. WebSocket AM is the direction for 550 instruments; REST sample latency is not a scale proof. Current focused suite: 52 PASS. AM conversion preserves original frame hash and actual reception available_at, rejects open intervals, reconnect retroactivity, OTC/wrong identity and late data. Authenticated connection, raw spool, heartbeat/disconnect propagation and real motor integration remain pending.

Official protocol reference (25 September 2026): https://massive.com/docs/websocket/stocks/aggregates-per-minute — AM start/end in milliseconds; 1-minute OHLC from eligible trades; no eligible trade means no emitted bar. Advanced access is documented realtime, but configuration alone does not prove runtime authorization. No invented empty bars.

## Connection-state increment

57 focused tests PASS, including a synthetic frame with all 550 distinct names. Disconnect/status produces per-name DATA_GAP; duplicate identical frames are idempotent in memory; conflicting OHLC invalidates the stream; reconnect rejects minutes beginning before the new connection. Sink failure is not acknowledged. This is not live 550-name latency proof. Network loop, minute-expiry gaps, bounded state pruning, durable restart/spool and motor integration remain required before review.
