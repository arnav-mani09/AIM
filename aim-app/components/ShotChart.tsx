import type { ShotChartRecord, ShotZone, ZoneStat } from "@/lib/teamApi";
import { CourtDiagram } from "@/components/CourtDiagram";

// Validated sequential ramp (single hue, monotone lightness, light end clears
// 2:1 contrast on the white card surface) — see dataviz skill validation.
// node scripts/validate_palette.js "<ramp>" --mode light --ordinal --surface "#ffffff" -> ALL CHECKS PASS
const FG_PCT_RAMP = ["#96b9e0", "#78a3d6", "#5991c8", "#3b76b2", "#1a4d84"];
const ZERO_ATTEMPTS_FILL = "#f5f7fb";

function rampColorForPct(pct: number): string {
  const index = Math.min(FG_PCT_RAMP.length - 1, Math.floor(pct / (100 / FG_PCT_RAMP.length)));
  return FG_PCT_RAMP[index];
}

const ZONE_TITLES: Record<ShotZone, string> = {
  restricted_area: "Restricted area",
  paint: "Paint",
  mid_range_left: "Mid-range (L)",
  mid_range_right: "Mid-range (R)",
  corner_three_left: "Corner 3 (L)",
  corner_three_right: "Corner 3 (R)",
  wing_three_left: "Wing 3 (L)",
  wing_three_right: "Wing 3 (R)",
  top_of_key_three: "Top of key 3",
};

type ShotChartProps = {
  data: ShotChartRecord;
};

export function ShotChart({ data }: ShotChartProps) {
  const byZone = new Map<ShotZone, ZoneStat>(data.zones.map((z) => [z.zone, z]));

  const zoneFill = (zone: ShotZone) => {
    const stat = byZone.get(zone);
    if (!stat || stat.attempts === 0) return ZERO_ATTEMPTS_FILL;
    return rampColorForPct(stat.fg_pct ?? 0);
  };

  const zoneLabel = (zone: ShotZone) => {
    const stat = byZone.get(zone);
    if (!stat || stat.attempts === 0) return "No shots";
    return `${stat.makes}/${stat.attempts} · ${stat.fg_pct}%`;
  };

  return (
    <div className="rounded-2xl border border-stroke bg-white p-5 shadow-soft">
      <div className="flex items-center justify-between">
        <p className="label-text">Team shot chart</p>
        <p className="text-sm font-semibold text-ink">
          {data.total_makes}/{data.total_attempts}
          {data.overall_fg_pct !== null && <span className="text-subtext"> · {data.overall_fg_pct}% FG</span>}
        </p>
      </div>

      <div className="mt-4">
        <CourtDiagram mode="display" zoneFill={zoneFill} zoneLabel={zoneLabel} />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <span className="text-xs text-subtext">FG%</span>
        <div
          className="h-2 flex-1 rounded-full"
          style={{ background: `linear-gradient(to right, ${FG_PCT_RAMP.join(",")})` }}
          aria-hidden
        />
        <span className="text-xs text-subtext">0 · 50 · 100</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-subtext">
        <span
          className="inline-block h-3 w-3 rounded border border-dashed border-stroke"
          style={{ background: ZERO_ATTEMPTS_FILL }}
          aria-hidden
        />
        No shots logged in that zone yet
      </div>

      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-subtext sm:grid-cols-3">
        {data.zones.map((zone) => (
          <li key={zone.zone} className="flex items-center justify-between gap-2">
            <span>{ZONE_TITLES[zone.zone]}</span>
            <span className="font-semibold text-ink">
              {zone.attempts > 0 ? `${zone.makes}/${zone.attempts}` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
