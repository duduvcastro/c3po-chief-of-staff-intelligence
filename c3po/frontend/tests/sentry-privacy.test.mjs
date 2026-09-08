import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import * as Sentry from "@sentry/react";
import { renderNginxConfig } from "../scripts/build-nginx-config.cjs";
import {
  browserTraceSampleRate,
  createMinuteBudget,
  publicAssetPath,
  scrubBrowserBreadcrumb,
  scrubBrowserError,
  scrubBrowserSpan,
  scrubBrowserTransaction,
  validBrowserDsn
} from "../lib/sentry-privacy.ts";

const DSN = "https://012345abcdef@o123.ingest.us.sentry.io/456";
const SECRET = "sensitive-portfolio-ypf-secret";

test("sampling is opt-in and cannot exceed 1%", () => {
  for (const value of [undefined, "", " ", "bad", "Infinity", "-0.1", "0"]) {
    assert.equal(browserTraceSampleRate(value), 0);
  }
  assert.equal(browserTraceSampleRate("0.003"), 0.003);
  assert.equal(browserTraceSampleRate("1"), 0.01);
  assert.equal(browserTraceSampleRate("0.01"), 0.01);
});

test("budget resets without storage and caps repeated errors in one tab", () => {
  let now = 100;
  const take = createMinuteBudget(2, () => now);
  assert.equal(take(), true);
  assert.equal(take(), true);
  assert.equal(take(), false);
  now += 59_999;
  assert.equal(take(), false);
  now += 1;
  assert.equal(take(), true);
});

test("DSN policy only accepts official HTTPS ingest with public DSN key and numeric project", () => {
  assert.equal(validBrowserDsn(DSN), DSN);
  for (const value of [undefined, "", "https://evil-sentry.io/1", "https://abc@sentry.io.evil/1",
    "https://abc:password@o1.ingest.sentry.io/1", "http://abc@o1.ingest.sentry.io/1",
    "https://abc@o1.ingest.sentry.io/1?token=123", "https://abc@o1.ingest.sentry.io/1#secret",
    "https://abc@o1.ingest.sentry.io:9000/1", "https://abc@o1.ingest.sentry.io/project"]) {
    assert.equal(validBrowserDsn(value), undefined, value);
  }
});

test("stack URLs lose credentials, query, fragment and private paths", () => {
  assert.equal(publicAssetPath(`https://user:${SECRET}@site.test/_next/static/chunks/app-a1.js?token=${SECRET}#${SECRET}`), "/_next/static/chunks/app-a1.js");
  for (const value of [`/api/portfolio/${SECRET}`, `/assets/${SECRET}.png`, `data:text/plain,${SECRET}`]) {
    assert.equal(publicAssetPath(value), "[filtered]");
  }
});

test("error event retains technical stack and proof id while removing free text and private fields", () => {
  const source = {
    type: undefined,
    event_id: "a".repeat(32),
    release: "c3po-sha",
    message: SECRET,
    user: { email: SECRET },
    request: { url: SECRET, headers: { Authorization: SECRET }, data: SECRET },
    extra: { balance: SECRET },
    tags: { customer: SECRET, "c3po.probe": "synthetic-20260907" },
    breadcrumbs: [{ category: "console", message: SECRET }],
    contexts: { portfolio: { balance: SECRET }, trace: { trace_id: "b".repeat(32), span_id: "c".repeat(16), data: { token: SECRET } } },
    exception: { values: [{ type: "TypeError", value: SECRET, mechanism: { type: "generic", handled: false, data: { token: SECRET } }, stacktrace: { frames: [{
      filename: `https://site.test/_next/static/chunks/main.js?query=${SECRET}`,
      function: "renderView", lineno: 12, colno: 42, vars: { balance: SECRET }, context_line: SECRET
    }] } }] }
  };
  const event = scrubBrowserError(source);
  assert.equal(JSON.stringify(event).includes(SECRET), false);
  assert.equal(event.event_id, source.event_id);
  assert.equal(event.exception.values[0].type, "TypeError");
  assert.equal(event.exception.values[0].stacktrace.frames[0].lineno, 12);
  assert.equal(event.tags["c3po.probe"], "synthetic-20260907");
  assert.equal(event.tags["c3po.service"], "web");
  assert.equal(source.extra.balance, SECRET, "sanitizer must not mutate application objects");
  assert.equal(scrubBrowserBreadcrumb({ category: "ui.click", message: SECRET }), null);
});

test("performance payload removes URL/DOM attributes, free-form measurements and excess spans", () => {
  const span = { trace_id: "a".repeat(32), span_id: "b".repeat(16), start_timestamp: 1, timestamp: 2,
    description: SECRET, op: "http.client", data: { "url.full": SECRET, "ui.component_name": SECRET } };
  const event = scrubBrowserTransaction({ type: "transaction", transaction: SECRET,
    request: { data: SECRET }, spans: Array.from({ length: 60 }, () => span),
    measurements: { lcp: { value: 123, unit: "millisecond" }, balance: { value: 999 }, cls: { value: NaN } } });
  assert.equal(event.spans.length, 50);
  assert.deepEqual(event.measurements, { lcp: { value: 123, unit: "millisecond" } });
  assert.equal(JSON.stringify(event).includes(SECRET), false);
  assert.deepEqual(scrubBrowserSpan(span).data, {});
});

test("nginx keeps the existing CSP and permits only this DSN's exact origin", () => {
  const original = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");
  const rendered = renderNginxConfig(original, DSN);
  assert.equal(rendered, original.replace("connect-src 'self';", "connect-src 'self' https://o123.ingest.us.sentry.io;"));
  assert.equal(rendered.includes("012345abcdef"), false, "DSN key must not enter nginx configuration");
  assert.equal(renderNginxConfig(original, ""), original);
  assert.throws(() => renderNginxConfig(original, "https://abc@evil.test/456"));
  assert.throws(() => renderNginxConfig(original, `${DSN}?inject=;connect-src%20*`));
  assert.throws(() => renderNginxConfig("missing directive", DSN));
});

test("real SDK envelope filters scope attachments and event content before transport", async () => {
  const envelopes = [];
  const client = Sentry.init({
    dsn: DSN, release: "synthetic-review", defaultIntegrations: false,
    sendDefaultPii: false, sendClientReports: false,
    transport: () => ({ send: async (envelope) => { envelopes.push(envelope); return { statusCode: 200 }; }, flush: async () => true }),
    beforeSend: (event, hint) => { hint.attachments = []; return scrubBrowserError(event); }
  });
  try {
    const id = Sentry.withScope((scope) => {
      scope.setUser({ email: SECRET });
      scope.setExtra("balance", SECRET);
      scope.addAttachment({ filename: "portfolio.txt", data: SECRET });
      scope.setTag("c3po.probe", "synthetic-sdk-test");
      return Sentry.captureException(new Error(SECRET));
    });
    assert.equal(await Sentry.flush(2000), true);
    assert.equal(envelopes.length, 1);
    const envelope = envelopes[0];
    assert.equal(envelope[1].length, 1, "no attachment item may reach transport");
    assert.equal(envelope[1][0][0].type, "event");
    assert.equal(envelope[1][0][1].event_id, id);
    assert.equal(JSON.stringify(envelope).includes(SECRET), false);
  } finally {
    await client.close();
  }
});
