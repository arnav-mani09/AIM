import type { FeaturePanel, FeatureSummary } from "@/lib/mockData";

interface FeaturesSectionProps {
  summary: FeatureSummary[];
  panels: FeaturePanel[];
}

export function FeaturesSection({ summary, panels }: FeaturesSectionProps) {
  return (
    <section id="features" className="features">
      <div className="flex flex-col gap-6">
        <div>
          <p className="label-text">Platform features</p>
          <h2 className="mt-2 text-3xl font-semibold text-[#0e1a2e]">
            Every module is tuned for coaches, analysts, and players.
          </h2>
          <p className="mt-3 text-subtext">
            Live stats sync, film distribution, and the AIM assistant keep your staff aligned.
          </p>
        </div>
        <ul className="summary-list">
          {summary.map((item) => (
            <li key={item.title}>
              <span className="font-semibold text-[#0e1a2e]">{item.title}</span> {item.copy}
            </li>
          ))}
        </ul>
        <div className="feature-cta">
          <button className="rounded-2xl bg-accent px-5 py-3 font-semibold text-white">Schedule walkthrough</button>
          <button className="rounded-2xl border border-stroke px-5 py-3 font-semibold text-[#0e1a2e]">Download spec sheet</button>
        </div>
      </div>
      <div className="feature-scroll" tabIndex={0} aria-label="Feature details">
        {panels.map((panel) => (
          <article key={panel.title} className="feature-panel">
            <p className="label-text">{panel.label}</p>
            <h3 className="mt-3 text-xl font-semibold text-[#0e1a2e]">{panel.title}</h3>
            <p className="text-sm text-subtext">{panel.body}</p>
            <ul className="mt-4 list-disc space-y-1 pl-4 text-sm text-subtext">
              {panel.bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
