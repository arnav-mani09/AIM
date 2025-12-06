'use client';

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus("loading");
    setMessage("");
    try {
      const response = await fetch(`${baseUrl}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? "Unable to create account");
      }
      setStatus("success");
      setMessage("Account created. Check your inbox for confirmation.");
      setTimeout(() => router.push("/auth/login"), 1500);
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
        <h1 className="text-2xl font-semibold text-[#0e1a2e]">Create an AIM account</h1>
        <p className="mt-2 text-sm text-subtext">
          Get access to film uploads, AI chat, and team collaboration.
        </p>
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            Full name
            <input
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="rounded-xl border border-stroke bg-transparent px-3 py-2 text-[#0e1a2e] focus:border-accent focus:outline-none"
              required
            />
          </label>
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
            {status === "loading" ? "Creating account..." : "Sign up"}
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
