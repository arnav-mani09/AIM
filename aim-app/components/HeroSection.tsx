import type { HeroMetric, OverviewItem } from "@/lib/mockData";

interface HeroSectionProps {
  metrics: HeroMetric[];
  overview: OverviewItem[];
}

export function HeroSection({ metrics, overview }: HeroSectionProps) {
  return (
    <section id="general" className="relative grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
      <div
        className="pointer-events-none absolute -top-24 left-1/3 -z-10 h-72 w-72 rounded-full bg-accent/10 blur-3xl"
        aria-hidden
      />
      <div className="section-card relative overflow-hidden">
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-tint" aria-hidden />
        <p className="pill">General info</p>
        <h1 className="relative mt-4 text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl">
          All of your high school basketball ops in a single{" "}
          <span className="bg-gradient-to-r from-accent to-[#3f7cb8] bg-clip-text text-transparent">
            AIM workspace
          </span>
          .
        </h1>
        <p className="relative mt-4 max-w-lg text-lg text-subtext">
          Keep film, stats, clips, and scouting notes in one secure view for the whole staff.
        </p>
        <div className="relative mt-7 flex flex-wrap gap-3">
          <button className="rounded-2xl bg-accent px-5 py-3 font-semibold text-white shadow-soft transition-transform hover:-translate-y-0.5 hover:bg-accentDark">
            Upload your first game
          </button>
          <button className="rounded-2xl border border-stroke bg-white px-5 py-3 font-semibold text-ink transition-colors hover:bg-tint">
            View product tour
          </button>
        </div>
        <div className="relative mt-8 grid gap-4 sm:grid-cols-3">
          {metrics.map((metric) => (
            <article
              key={metric.title}
              className="rounded-2xl border border-stroke bg-white p-4 text-center shadow-soft transition-transform hover:-translate-y-1"
            >
              <h3 className="text-2xl font-semibold text-accent">{metric.title}</h3>
              <p className="mt-1 text-sm text-subtext">{metric.copy}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="flex flex-col rounded-3xl border border-ink bg-ink p-8 text-white shadow-soft">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-[0.7rem] uppercase tracking-[0.14em] text-white/60">General overview</p>
            <p className="mt-1 text-sm text-white/80">Control panel snapshot</p>
          </div>
          <span className="flex h-2 w-2 rounded-full bg-emerald-400" aria-hidden />
        </header>
        <ul className="mt-6 flex flex-1 flex-col divide-y divide-white/10">
          {overview.map((item) => (
            <li key={item.title} className="py-4 first:pt-0 last:pb-0">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-sm font-medium text-white/70">{item.title}</p>
                <p className="text-lg font-semibold text-white">{item.value}</p>
              </div>
              <p className="mt-1 text-sm text-white/50">{item.detail}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
