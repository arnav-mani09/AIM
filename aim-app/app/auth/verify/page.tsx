'use client';

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export default function VerifyPage() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("Verifying your account...");

  useEffect(() => {
    async function verify() {
      if (!token) {
        setStatus("error");
        setMessage("Missing verification token.");
        return;
      }
      try {
        const response = await fetch(`${baseUrl}/api/v1/auth/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail ?? "Invalid token");
        }
        setStatus("success");
        setMessage("Account verified. Redirecting to sign in...");
        setTimeout(() => router.push("/auth/login"), 1800);
      } catch (error) {
        setStatus("error");
        setMessage(error instanceof Error ? error.message : "Verification failed.");
      }
    }
    verify();
  }, [token, router]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-6 py-12">
      <div className="section-card text-center">
        <h1 className="text-2xl font-semibold text-[#0e1a2e]">Email verification</h1>
        <p className={`mt-4 text-sm ${status === "error" ? "text-red-500" : "text-subtext"}`}>{message}</p>
      </div>
    </main>
  );
}
