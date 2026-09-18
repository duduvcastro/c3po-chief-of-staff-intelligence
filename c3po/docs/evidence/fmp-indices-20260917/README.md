# Six cash indices: FMP replacement

Owner requested FMP for IBOV, Nasdaq Composite, NYSE Composite, Nikkei, Shanghai Composite and DAX across Falcon Capcom, Master Luke and other consumers on 2026-09-17.

Read-only production-credential probes confirmed FMP Ultimate access: batch-index-quotes returned 427 indices including all six but lacks timestamps. This implementation uses stable/batch-quote instead: all six quotes include UTC Unix timestamps, price, previousClose and session ranges. Six historical-chart/5min probes also returned data. Sanitized responses are attached; no credentials.

At 15:38Z, Nasdaq and DAX quotes were current; IBOV and NYSE were approximately 15 minutes delayed. Replacing the source does not remove an exchange's delay. Asian markets were closed. Chart date strings were exchange-local in all six probes (New York, São Paulo, Tokyo, Shanghai and Frankfurt); parse using the corresponding exchange calendar timezone, including DST. Source references:
- https://site.financialmodelingprep.com/developer/docs/stable/index-quote
- https://site.financialmodelingprep.com/developer/docs/stable/all-index-quotes

One shared IndexQuotesService is injected into both API services. Requests are coalesced behind a lock with a 10-second cache, including failed requests. Invalid/missing/future timestamps never become collection-time quotes; source regression cannot overwrite a newer observation. Failed/missing rows retain only previous FMP observations marked stale. No Yahoo fallback for these six quotes or charts. All six now belong to the Index API group; the frontend no longer joins a slower Future Index response to obtain global indices.

Calendar-aware status and observed quote age replace fixed ~5m labels. Currencies remain instrument-specific. Futures ES/NQ and Treasury yields are different instruments and retain their existing providers. Other equity/FX/crypto providers are unchanged.

Deployment requires Fable review and coordination with the approved D18 package pinned to revision 1bb009c3. This PR does not authorize replacing that installed revision, recreating its worker or changing any policy during the D18 rite.

## F413-1 audit correction

The library's BVMF calendar fixes the cash close at 18:00 São Paulo. B3's 2026 circular 005/2026-PRE instead closes cash at 17:00 during US daylight saving time; the preceding 043/2025-VNC circular establishes 18:00 after US DST ends. The status function caps the BVMF session close at 16:00 America/New_York for that B3 session date. B3 holidays, opening times and any earlier special close remain governed by BVMF. US holidays and half-days are not imported into B3. This is the regular cash session, not after-market or futures; future B3 timetable changes require updating this rule.

- https://www.b3.com.br/data/files/E3/B2/C2/12/BC09C910F37907C9AC094EA8/OC%20005-2026%20PRE%20NOVOS%20HORARIOS%20DE%20NEGOCIACAO_PT.pdf
- https://www.b3.com.br/data/files/36/22/17/A0/0131A910F51990A9AC094EA8/OC%20043-2025-VNC%20NOVOS%20HORARIOS%20DE%20NEGOCIACAO_PT.pdf

Regression coverage includes September 20:30Z and 21:30Z quotes and charts, the close boundary, January standard time, B3 holidays, US holidays/half-days and an obsolete previous-session quote that must remain stale.

Fable's non-blocking follow-ups F413-2 through F413-7 remain open: blocking HTTP under the shared lock, stale-on-failure after close, previous-session chart status, long age formatting, remaining source labels and sanitized transport diagnostics. This correction addresses only F413-1.
