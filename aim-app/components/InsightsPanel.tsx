"use client";

// Pieces for team shooting insights: stat tiles (with short explanations of eFG% and TS%), a zone
// chart, a zone table and the plain-language scouting lines. Numbers come from the insights API,
// which uses the same formulas and zones as ml/tools/insights.py.

import { useId } from "react";

import type { InsightZone, TeamInsights, ZoneRow } from "@/lib/insightsApi";

const fmtPct = (x: number | null | undefined) => (x == null ? "-" : `${Math.round(x)}%`);

export const COMING_SOON_NOTE = "AIM can't read these well enough from film yet, so not shown.";

export function InfoTip({ label, text }: { label: string; text: string }) {
  const id = useId();
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={`What is ${label}?`}
        aria-describedby={id}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-stroke text-[0.65rem] font-bold text-subtext hover:border-accent hover:text-accent focus:border-accent focus:text-accent focus:outline-none"
      >
        ?
      </button>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-56 -translate-x-1/2 rounded-lg border border-stroke bg-white px-3 py-2 text-xs font-normal normal-case tracking-normal text-ink opacity-0 shadow-soft transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

const TIPS = {
  efg: "Effective FG%: like FG%, but a made 3 counts as one and a half makes, because it's worth 1.5 times a 2. It shows how well a team shoots once 3s get their extra credit.",
  ts: "True shooting %: points per shot, with free throws counted in. It's on the same scale as FG%, so a higher number means more points from the same number of shots.",
  ftRate: "How many free throws a team shoots for every 10 field goal tries. Higher means they get fouled a lot.",
  tov: "Turnover rate: turnovers out of every 100 possessions. Lower is better. Fair: AIM drafts turnovers from who has the ball, so treat it as close, not exact.",
  oreb: "Offensive rebound rate: the share of the team's own misses it got back. Fair: drafted from film, close but not exact.",
  dreb: "Defensive rebound rate: the share of the other team's misses this team grabbed. Fair: drafted from film, close but not exact.",
};

type Tile = { label: string; value: string; detail?: string; tip?: string; fair?: boolean };

export function StatTiles({ team, compact = false }: { team: TeamInsights; compact?: boolean }) {
  const tiles: Tile[] = [
    {
      label: team.games > 1 ? "Points a game" : "Points",
      value: team.games > 1 ? `${team.pts_per_game ?? "-"}` : `${team.pts}`,
      detail: team.games > 1 ? `${team.pts} in ${team.games} games` : undefined,
    },
    { label: "FG%", value: fmtPct(team.fg_pct), detail: `${team.fgm} of ${team.fga}` },
    { label: "3PT%", value: fmtPct(team.fg3_pct), detail: `${team.fg3m} of ${team.fg3a}` },
    { label: "FT%", value: fmtPct(team.ft_pct), detail: `${team.ftm} of ${team.fta}` },
    { label: "Effective FG%", value: fmtPct(team.efg_pct), tip: TIPS.efg },
    { label: "True shooting %", value: fmtPct(team.ts_pct), tip: TIPS.ts },
    { label: "Shots from 3", value: team.fg3a_rate === null ? "-" : `${Math.round(team.fg3a_rate * 100)}%` },
    {
      label: "Free throws per 10 shots",
      value: team.ft_rate === null ? "-" : `${(team.ft_rate * 10).toFixed(1)}`,
      tip: TIPS.ftRate,
    },
  ];
  if (team.play_games) {
    const games = team.play_games < team.games ? ` (${team.play_games} of ${team.games} games)` : "";
    tiles.push(
      { label: "Turnover rate", value: fmtPct(team.tov_pct), detail: `${team.to ?? "-"} turnovers${games}`, tip: TIPS.tov, fair: true },
      { label: "Off. rebound rate", value: fmtPct(team.oreb_pct), detail: `${team.oreb ?? "-"} off. rebounds${games}`, tip: TIPS.oreb, fair: true },
      { label: "Def. rebound rate", value: fmtPct(team.dreb_pct), detail: `${team.dreb ?? "-"} def. rebounds${games}`, tip: TIPS.dreb, fair: true },
      { label: "Rebounds", value: `${team.reb ?? "-"}`, detail: games ? games.trim() : undefined, fair: true },
    );
  }
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className={`rounded-xl border border-stroke ${compact ? "px-3 py-2" : "px-4 py-3"}`}>
          <dt className="text-xs text-subtext">
            {t.label}
            {t.tip && <InfoTip label={t.label} text={t.tip} />}
            {t.fair && (
              <span className="ml-1 rounded-full bg-yellow-50 px-1.5 text-[0.65rem] font-semibold text-yellow-800">fair</span>
            )}
          </dt>
          <dd className={`${compact ? "text-lg" : "text-2xl"} font-semibold text-ink`}>{t.value}</dd>
          {t.detail && <dd className="text-xs text-subtext">{t.detail}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function ScoutingLines({ team }: { team: TeamInsights }) {
  return (
    <ul className="space-y-2 text-sm text-ink">
      {team.lines.map((line) => (
        <li key={line} className="flex gap-2">
          <span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-accent" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

export function ZoneTable({ zones }: { zones: ZoneRow[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-subtext">
          <th className="pb-2 font-semibold">Zone</th>
          <th className="pb-2 text-right font-semibold">Made</th>
          <th className="pb-2 text-right font-semibold">FG%</th>
          <th className="pb-2 text-right font-semibold">Share of shots</th>
          <th className="pb-2 text-right font-semibold">Points</th>
        </tr>
      </thead>
      <tbody>
        {zones.map((z) => (
          <tr key={z.zone} className="border-t border-stroke text-ink">
            <td className="py-1.5">
              {z.label}
              {z.small_sample && <span className="ml-1 text-xs text-subtext">(few shots)</span>}
            </td>
            <td className="py-1.5 text-right">{z.attempts ? `${z.makes}/${z.attempts}` : "-"}</td>
            <td className="py-1.5 text-right font-semibold">{z.attempts ? fmtPct(z.fg_pct) : "-"}</td>
            <td className="py-1.5 text-right">{z.attempts ? fmtPct(z.share) : "-"}</td>
            <td className="py-1.5 text-right">{z.points}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Zone chart: the half court split into the five zones, shaded by share of shots (darker = more),
// each labeled with makes/tries. 10 SVG units per foot, rim at (0, 0) in court feet, the same
// layout as FilmShotChart.
const PX = 10;
const W = 50 * PX;
const H = 34 * PX;
const RIM = { x: W / 2, y: 5.25 * PX };
const ARC = 19.75 * PX;
const CORNER_Y = RIM.y + 8 * PX; // a 3 this close to the baseline is a corner 3
const ACCENT = "26, 77, 132";

export function ZoneChart({ team, name }: { team: TeamInsights; name: string }) {
  const byZone = new Map(team.zones.map((z) => [z.zone, z]));
  const maxShare = Math.max(1, ...team.zones.filter((z) => z.zone !== "unknown").map((z) => z.share ?? 0));
  const fill = (zone: InsightZone) => {
    const share = byZone.get(zone)?.share ?? 0;
    return `rgba(${ACCENT}, ${(0.05 + 0.4 * (share / maxShare)).toFixed(2)})`;
  };
  const title = (zone: InsightZone) => {
    const z = byZone.get(zone);
    if (!z || !z.attempts) return `${ZONE_LABEL[zone]}: no shots`;
    return `${z.label}: ${z.makes} of ${z.attempts} made (${fmtPct(z.fg_pct)}), ${fmtPct(z.share)} of shots, ${z.points} points`;
  };
  const label = (zone: InsightZone, x: number, y: number) => {
    const z = byZone.get(zone);
    return (
      <text
        x={x}
        y={y}
        textAnchor="middle"
        className="pointer-events-none"
        fontSize={14}
        fontWeight={600}
        fill="#0e1a2e"
        stroke="#ffffff"
        strokeWidth={3}
        paintOrder="stroke"
      >
        <tspan x={x}>{z && z.attempts ? `${z.makes}/${z.attempts}` : "-"}</tspan>
        {z && z.attempts > 0 && (
          <tspan x={x} dy={15} fontSize={12} fontWeight={400}>
            {fmtPct(z.fg_pct)}
          </tspan>
        )}
      </text>
    );
  };
  const twoPointArea = `M ${RIM.x - ARC} 0 L ${RIM.x - ARC} ${RIM.y} A ${ARC} ${ARC} 0 0 0 ${RIM.x + ARC} ${RIM.y} L ${RIM.x + ARC} 0 Z`;
  const region = "stroke-white [stroke-width:2] transition-opacity hover:opacity-80";

  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full rounded-xl border border-stroke bg-white"
        role="img"
        aria-label={`${name} shots by zone, darker means more of their shots`}
      >
        {/* The svg's own edges clip the circles that run past the baseline. */}
        <g>
          <rect x={0} y={0} width={W} height={H} fill={fill("above_break3")} className={region}>
            <title>{title("above_break3")}</title>
          </rect>
          <g fill={fill("corner3")} className={region}>
            <title>{title("corner3")}</title>
            <rect x={0} y={0} width={RIM.x - ARC} height={CORNER_Y} />
            <rect x={RIM.x + ARC} y={0} width={W - RIM.x - ARC} height={CORNER_Y} />
          </g>
          <path d={twoPointArea} fill="#ffffff" />
          <path d={twoPointArea} fill={fill("midrange")} className={region}>
            <title>{title("midrange")}</title>
          </path>
          <circle cx={RIM.x} cy={RIM.y} r={13.75 * PX} fill="#ffffff" />
          <circle cx={RIM.x} cy={RIM.y} r={13.75 * PX} fill={fill("paint")} className={region}>
            <title>{title("paint")}</title>
          </circle>
          <circle cx={RIM.x} cy={RIM.y} r={4.5 * PX} fill="#ffffff" />
          <circle cx={RIM.x} cy={RIM.y} r={4.5 * PX} fill={fill("rim")} className={region}>
            <title>{title("rim")}</title>
          </circle>
        </g>
        <line x1={RIM.x - 3 * PX} y1={4 * PX} x2={RIM.x + 3 * PX} y2={4 * PX} stroke="#8a97ab" strokeWidth={3} />
        {label("rim", RIM.x, RIM.y + 2)}
        {label("paint", RIM.x, RIM.y + 9 * PX)}
        {label("midrange", RIM.x, RIM.y + 16.5 * PX)}
        {label("above_break3", RIM.x, RIM.y + 24.5 * PX)}
        {label("corner3", (RIM.x - ARC) / 2, CORNER_Y / 2)}
      </svg>
      <figcaption className="mt-2 text-xs text-subtext">
        Darker zones get more of {name === "Valley" ? "our" : "their"} shots. Corner 3s count both corners (number
        shown on the left). Hover a zone for details. Spots are rough, read from the film; inside the arc only the
        distance from the rim counts.
      </figcaption>
    </figure>
  );
}

const ZONE_LABEL: Record<InsightZone, string> = {
  rim: "At the rim",
  paint: "Paint",
  midrange: "Midrange",
  corner3: "Corner 3",
  above_break3: "Above-the-break 3",
  unknown: "No spot",
};

export function SmallSampleNote({ team }: { team: TeamInsights }) {
  if (!team.small_sample) return null;
  return (
    <p className="rounded-xl bg-yellow-50 px-3 py-2 text-xs text-yellow-800">
      Small sample: only {team.fga} shots. Treat these numbers as hints, not habits.
    </p>
  );
}

export function ComingSoon({ stats }: { stats: string[] }) {
  if (!stats.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-subtext" title={COMING_SOON_NOTE}>
      <span>Coming soon:</span>
      {stats.map((stat) => (
        <span key={stat} className="rounded-full border border-dashed border-stroke px-3 py-1">
          {stat}
        </span>
      ))}
    </div>
  );
}

/** Full team card: tiles, zone chart and table, scouting lines. */
export function TeamInsightsCard({
  team,
  name,
  comingSoon,
}: {
  team: TeamInsights;
  name: string;
  comingSoon: string[];
}) {
  if (!team.fga && !team.fta && !team.play_games) {
    return <p className="text-sm text-subtext">No shots counted for {name} in these games.</p>;
  }
  return (
    <div className="flex flex-col gap-5">
      <SmallSampleNote team={team} />
      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">Scouting notes</h3>
        <ScoutingLines team={team} />
      </div>
      <StatTiles team={team} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <ZoneChart team={team} name={name} />
        <ZoneTable zones={team.zones} />
      </div>
      <ComingSoon stats={comingSoon} />
    </div>
  );
}
