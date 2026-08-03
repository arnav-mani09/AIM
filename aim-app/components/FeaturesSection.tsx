import type { FeaturePanel, FeatureSummary } from "@/lib/mockData";

interface FeaturesSectionProps {
  summary: FeatureSummary[];
  panels: FeaturePanel[];
}

export function FeaturesSection({ summary, panels }: FeaturesSectionProps) {
  return (
    <section id="features" className="flex flex-col gap-10">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-xl">
          <p className="label-text">Platform features</p>
          <h2 className="mt-2 text-3xl font-semibold text-ink">
            Every module is tuned for coaches, analysts, and players.
          </h2>
          <p className="mt-3 text-subtext">
            Live stats sync, film distribution, and the AIM assistant keep your staff aligned.
          </p>
        </div>
        <ul className="flex flex-col gap-2 text-sm text-subtext">
          {summary.map((item) => (
            <li key={item.title} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
              <span className="font-semibold text-ink">{item.title}</span> {item.copy}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3">
          <button className="rounded-2xl bg-accent px-5 py-3 font-semibold text-white shadow-soft transition-transform hover:-translate-y-0.5 hover:bg-accentDark">
            Schedule walkthrough
          </button>
          <button className="rounded-2xl border border-stroke bg-white px-5 py-3 font-semibold text-ink transition-colors hover:bg-tint">
            Download spec sheet
          </button>
        </div>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        {panels.map((panel) => (
          <article
            key={panel.title}
            className="rounded-2xl border border-stroke bg-white p-6 shadow-soft transition-transform hover:-translate-y-1"
          >
            <p className="pill">{panel.label}</p>
            <h3 className="mt-4 text-xl font-semibold text-ink">{panel.title}</h3>
            <p className="mt-2 text-sm text-subtext">{panel.body}</p>
            <ul className="mt-4 space-y-1.5 text-sm text-subtext">
              {panel.bullets.map((bullet) => (
                <li key={bullet} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />
                  {bullet}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
