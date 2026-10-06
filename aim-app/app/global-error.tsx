"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body>
        {/* The App Router doesn't expose status codes for errors, so 0 renders a generic message. */}
        <NextError statusCode={0} />
      </body>
    </html>
  );
}
