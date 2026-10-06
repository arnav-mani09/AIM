import { withSentryConfig } from "@sentry/nextjs/config";

/** @type {import('next').NextConfig} */
const nextConfig = {};

export default withSentryConfig(nextConfig, {
  org: "aim-qn",
  project: "javascript-nextjs",

  // Uploads source maps so production stack traces are readable. Without the
  // token (e.g. local builds) the upload is skipped and the build still works.
  authToken: process.env.SENTRY_AUTH_TOKEN,
  widenClientFileUpload: true,

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,
});
