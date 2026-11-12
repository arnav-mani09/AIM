"use client";

// Half-court shot chart for the review screen, from the spots AIM read off the film (one per field
// goal). Makes are filled dots, misses are crosses, so the two never depend on color alone.
// Clicking a mark plays the film from that shot.

import { useMemo, useState } from "react";

import type { ShotEvent, TeamSide } from "@/lib/reviewApi";
import type { ShotZone } from "@/lib/teamApi";
import { ZONE_TITLES } from "@/components/ShotChart";

// 10 SVG units per foot. The court is 50 ft wide; the rim sits 5.25 ft out from the baseline. Only
// the first 38 ft from the baseline are drawn: shots from farther out are rare and sit on the edge.
const PX = 10;
const W = 50 * PX;
const H = 38 * PX;
const RIM = { x: W / 2, y: 5.25 * PX };
const ARC_FT = 19.75; // high school 3-point line
const MAX_Y_FT = 32; // keep stray spots on the drawn court

const ZONE_ORDER: ShotZone[] = [
  "restricted_area",
  "paint",
  "mid_range_left",
  "mid_range_right",
  "corner_three_left",
  "corner_three_right",
  "wing_three_left",
  "wing_three_right",
  "top_of_key_three",
];

const sx = (x: number) => RIM.x + Math.max(-24.5, Math.min(24.5, x)) * PX;
const sy = (y: number) => RIM.y + Math.max(-5, Math.min(MAX_Y_FT, y)) * PX;

// Same rules as ml/tools/three_point.zone_of. Worked out here from the coach's current call, so a
// shot fixed from a 2 to a 3 counts in a 3-point zone.
function zoneOf(x: number, y: number, three: boolean): ShotZone {
  const side = x < 0 ? "left" : "right";
  if (three) {
    if (y <= 8) return `corner_three_${side}`;
    if (Math.abs((Math.atan2(x, y) * 180) / Math.PI) <= 22.5) return "top_of_key_three";
    return `wing_three_${side}`;
  }
  if (Math.hypot(x, y) <= 4) return "restricted_area";
  if (Math.abs(x) <= 6 && y <= 13.75) return "paint";
  return `mid_range_${side}`;
}

type Placed = ShotEvent & { x: number; y: number };

function formatClock(t: number) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function Court() {
  const arcEndY = RIM.y; // the arc meets straight corner lines level with the rim
  const r = ARC_FT * PX;
  return (
    <g fill="none" stroke="#c3cede" strokeWidth={2}>
      <path d={`M 1 ${H} L 1 1 L ${W - 1} 1 L ${W - 1} ${H}`} />
      {/* Lane, free throw circle, restricted area */}
      <rect x={RIM.x - 6 * PX} y={1} width={12 * PX} height={19 * PX - 1} />
      <circle cx={RIM.x} cy={19 * PX} r={6 * PX} />
      <path d={`M ${RIM.x - 4 * PX} ${RIM.y} A ${4 * PX} ${4 * PX} 0 0 0 ${RIM.x + 4 * PX} ${RIM.y}`} />
      {/* 3-point line */}
      <path
        d={`M ${RIM.x - r} 1 L ${RIM.x - r} ${arcEndY} A ${r} ${r} 0 0 0 ${RIM.x + r} ${arcEndY} L ${RIM.x + r} 1`}
      />
      {/* Backboard and rim */}
      <line x1={RIM.x - 3 * PX} y1={4 * PX} x2={RIM.x + 3 * PX} y2={4 * PX} stroke="#8a97ab" strokeWidth={3} />
      <circle cx={RIM.x} cy={RIM.y} r={0.75 * PX} stroke="#8a97ab" />
    </g>
  );
}

export function FilmShotChart({
  events,
  onPick,
  title = "Shot chart",
}: {
  events: ShotEvent[];
  onPick: (event: ShotEvent) => void;
  title?: string;
}) {
  const [team, setTeam] = useState<TeamSide>("valley");
  const [hoverId, setHoverId] = useState<number | null>(null);

  const { placed, unplaced, zones, makes } = useMemo(() => {
    const fg = events.filter((e) => e.team === team && e.status !== "deleted" && e.shot_type !== "ft");
    const placed = fg.filter((e): e is Placed => typeof e.x === "number" && typeof e.y === "number");
    const counts = new Map<ShotZone, { makes: number; attempts: number }>();
    for (const e of placed) {
      const zone = zoneOf(e.x, e.y, e.shot_type === "fg3");
      const c = counts.get(zone) ?? { makes: 0, attempts: 0 };
      c.attempts += 1;
      if (e.made) c.makes += 1;
      counts.set(zone, c);
    }
    return {
      placed,
      unplaced: fg.length - placed.length,
      zones: ZONE_ORDER.map((zone) => ({ zone, ...(counts.get(zone) ?? { makes: 0, attempts: 0 }) })),
      makes: placed.filter((e) => e.made).length,
    };
  }, [events, team]);

  const hovered = placed.find((e) => e.id === hoverId) ?? null;

  return (
    <section className="section-card flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
          <p className="text-sm text-subtext">
            {placed.length > 0
              ? `${makes}/${placed.length} field goals · ${Math.round((makes / placed.length) * 100)}%`
              : "No shot spots for this team yet"}
          </p>
        </div>
        <div className="flex gap-2 text-sm">
          {(
            [
              ["valley", "Valley"],
              ["opponent", "Opponent"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTeam(value)}
              className={`rounded-full px-4 py-2 font-semibold ${
                team === value ? "bg-accent text-white" : "border border-stroke text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="relative">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full rounded-xl border border-stroke bg-white"
            role="img"
            aria-label={`${team === "valley" ? "Valley" : "Opponent"} shot chart: ${makes} makes of ${placed.length} field goals`}
          >
            <Court />
            {placed.map((e) => {
              const cx = sx(e.x);
              const cy = sy(e.y);
              const active = e.id === hoverId;
              return (
                <g
                  key={e.id}
                  className="cursor-pointer"
                  onClick={() => onPick(e)}
                  onMouseEnter={() => setHoverId(e.id)}
                  onMouseLeave={() => setHoverId((id) => (id === e.id ? null : id))}
                >
                  {e.made ? (
                    <circle cx={cx} cy={cy} r={active ? 9 : 7} fill="#1a4d84" stroke="#ffffff" strokeWidth={2} />
                  ) : (
                    <path
                      d={`M ${cx - 6} ${cy - 6} L ${cx + 6} ${cy + 6} M ${cx + 6} ${cy - 6} L ${cx - 6} ${cy + 6}`}
                      stroke={active ? "#0e1a2e" : "#54627a"}
                      strokeWidth={active ? 3 : 2}
                      strokeLinecap="round"
                    />
                  )}
                  {/* Bigger than the mark, so it's easy to hit */}
                  <circle cx={cx} cy={cy} r={14} fill="transparent" />
                </g>
              );
            })}
          </svg>
          {hovered && (
            <div
              className="pointer-events-none absolute rounded-lg border border-stroke bg-white px-3 py-2 text-xs text-ink shadow-soft"
              style={{
                left: `${(sx(hovered.x) / W) * 100}%`,
                top: `${(sy(hovered.y) / H) * 100}%`,
                transform: "translate(-50%, calc(-100% - 14px))",
              }}
            >
              <p className="font-semibold">
                {hovered.made ? "Make" : "Miss"} · {hovered.shot_type === "fg3" ? "3" : "2"}
                {hovered.player_number !== null ? ` · #${hovered.player_number}` : ""}
              </p>
              <p className="text-subtext">
                {formatClock(hovered.t)} in the film · {Math.round(Math.hypot(hovered.x, hovered.y))} ft
              </p>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-subtext">
            <span className="flex items-center gap-1.5">
              <svg width="14" height="14" aria-hidden>
                <circle cx="7" cy="7" r="5" fill="#1a4d84" />
              </svg>
              Make
            </span>
            <span className="flex items-center gap-1.5">
              <svg width="14" height="14" aria-hidden>
                <path d="M 3 3 L 11 11 M 11 3 L 3 11" stroke="#54627a" strokeWidth="2" strokeLinecap="round" />
              </svg>
              Miss
            </span>
            <span>Click a shot to watch it. Spots are rough, read from the film.</span>
          </div>
        </div>

        <div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-subtext">
                <th className="pb-2 font-semibold">Zone</th>
                <th className="pb-2 text-right font-semibold">Made</th>
                <th className="pb-2 text-right font-semibold">FG%</th>
              </tr>
            </thead>
            <tbody>
              {zones.map((z) => (
                <tr key={z.zone} className="border-t border-stroke">
                  <td className="py-1.5 text-ink">{ZONE_TITLES[z.zone]}</td>
                  <td className="py-1.5 text-right text-ink">{z.attempts ? `${z.makes}/${z.attempts}` : "-"}</td>
                  <td className="py-1.5 text-right font-semibold text-ink">
                    {z.attempts ? `${Math.round((z.makes / z.attempts) * 100)}%` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {unplaced > 0 && (
            <p className="mt-3 text-xs text-subtext">
              {unplaced} field goal{unplaced === 1 ? "" : "s"} without a spot (added by hand, or AIM didn&apos;t find
              the shooter), so not on the chart.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
