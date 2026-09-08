import * as Sentry from "@sentry/react";
import {
  browserTraceSampleRate,
  createMinuteBudget,
  scrubBrowserBreadcrumb,
  scrubBrowserError,
  scrubBrowserSpan,
  scrubBrowserTransaction,
  validBrowserDsn
} from "./lib/sentry-privacy";

// This application is exported to static HTML and served by nginx: there is no
// Next.js server to instrument. Next >=15.3 loads this module before hydration.
const dsn = validBrowserDsn(process.env.NEXT_PUBLIC_SENTRY_DSN);

if (dsn) {
  const errors = createMinuteBudget(20);
  const transactions = createMinuteBudget(20);
  const traceRate = browserTraceSampleRate(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE);

  try {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "production",
      release: process.env.NEXT_PUBLIC_C3PO_BUILD_SHA || "development",
      sampleRate: 1,
      tracesSampler: () => traceRate,
      traceLifecycle: "static",
      streamGenAiSpans: false,
      tracePropagationTargets: [],
      sendDefaultPii: false,
      enableLogs: false,
      enableMetrics: false,
      maxBreadcrumbs: 0,
      sendClientReports: false,
      defaultIntegrations: false,
      integrations: [
        Sentry.inboundFiltersIntegration(),
        Sentry.browserApiErrorsIntegration(),
        Sentry.globalHandlersIntegration(),
        Sentry.linkedErrorsIntegration(),
        Sentry.dedupeIntegration(),
        ...(traceRate > 0 ? [Sentry.browserTracingIntegration({
          beforeStartSpan: (options) => ({ ...options, name: "C3PO page", attributes: {} }),
          traceFetch: false,
          traceXHR: false,
          shouldCreateSpanForRequest: () => false,
          enableLongTask: false,
          enableLongAnimationFrame: false,
          enableInp: false,
          ignoreResourceSpans: ["resource.script", "resource.css", "resource.img", "resource.other"],
          ignorePerformanceApiSpans: [/.*/],
          linkPreviousTrace: "off",
          finalTimeout: 15_000
        })] : [])
      ],
      beforeBreadcrumb: scrubBrowserBreadcrumb,
      beforeSend: (event, hint) => {
        // Attachments are outside the event body and must be filtered separately.
        hint.attachments = [];
        return errors() ? scrubBrowserError(event) : null;
      },
      beforeSendSpan: scrubBrowserSpan,
      beforeSendTransaction: (event) => transactions() ? scrubBrowserTransaction(event) : null
    });
    Sentry.setTag("c3po.service", "web");
  } catch {
    // Observability configuration must not stop the application from rendering.
  }
}
