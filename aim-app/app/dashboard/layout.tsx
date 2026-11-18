"use client";

import { ReactNode, Suspense, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const NAV_ITEMS = [
  { tab: "film", label: "Film + Clips", path: "m9 8 7 4-7 4V8Z M4 3h16v18H4z" },
  { tab: "season", label: "Season", path: "M4 20V10m8 10V4m8 16V7" },
  { tab: "scouting", label: "Scouting", path: "m16 16 5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" },
  { tab: "games", label: "Games", path: "M4 5h16v16H4z M8 2v6m8-6v6M4 11h16m-12 5h2m4 0h2" },
  { tab: "chat", label: "AI Chat", path: "M21 4H3v13h5v4l5-4h8V4ZM7 9h10M7 13h6" },
  { tab: "teams", label: "Team Spaces", path: "M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3m20 0v-3a4 4 0 0 0-3-4M13 3a4 4 0 0 1 0 8 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" },
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
    <nav aria-label="Workspace" className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.tab}
          href={`/dashboard?tab=${item.tab}`}
          onClick={onNavigate}
          aria-current={isTabActive(item.tab) ? "page" : undefined}
          className={`dashboard-nav-link ${isTabActive(item.tab) ? "is-active" : ""}`}
        >
          <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={item.path} /></svg>
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

function AccountLinks({ onSignOut, onNavigate }: { onSignOut: () => void; onNavigate?: () => void }) {
  return (
    <nav aria-label="Account" className="flex flex-col gap-1 text-sm">
      <a
        href="mailto:support@aimsports.com"
        onClick={onNavigate}
        className="dashboard-nav-link"
      >
        Get help
      </a>
      <button
        onClick={() => {
          onNavigate?.();
          onSignOut();
        }}
        className="dashboard-nav-link mt-1 w-full text-left"
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
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const dialog = dialogRef.current;
    const content = contentRef.current;
    const menuButton = menuButtonRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (content) content.inert = true;
    dialog?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNavOpen(false);
      }
      if (event.key !== "Tab" || !dialog) return;
      const elements = Array.from(dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'));
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    const desktop = window.matchMedia("(min-width: 768px)");
    const onResize = () => { if (desktop.matches) setMobileNavOpen(false); };
    desktop.addEventListener("change", onResize);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      if (content) content.inert = false;
      document.removeEventListener("keydown", onKeyDown);
      desktop.removeEventListener("change", onResize);
      menuButton?.focus();
    };
  }, [mobileNavOpen]);

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
    <div className="dashboard-shell flex min-h-screen">
      <a href="#dashboard-content" className="dashboard-skip-link">Skip to workspace</a>
      <aside aria-label="Main navigation" className="dashboard-sidebar sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto px-4 py-7 md:flex">
        <Link href="/" className="flex items-center gap-2 px-2">
          <Image src="/aim-logo.png" alt="AIM logo" width={32} height={32} className="h-8 w-8" />
          <div className="leading-none">
            <p className="text-sm font-semibold tracking-[0.3em] text-white">AIM</p>
            <p className="mt-2 text-[10px] tracking-[0.12em] text-slate-400">FILM. INSIGHT. ADVANTAGE.</p>
          </div>
        </Link>
        <div className="mt-8 flex-1">
          <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">Workspace</p>
          <div className="mt-2">
            <NavLinks isTabActive={isTabActive} />
          </div>
        </div>
        <div className="mt-8 border-t border-white/10 pt-4">
          <AccountLinks onSignOut={handleSignOut} />
        </div>
      </aside>

      <div ref={contentRef} className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-stroke bg-white/90 px-4 py-3 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/aim-logo.png" alt="AIM logo" width={28} height={28} className="h-7 w-7" />
            <p className="text-sm font-semibold tracking-[0.3em] text-ink">AIM</p>
          </Link>
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-stroke text-ink"
            aria-label="Open menu"
            aria-expanded={mobileNavOpen}
            aria-controls="dashboard-mobile-menu"
          >
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
          </button>
        </header>

        <div id="dashboard-content" tabIndex={-1} className="dashboard-workspace min-w-0 flex-1">{children}</div>
      </div>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close menu"
          />
          <aside ref={dialogRef} id="dashboard-mobile-menu" role="dialog" aria-modal="true" aria-labelledby="dashboard-menu-title" className="dashboard-sidebar relative z-10 ml-auto flex h-full w-72 max-w-[90vw] flex-col gap-8 overflow-y-auto p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <p id="dashboard-menu-title" className="text-sm font-semibold tracking-[0.2em] text-white">WORKSPACE</p>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="rounded-lg border border-white/20 px-3 py-2 text-xs text-white"
              >
                Close
              </button>
            </div>
            <div>
              <div className="mt-2">
                <NavLinks isTabActive={isTabActive} onNavigate={() => setMobileNavOpen(false)} />
              </div>
            </div>
            <div className="mt-auto border-t border-white/10 pt-4">
              <AccountLinks onSignOut={handleSignOut} onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
