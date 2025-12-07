'use client';

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus("loading");
    setMessage("");
    try {
      const params = new URLSearchParams();
      params.append("username", email);
      params.append("password", password);
      const response = await fetch(`${baseUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params.toString(),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? "Invalid credentials");
      }
      const data = await response.json();
      if (!data?.access_token) {
        throw new Error("Login did not return an access token");
      }
      window.localStorage.setItem("aim_access_token", data.access_token);
      setStatus("success");
      setMessage("Signed in successfully. Redirecting to dashboard...");
      setTimeout(() => router.push("/dashboard"), 1200);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Unexpected error");
    }
  };

  return (
    <main className="mx-auto min-h-screen w-full max-w-md px-6 py-12">
      <Link href="/" className="mb-8 flex items-center gap-2">
        <Image src="/aim-logo.png" alt="AIM logo" width={48} height={48} className="h-12 w-12" />
        <div>
          <p className="text-xs uppercase tracking-[0.5em] text-subtext">AIM</p>
          <p className="text-sm text-subtext">Analyze • Improve • Master</p>
        </div>
      </Link>
      <div className="section-card">
        <h1 className="text-2xl font-semibold text-[#0e1a2e]">Sign in to AIM</h1>
        <p className="mt-2 text-sm text-subtext">Access film uploads, chat, and your team workspaces.</p>
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="rounded-xl border border-stroke bg-transparent px-3 py-2 text-[#0e1a2e] focus:border-accent focus:outline-none"
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="rounded-xl border border-stroke bg-transparent px-3 py-2 text-[#0e1a2e] focus:border-accent focus:outline-none"
              required
            />
          </label>
          <button
            type="submit"
            className="rounded-2xl bg-accent px-4 py-2 font-semibold text-white"
            disabled={status === "loading"}
          >
            {status === "loading" ? "Signing in..." : "Sign in"}
          </button>
          {message && (
            <p className={`text-sm ${status === "error" ? "text-red-500" : "text-green-600"}`}>
              {message}
            </p>
          )}
        </form>
      </div>
    </main>
  );
}
