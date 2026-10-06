import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  // Vercel exposes NEXT_PUBLIC_VERCEL_ENV (production / preview); local runs are development.
  environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? "development",

  // Capture 100% of traces in dev, 10% in production. Adjust based on traffic.
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,

  // Set SENTRY_DEBUG=1 (or NEXT_PUBLIC_SENTRY_DEBUG=1 in the browser) to log what the SDK sends.
  debug: process.env.SENTRY_DEBUG === "1" || process.env.NEXT_PUBLIC_SENTRY_DEBUG === "1",
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
