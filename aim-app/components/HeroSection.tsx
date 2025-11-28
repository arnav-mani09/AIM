import type { HeroMetric, OverviewItem } from "@/lib/mockData";

interface HeroSectionProps {
  metrics: HeroMetric[];
  overview: OverviewItem[];
}

export function HeroSection({ metrics, overview }: HeroSectionProps) {
  return (
    <section id="general" className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="section-card">
        <p className="pretitle text-xs uppercase tracking-[0.18em] text-subtext">General info</p>
        <h1 className="mt-3 text-4xl font-semibold leading-tight text-[#0e1a2e]">
          All of your high school basketball ops in a single AIM workspace.
        </h1>
        <p className="mt-4 text-lg text-subtext">
          Keep film, stats, clips, and scouting notes in one secure view for the whole staff.
        </p>
        <div className="mt-6 flex flex-wrap gap-4">
          <button className="rounded-2xl bg-accent px-5 py-3 font-semibold text-white">Upload your first game</button>
          <button className="rounded-2xl border border-stroke px-5 py-3 font-semibold text-[#0e1a2e]">View product tour</button>
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          {metrics.map((metric) => (
            <article key={metric.title} className="rounded-2xl border border-stroke bg-white p-4 text-center shadow-soft">
              <h3 className="text-2xl font-semibold text-[#0e1a2e]">{metric.title}</h3>
              <p className="mt-1 text-sm text-subtext">{metric.copy}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="section-card">
        <header>
          <p className="label-text">General overview</p>
          <p className="mt-1 text-sm text-subtext">Control panel snapshot</p>
        </header>
        <ul className="mt-6 flex flex-col divide-y divide-stroke/70">
          {overview.map((item) => (
            <li key={item.title} className="py-4 first:pt-0 last:pb-0">
              <p className="text-sm font-semibold text-[#0e1a2e]">
                {item.title} • {item.value}
              </p>
              <p className="text-sm text-subtext">{item.detail}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
