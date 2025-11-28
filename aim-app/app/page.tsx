import Image from "next/image";

import { ExampleSection } from "@/components/ExampleSection";
import { FeaturesSection } from "@/components/FeaturesSection";
import { HeroSection } from "@/components/HeroSection";
import { getPlatformData } from "@/lib/platformData";

export default async function Home() {
  const { heroMetrics, overviewItems, exampleCards, featureSummary, featurePanels } = await getPlatformData(
    process.env.NEXT_PUBLIC_BASE_URL
  );

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-10 border-b border-stroke bg-white/90 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Image src="/aim-logo.png" alt="AIM logo" width={56} height={56} className="h-14 w-14" priority />
            <div>
              <p className="text-xs uppercase tracking-[0.5em] text-subtext">AIM</p>
              <p className="text-sm text-subtext">Analyze • Improve • Master</p>
            </div>
          </div>
          <nav className="hidden items-center gap-6 text-sm text-subtext md:flex">
            <a href="#general" className="hover:text-[#0e1a2e]">General Info</a>
            <a href="#example" className="hover:text-[#0e1a2e]">Example</a>
            <a href="#features" className="hover:text-[#0e1a2e]">Features</a>
            <a href="#about" className="hover:text-[#0e1a2e]">About</a>
          </nav>
          <button className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-white shadow-soft">Request Demo</button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10">
        <HeroSection metrics={heroMetrics} overview={overviewItems} />
        <ExampleSection cards={exampleCards} />
        <FeaturesSection summary={featureSummary} panels={featurePanels} />

        <section id="about" className="section-card">
          <h2 className="text-2xl font-semibold text-[#0e1a2e]">About AIM</h2>
          <p className="mt-2 italic text-subtext">(Placeholder content. Add program story here.)</p>
        </section>
      </main>

      <footer className="border-t border-stroke bg-[#f0f4fa] px-6 py-8">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h4 className="text-lg font-semibold text-[#0e1a2e]">AIM</h4>
            <p className="text-sm text-subtext">Hudl-level structure with AI-native workflows.</p>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-subtext">
            <a href="#general">General Info</a>
            <a href="#example">Example</a>
            <a href="#features">Features</a>
            <a href="#about">About</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
