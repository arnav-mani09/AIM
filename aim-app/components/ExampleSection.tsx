import type { GameStats } from "@/lib/statsData";

interface ExampleSectionProps {
  stats: GameStats;
}

export function ExampleSection({ stats }: ExampleSectionProps) {
  const possession = stats.possession;
  const summary = stats.summary;
  const insights = stats.insights;
  return (
    <section id="example">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="label-text">Example: {stats.matchup}</p>
          <h2 className="mt-2 text-3xl font-semibold text-ink">Sample dashboard</h2>
        </div>
        <span className="pill">sample data</span>
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
          <p className="label-text">Possession split</p>
          <div className="mt-4 flex flex-col gap-2">
            {possession.map((team) => (
              <div key={team.team} className="flex items-center justify-between text-sm text-ink">
                <span>{team.team}</span>
                <strong>{team.percentage}%</strong>
              </div>
            ))}
          </div>
          <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-tint">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-[#3f7cb8] transition-[width]"
              style={{ width: `${possession[0]?.percentage ?? 0}%` }}
            />
          </div>
        </article>
        <article className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
          <p className="label-text">Game summary</p>
          <ul className="mt-4 grid grid-cols-3 gap-2 text-center">
            <li className="rounded-xl bg-tint/70 px-2 py-3">
              <strong className="block text-lg text-accent">{summary.offensiveRating}</strong>
              <span className="text-xs text-subtext">ORtg</span>
            </li>
            <li className="rounded-xl bg-tint/70 px-2 py-3">
              <strong className="block text-lg text-accent">{summary.effectiveFG}%</strong>
              <span className="text-xs text-subtext">eFG</span>
            </li>
            <li className="rounded-xl bg-tint/70 px-2 py-3">
              <strong className="block text-lg text-accent">{summary.turnoverRate}%</strong>
              <span className="text-xs text-subtext">TO rate</span>
            </li>
          </ul>
        </article>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {insights.map((insight, index) => (
          <article
            key={`${insight.label}-${insight.player}-${index}`}
            className="rounded-2xl border border-stroke bg-white p-5 shadow-soft"
          >
            <p className="label-text">{insight.label}</p>
            <h3 className="mt-3 text-xl font-semibold text-ink">{insight.player}</h3>
            <p className="mt-2 text-sm text-subtext">{insight.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
