import type { ExampleCard } from "@/lib/mockData";

interface ExampleSectionProps {
  cards: ExampleCard[];
}

export function ExampleSection({ cards }: ExampleSectionProps) {
  return (
    <section id="example" className="section-card">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="label-text">Example: Valley vs Central</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#0e1a2e]">Sample dashboard</h2>
        </div>
        <span className="pill">sample data</span>
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
