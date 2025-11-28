import type { ExampleCard } from "@/lib/mockData";
import type { GameStats } from "@/lib/statsData";

interface ExampleSectionProps {
  cards: ExampleCard[];
  stats: GameStats;
}

export function ExampleSection({ cards, stats }: ExampleSectionProps) {
  const possession = stats.possession;
  const summary = stats.summary;
  return (
    <section id="example" className="section-card">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="label-text">Example: {stats.matchup}</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#0e1a2e]">Sample dashboard</h2>
        </div>
        <span className="pill">sample data</span>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
          <p className="label-text">Possession split</p>
          <div className="mt-4 flex flex-col gap-2">
            {possession.map((team) => (
              <div key={team.team} className="flex items-center justify-between text-sm text-[#0e1a2e]">
                <span>{team.team}</span>
                <strong>{team.percentage}%</strong>
              </div>
            ))}
          </div>
          <div className="mt-3 h-3 rounded-full bg-[#ecf2fb]">
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${possession[0]?.percentage ?? 0}%` }}
            />
          </div>
        </article>
        <article className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
          <p className="label-text">Game summary</p>
          <ul className="mt-4 space-y-2 text-sm text-[#0e1a2e]">
            <li>
              <strong className="text-base">{summary.offensiveRating}</strong> Offensive rating
            </li>
            <li>
              <strong className="text-base">{summary.effectiveFG}%</strong> eFG
            </li>
            <li>
              <strong className="text-base">{summary.turnoverRate}%</strong> Turnover rate
            </li>
          </ul>
        </article>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <article key={card.label} className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
            <p className="label-text">{card.label}</p>
            <h3 className="mt-3 text-xl font-semibold text-[#0e1a2e]">{card.title}</h3>
            <p className="mt-2 text-sm text-subtext">{card.copy}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
