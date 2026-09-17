# Six cash indices: FMP replacement

Owner requested FMP for IBOV, Nasdaq Composite, NYSE Composite, Nikkei, Shanghai Composite and DAX across Falcon Capcom, Master Luke and other consumers on 2026-09-17.

Read-only production-credential probes confirmed FMP Ultimate access: batch-index-quotes returned 427 indices including all six but lacks timestamps. This implementation uses stable/batch-quote instead: all six quotes include UTC Unix timestamps, price, previousClose and session ranges. Six historical-chart/5min probes also returned data. Sanitized responses are attached; no credentials.

At 15:38Z, Nasdaq and DAX quotes were current; IBOV and NYSE were approximately 15 minutes delayed. Replacing the source does not remove an exchange's delay. Asian markets were closed. Chart date strings were exchange-local in all six probes (New York, São Paulo, Tokyo, Shanghai and Frankfurt); parse using the corresponding exchange calendar timezone, including DST. Source references:
- https://site.financialmodelingprep.com/developer/docs/stable/index-quote
- https://site.financialmodelingprep.com/developer/docs/stable/all-index-quotes

One shared IndexQuotesService is injected into both API services. Requests are coalesced behind a lock with a 10-second cache, including failed requests. Invalid/missing/future timestamps never become collection-time quotes; source regression cannot overwrite a newer observation. Failed/missing rows retain only previous FMP observations marked stale. No Yahoo fallback for these six quotes or charts. All six now belong to the Index API group; the frontend no longer joins a slower Future Index response to obtain global indices.

Calendar-aware status and observed quote age replace fixed ~5m labels. Currencies remain instrument-specific. Futures ES/NQ and Treasury yields are different instruments and retain their existing providers. Other equity/FX/crypto providers are unchanged.

Deployment requires Fable review and coordination with the approved D18 package pinned to revision 1bb009c3. This PR does not authorize replacing that installed revision, recreating its worker or changing any policy during the D18 rite.
