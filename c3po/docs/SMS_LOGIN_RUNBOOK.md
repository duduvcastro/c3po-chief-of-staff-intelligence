# SMS Login Runbook

## Scope

SMS is the preferred login factor when a confirmed phone and a healthy Twilio
Verify configuration are present. TOTP and email remain recovery paths. A
Twilio outage falls back to email and creates an audit event without exposing
the phone number.

Brazilian mobile numbers are stored in encrypted E.164 form, for example
`+5511999999999`. The UI and audit records expose only the last four digits.

## Twilio preparation

1. Create a Twilio Verify Service with SMS enabled.
2. Enable delivery to Brazil in Twilio geographic permissions.
3. If the Twilio account is still in trial, add the destination phone to the
   verified caller IDs allowed by the account.
4. For Safari's strongest one-time-code association, create a Verify custom
   template whose final line follows Apple's domain-bound format:

   ```text
   @c3po.eduardocastro.com.br #{{code}}
   ```

   Custom Verify templates may require Twilio approval. Login still works
   without this template, and the existing `autocomplete="one-time-code"`
   field allows the operating system to suggest codes it recognizes.

## Production configuration

Edit `/opt/chief-of-staff-digital/.env` and set:

```dotenv
C3PO_TWILIO_ACCOUNT_SID=AC...
C3PO_TWILIO_AUTH_TOKEN=...
C3PO_TWILIO_VERIFY_SERVICE_SID=VA...
C3PO_TWILIO_VERIFY_TEMPLATE_SID=HJ...
```

The template SID is optional. The other three values are required. Never put
real values in Git, shell history, logs, screenshots, or audit metadata.

After the deployment is green, recreate only the API so it loads the new
environment and applies migration `030_auth_sms.sql`:

```bash
cd /opt/chief-of-staff-digital
docker compose --env-file .env -f c3po/compose.yml up -d --build api
docker compose --env-file .env -f c3po/compose.yml ps api
```

## Enrollment and validation

1. Sign in with the current TOTP or email path.
2. Open the user profile and select `SMS de acesso`.
3. Enter the Brazilian number with `+55`, request the code, and confirm it.
4. Sign out and request a new login code.
5. Confirm the response says the code was sent by SMS and that Safari offers
   the one-time code above the keyboard when the message arrives.
6. Complete the login and confirm the normal login audit event.
7. Keep TOTP configured as recovery until SMS has been validated on the real
   device and network.

## Fail-safe behavior

- Provider credentials absent: SMS is shown as awaiting configuration and the
  existing login behavior remains unchanged.
- SMS delivery failure: the request falls back to email and records
  `auth.sms_delivery_failed` without the phone number.
- Invalid or expired code: no session is created and the existing attempt and
  IP rate limits apply.
- Phone replacement or SMS removal: a fresh code to the affected phone is
  required before the change is committed.
