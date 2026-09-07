import type { Breadcrumb, BrowserOptions, ErrorEvent, Event } from "@sentry/react";

type SpanJSON = Parameters<NonNullable<BrowserOptions["beforeSendSpan"]>>[0];
type TransactionEvent = Parameters<NonNullable<BrowserOptions["beforeSendTransaction"]>>[0];

const SAFE_TOKEN = /^[a-zA-Z0-9_.:-]{1,96}$/;
const NATIVE_ERROR = /^(Error|TypeError|RangeError|ReferenceError|SyntaxError|URIError|EvalError|AggregateError|DOMException)$/;
const WEB_VITALS = new Set(["cls", "fcp", "fid", "inp", "lcp", "ttfb", "ttfb.requestTime"]);

/** Sampling is opt-in, with a hard 1% ceiling independent of remote/parent decisions. */
export function browserTraceSampleRate(raw: string | undefined): number {
  if (!raw?.trim()) return 0;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.min(0.01, Math.max(0, value)) : 0;
}

export function validBrowserDsn(raw: string | undefined): string | undefined {
  if (!raw?.trim()) return undefined;
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== "https:" || !url.hostname.endsWith(".sentry.io") ||
        !/^[a-f0-9]+$/i.test(url.username) || url.password || !/^\/\d+$/.test(url.pathname) ||
        url.search || url.hash || (url.port && url.port !== "443")) return undefined;
    return url.href;
  } catch {
    return undefined;
  }
}

/** Only the public application root and compiled asset paths leave the browser. */
export function publicAssetPath(raw: string | undefined): string {
  if (!raw) return "[filtered]";
  try {
    const { pathname } = new URL(raw, "https://c3po.invalid");
    if (pathname === "/") return "/";
    if (/^\/_next\/static\/[a-zA-Z0-9_/.-]+\.(?:js|css)$/.test(pathname)) return pathname;
  } catch {
    // Invalid and custom-protocol URLs are deliberately not retained.
  }
  return "[filtered]";
}

/** Per-tab memory only: no cookie, user identifier, or persistent browser storage. */
export function createMinuteBudget(limit: number, now: () => number = Date.now): () => boolean {
  let startsAt = now();
  let used = 0;
  return () => {
    const current = now();
    if (current - startsAt >= 60_000 || current < startsAt) {
      startsAt = current;
      used = 0;
    }
    if (used >= limit) return false;
    used += 1;
    return true;
  };
}

function safeToken(value: unknown): string | undefined {
  return typeof value === "string" && SAFE_TOKEN.test(value) ? value : undefined;
}

function safeTrace(event: Event): Event["contexts"] {
  const trace = event.contexts?.trace;
  if (!trace) return undefined;
  return { trace: {
    trace_id: trace.trace_id,
    span_id: trace.span_id,
    parent_span_id: trace.parent_span_id,
    op: safeToken(trace.op),
    status: safeToken(trace.status)
  } };
}

function eventMetadata(event: Event): Event {
  return {
    event_id: event.event_id,
    timestamp: event.timestamp,
    start_timestamp: event.start_timestamp,
    level: event.level,
    platform: "javascript",
    release: event.release,
    environment: event.environment,
    contexts: safeTrace(event),
    tags: {
      "c3po.service": "web",
      ...(safeToken(event.tags?.["c3po.probe"]) ? { "c3po.probe": event.tags?.["c3po.probe"] } : {})
    }
  };
}

/** Console, DOM, navigation URLs and arbitrary breadcrumb data can contain portfolio data. */
export function scrubBrowserBreadcrumb(_breadcrumb: Breadcrumb): null {
  return null;
}

export function scrubBrowserError(event: ErrorEvent): ErrorEvent {
  return {
    ...eventMetadata(event),
    type: undefined,
    // Free-form exception messages may include API responses, balances or names.
    // Native type + compiled stack location + release retain error grouping.
    ...(event.message ? { message: "C3PO browser error (message filtered)" } : {}),
    exception: event.exception ? { values: event.exception.values?.map((exception) => ({
      type: NATIVE_ERROR.test(exception.type ?? "") ? exception.type : "Error",
      value: "Browser error message filtered",
      mechanism: exception.mechanism ? {
        type: safeToken(exception.mechanism.type) ?? "generic",
        handled: exception.mechanism.handled
      } : undefined,
      stacktrace: exception.stacktrace ? { frames: exception.stacktrace.frames?.map((frame) => ({
        filename: publicAssetPath(frame.filename),
        function: safeToken(frame.function),
        lineno: frame.lineno,
        colno: frame.colno,
        in_app: frame.in_app
      })) } : undefined
    })) } : undefined
  };
}

export function scrubBrowserSpan(span: SpanJSON): SpanJSON {
  return {
    trace_id: span.trace_id,
    span_id: span.span_id,
    parent_span_id: span.parent_span_id,
    start_timestamp: span.start_timestamp,
    timestamp: span.timestamp,
    op: safeToken(span.op),
    status: safeToken(span.status),
    description: "C3PO browser timing",
    data: {}
  };
}

export function scrubBrowserTransaction(event: TransactionEvent): TransactionEvent {
  return {
    ...eventMetadata(event),
    type: "transaction",
    transaction: "C3PO page",
    transaction_info: { source: "custom" },
    spans: event.spans?.slice(0, 50).map(scrubBrowserSpan),
    measurements: Object.fromEntries(Object.entries(event.measurements ?? {}).filter(
      ([key, item]) => WEB_VITALS.has(key) && Number.isFinite(item.value)
    ).map(([key, item]) => [key, {
      value: item.value,
      unit: item.unit === "millisecond" ? "millisecond" : "none"
    }]))
  };
}
