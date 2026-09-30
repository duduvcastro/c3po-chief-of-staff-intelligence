# Massive AM candidate — limits and unresolved proof

Official documentation checked 2026-09-26:
- https://massive.com/docs/websocket/quickstart — real-time endpoint `wss://socket.massive.com/stocks`, authentication before AM subscription, default one concurrent connection per asset class. Slow consumers may be disconnected.
- https://massive.com/docs/websocket/stocks/aggregates-per-minute — AM derives from eligible trades; no eligible trade means no bar. Includes extended sessions; candidate must filter XNYS regular session. Stocks Advanced advertises real-time; plan descriptions do not prove this account's entitlement.

Candidate connection uses one bounded receive queue, explicit frame-size bound, ten-second opening deadline, three-second closing deadline, fifteen-second ping interval and ten-second ping timeout. Compression and proxy discovery disabled. Credentials only in authentication frame; dedicated disabled protocol logger. No retries or delayed endpoint fallback in this layer. No new provider connections were executed during offline testing.

This is not evidence of 550-name coverage, throughput or <90-second end-to-end freshness. Durable ingest bridge, process ownership, single-connection conflict check, scheduler/spool integration, restart, backpressure and engine tests remain required before GO. Neither the previous REST sample nor a subscription acknowledgement establishes continuous complete coverage.
