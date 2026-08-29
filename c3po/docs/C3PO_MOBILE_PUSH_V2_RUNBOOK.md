# C3PO Mobile Push V2 — Runbook

## Configuration

Production requires `C3PO_PUSH_VAPID_PRIVATE_KEY` and `C3PO_PUSH_VAPID_PUBLIC_KEY` in the
GitHub `production` environment. The deploy workflow stages them through an ephemeral mode-600
file, updates `/opt/chief-of-staff-digital/.env`, restores mode 600, and removes the staged file
before recreating containers. Values must never be printed or committed.

`C3PO_PUSH_VAPID_SUBJECT` defaults to `mailto:eu@eduardocastro.com.br`; delivery timeout defaults
to three seconds. Rotating VAPID keys invalidates every browser subscription and therefore requires
the user to activate alerts again.

## Operational Contract

- Subscription and preference changes require an authenticated C3PO session.
- The manual test route is owner-only.
- Push delivery is best-effort. A timeout, provider rejection, or diagnostics failure never changes
  the result of the job that emitted it.
- HTTP 404/410 from a push endpoint logically revokes that subscription.
- Event keys suppress duplicate alerts from retries.
- The service worker handles only `push` and `notificationclick`; it has no fetch or cache handler.
- A deploy during an open US session may emit one catch-up batch of `sell_win` notifications for
  positive episodes already closed in that session. This is expected: the observer rebuilds the
  current session from the canonical ledger after restart, while stable episode event keys keep the
  catch-up idempotent and prevent duplicate delivery. Schedule display-only deploys outside the
  session when that one-time backlog would be distracting.

## Device Acceptance

1. Install/open the C3PO PWA on iOS 16.4 or later.
2. Open the authenticated profile and tap **Ativar alertas**.
3. Grant the iOS permission, then choose categories explicitly.
4. With the PWA closed, use **Enviar notificação de teste** as owner.
5. Confirm the locked-screen notification and that tapping it opens Storm Troops.
6. Preserve the screenshot as the factual acceptance attestation.

## Supervised Emit

For an existing factual event only:

```bash
docker compose --env-file .env -f c3po/compose.yml run --rm api \
  python -m app.push_notifications emit \
  --category job_failure \
  --title "Job crítico falhou" \
  --body "Consulte a evidência no Storm Troops." \
  --deep-link '/?view=health' \
  --event-key 'job-name:YYYY-MM-DD'
```

Never use this command to fabricate a kill-criterion or table-reading event. Those categories are
emitted only by their factual publishers when they exist.
