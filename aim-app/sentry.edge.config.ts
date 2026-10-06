import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.VERCEL_ENV ?? "development",

  // Capture 100% of traces in dev, 10% in production. Adjust based on traffic.
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,

  // Set SENTRY_DEBUG=1 (or NEXT_PUBLIC_SENTRY_DEBUG=1 in the browser) to log what the SDK sends.
  debug: process.env.SENTRY_DEBUG === "1" || process.env.NEXT_PUBLIC_SENTRY_DEBUG === "1",
});
