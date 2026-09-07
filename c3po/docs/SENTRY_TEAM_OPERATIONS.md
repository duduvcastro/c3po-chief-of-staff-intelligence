# Sentry errors, browser monitoring and bounded performance

The C3PO Sentry card reports SDK configuration and Sentry's public service
status. `Serviço operacional` means the official status endpoint reported
`indicator=none`. It does not prove that a particular error or email arrived.
An unknown or malformed status response is attention, not confirmed health.

## Configuration

| Setting | Purpose | Production value |
| --- | --- | --- |
| `C3PO_SENTRY_DSN` | Existing public SDK ingestion identifier | `production` environment secret |
| `C3PO_SENTRY_SAMPLE_RATE` | Error sampling, independent of performance | `1.0` |
| `C3PO_SENTRY_TRACES_SAMPLE_RATE` | API performance sampling | `0.01` maximum; `0` disables |
| `NEXT_PUBLIC_SENTRY_DSN` | Browser ingestion, set at build time | Existing DSN from CI |
| `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | Browser environment | `production` |
| `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE` | Browser performance sampling | `0.01` maximum; `0` disables |
| `NEXT_PUBLIC_C3PO_BUILD_SHA` | Browser release attribution | Tested deployment revision |

Do not enable profiling, Session Replay or structured Sentry Logs as a side
effect of this setup. They have separate data and consumption implications.
Keep PII collection off and do not send account, portfolio or trading data in
custom event context. SDK privacy filters are defense in depth, not proof that
arbitrary free text can never contain personal data.

## Cost controls

Performance sampling reduces volume; it is not a hard monthly quota. The
organization's **Subscription → Pay-as-you-go** budget must remain **US$ 0**
unless the owner separately approves a higher amount. At the included quota,
Sentry can drop additional data instead of charging for overage. Check usage
and dropped events when diagnosing missing telemetry. Do not increase sampling
or enable a paid trial to work around a quota.

The SDK defaults to no tracing outside the production wiring. Sampling is
limited to 1% even if a caller supplies an upstream sampled trace. Errors
continue to use their separate sampling setting.

## End-to-end verification

1. Read the deployed revision and inspect the active alert's project,
   conditions and destination. A DSN alone does not establish delivery.
2. Send one explicitly authorized synthetic error with a unique `c3po.probe`
   identifier. Do not deliberately fail a trading cycle, query a provider or
   expose an unauthenticated canary route. A one-off SDK process can exercise
   the production environment without starting the application or touching
   its database.
3. Flush the SDK and record the returned event ID, UTC time, revision and
   service. An event ID or successful flush alone is not a receipt.
4. Find the same event in the `c3po-production` Sentry project and verify its
   service, release and synthetic tag. Record the issue/event URL.
5. Verify a matching alert trigger and the owner's received notification.
   The alert's trigger history proves rule execution; inbox evidence proves
   delivery. A standalone test notification proves routing only.
6. Repeat a browser-only synthetic error against the built client SDK, without
   including user data. Do not deploy a public test button or test endpoint.
7. Verify a sampled performance event separately. Use a local deterministic
   sampling test for the rate and filters; do not temporarily set global
   production sampling to 100% just to obtain a demonstration.
8. Resolve only the synthetic test issues once the evidence is recorded.
   Preserve all genuine errors and their triage state.

Receipts must not contain DSNs, auth tokens, cookies, request bodies or private
financial data. Browser source maps must not be published by Nginx; private
upload requires a separately configured Sentry upload credential.

## Rollback

Revert this change through the normal image pipeline to restore the previous
SDK behavior. To stop API tracing, set `C3PO_SENTRY_TRACES_SAMPLE_RATE=0` and
recreate the API. Browser tracing is compiled into the static bundle and needs
a rebuild with `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0`; changing a runtime
environment variable alone does not change a deployed static bundle.
