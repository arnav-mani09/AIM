import Image from "next/image";
import Link from "next/link";

import { ExampleSection } from "@/components/ExampleSection";
import { FeaturesSection } from "@/components/FeaturesSection";
import { HeroSection } from "@/components/HeroSection";
import { getPlatformData } from "@/lib/platformData";
import { getGameStats } from "@/lib/statsData";

export default async function Home() {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL;
  const [platformData, stats] = await Promise.all([getPlatformData(), getGameStats(baseUrl)]);
  const { heroMetrics, overviewItems, featureSummary, featurePanels } = platformData;

  const navLinks = [
    { href: "#general", label: "Overview" },
    { href: "#example", label: "Example" },
    { href: "#features", label: "Features" },
    { href: "#about", label: "About" },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-20 border-b border-stroke bg-white/80 px-6 py-3.5 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Image src="/aim-logo.png" alt="AIM logo" width={40} height={40} className="h-10 w-10" priority />
            <div className="leading-none">
              <p className="text-sm font-semibold tracking-[0.3em] text-ink">AIM</p>
              <p className="mt-1 text-[11px] text-subtext">Analyze • Improve • Master</p>
            </div>
          </div>
          <nav className="hidden items-center gap-7 text-sm font-medium text-subtext md:flex">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="transition-colors hover:text-ink">
                {link.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link
              href="/auth/login"
              className="rounded-full px-4 py-2 text-sm font-semibold text-subtext transition-colors hover:bg-tint hover:text-ink"
            >
              Sign in
            </Link>
            <Link
              href="/auth/register"
              className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white shadow-soft transition-transform hover:-translate-y-0.5 hover:bg-accentDark"
            >
              Sign up
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-16 px-6 py-14">
          <HeroSection metrics={heroMetrics} overview={overviewItems} />
        </div>

        <div className="bg-tint/60 py-16">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-16 px-6">
            <ExampleSection stats={stats} />
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-6xl flex-col gap-16 px-6 py-16">
          <FeaturesSection summary={featureSummary} panels={featurePanels} />

          <section id="about" className="section-card">
            <p className="label-text">About</p>
            <h2 className="mt-2 text-2xl font-semibold text-ink">About AIM</h2>
            <p className="mt-2 italic text-subtext">(Placeholder content. Add program story here.)</p>
          </section>
        </div>
      </main>

      <footer className="border-t border-stroke bg-white px-6 py-10">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Image src="/aim-logo.png" alt="AIM logo" width={32} height={32} className="h-8 w-8" />
            <div>
              <h4 className="text-base font-semibold text-ink">AIM</h4>
              <p className="text-sm text-subtext">Hudl-level structure with AI-native workflows.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-subtext">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-ink">
                {link.label}
              </a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
