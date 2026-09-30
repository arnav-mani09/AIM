"use client";

import { ReactNode, Suspense, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const NAV_ITEMS = [
  { tab: "film", label: "Film + Clips", icon: "🎬" },
  { tab: "games", label: "Games", icon: "🏀" },
  { tab: "chat", label: "AI Chat", icon: "💬" },
  { tab: "teams", label: "Team Spaces", icon: "👥" },
] as const;

// useSearchParams needs a Suspense boundary for the dashboard to prerender.
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense>
      <DashboardShell>{children}</DashboardShell>
    </Suspense>
  );
}

function NavLinks({ isTabActive, onNavigate }: { isTabActive: (tab: string) => boolean; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.tab}
          href={`/dashboard?tab=${item.tab}`}
          onClick={onNavigate}
          className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
            isTabActive(item.tab) ? "bg-accent text-white shadow-soft" : "text-subtext hover:bg-tint hover:text-ink"
          }`}
        >
          <span aria-hidden>{item.icon}</span>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

function AccountLinks({ onSignOut, onNavigate }: { onSignOut: () => void; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1 text-sm">
      <a
        href="mailto:support@aimsports.com"
        onClick={onNavigate}
        className="rounded-xl px-3 py-2 text-subtext transition-colors hover:bg-tint hover:text-ink"
      >
        Get help
      </a>
      <a href="#" onClick={onNavigate} className="rounded-xl px-3 py-2 text-subtext transition-colors hover:bg-tint hover:text-ink">
        Privacy & terms
      </a>
      <button
        onClick={() => {
          onNavigate?.();
          onSignOut();
        }}
        className="mt-1 rounded-xl border border-stroke px-3 py-2 text-left font-semibold text-ink transition-colors hover:bg-tint"
      >
        Sign out
      </button>
    </nav>
  );
}

function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") ?? "film";
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const isTabActive = (tab: string) => {
    if (pathname.startsWith("/dashboard/film") || pathname.startsWith("/dashboard/clips")) {
      return tab === "film";
    }
    if (pathname.startsWith("/dashboard/games")) {
      return tab === "games";
    }
    return pathname === "/dashboard" && activeTab === tab;
  };

  const handleSignOut = () => {
    window.localStorage.removeItem("aim_access_token");
    router.push("/");
  };

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-stroke bg-white px-4 py-6 md:flex">
        <Link href="/" className="flex items-center gap-2 px-2">
          <Image src="/aim-logo.png" alt="AIM logo" width={32} height={32} className="h-8 w-8" />
          <div className="leading-none">
            <p className="text-sm font-semibold tracking-[0.3em] text-ink">AIM</p>
          </div>
        </Link>
        <div className="mt-8 flex-1">
          <p className="label-text px-3">Workspace</p>
          <div className="mt-2">
            <NavLinks isTabActive={isTabActive} />
          </div>
        </div>
        <div className="border-t border-stroke pt-4">
          <AccountLinks onSignOut={handleSignOut} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-stroke bg-white/90 px-4 py-3 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/aim-logo.png" alt="AIM logo" width={28} height={28} className="h-7 w-7" />
            <p className="text-sm font-semibold tracking-[0.3em] text-ink">AIM</p>
          </Link>
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-stroke text-ink"
            aria-label="Open menu"
          >
            ☰
          </button>
        </header>

        <div className="flex-1">{children}</div>
      </div>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close menu"
          />
          <aside className="relative z-10 ml-auto flex h-full w-72 flex-col gap-8 bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold tracking-[0.2em] text-ink">MENU</p>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="rounded-full border border-stroke px-3 py-1 text-xs text-ink"
              >
                Close
              </button>
            </div>
            <div>
              <p className="label-text">Workspace</p>
              <div className="mt-2">
                <NavLinks isTabActive={isTabActive} onNavigate={() => setMobileNavOpen(false)} />
              </div>
            </div>
            <div className="mt-auto border-t border-stroke pt-4">
              <AccountLinks onSignOut={handleSignOut} onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
