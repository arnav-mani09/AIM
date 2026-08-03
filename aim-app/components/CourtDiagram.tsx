import type { ShotZone } from "@/lib/teamApi";

type ZoneShape =
  | { kind: "rect"; x: number; y: number; w: number; h: number }
  | { kind: "circle"; cx: number; cy: number; r: number };

type ZoneDef = {
  id: ShotZone;
  shape: ZoneShape;
  labelPoint: { x: number; y: number };
};

const BASKET = { x: 250, y: 40 };

// Non-overlapping tiling of the half-court (viewBox 0 0 500 470, basket at top).
// A cosmetic approximation, not a precise geometric match to shot_zones.py —
// the interaction is tap-a-zone, so this only needs to read clearly as "roughly
// where that zone is," not align pixel-for-pixel with the classifier.
const ZONES: ZoneDef[] = [
  { id: "corner_three_left", shape: { kind: "rect", x: 0, y: 0, w: 90, h: 140 }, labelPoint: { x: 45, y: 70 } },
  { id: "corner_three_right", shape: { kind: "rect", x: 410, y: 0, w: 90, h: 140 }, labelPoint: { x: 455, y: 70 } },
  { id: "wing_three_left", shape: { kind: "rect", x: 0, y: 140, w: 90, h: 330 }, labelPoint: { x: 45, y: 230 } },
  { id: "wing_three_right", shape: { kind: "rect", x: 410, y: 140, w: 90, h: 330 }, labelPoint: { x: 455, y: 230 } },
  { id: "mid_range_left", shape: { kind: "rect", x: 90, y: 0, w: 80, h: 190 }, labelPoint: { x: 130, y: 110 } },
  { id: "mid_range_right", shape: { kind: "rect", x: 330, y: 0, w: 80, h: 190 }, labelPoint: { x: 370, y: 110 } },
  { id: "top_of_key_three", shape: { kind: "rect", x: 90, y: 190, w: 320, h: 280 }, labelPoint: { x: 250, y: 340 } },
  { id: "paint", shape: { kind: "rect", x: 170, y: 0, w: 160, h: 190 }, labelPoint: { x: 250, y: 150 } },
  { id: "restricted_area", shape: { kind: "circle", cx: BASKET.x, cy: BASKET.y, r: 32 }, labelPoint: { x: 250, y: 100 } },
];

function shapeProps(shape: ZoneShape) {
  if (shape.kind === "circle") {
    return { cx: shape.cx, cy: shape.cy, r: shape.r };
  }
  return { x: shape.x, y: shape.y, width: shape.w, height: shape.h };
}

type CourtDiagramProps = {
  mode: "select" | "display";
  selectedZone?: ShotZone | null;
  onSelectZone?: (zone: ShotZone) => void;
  zoneFill?: (zone: ShotZone) => string;
  zoneLabel?: (zone: ShotZone) => string | undefined;
};

export function CourtDiagram({ mode, selectedZone, onSelectZone, zoneFill, zoneLabel }: CourtDiagramProps) {
  return (
    <svg
      viewBox="0 0 500 470"
      className="w-full rounded-2xl border border-stroke bg-white"
      role="img"
      aria-label="Half-court shot zone diagram"
    >
      {ZONES.map((zone) => {
        const isSelected = mode === "select" && selectedZone === zone.id;
        const fill = mode === "display" ? zoneFill?.(zone.id) ?? "#f5f7fb" : isSelected ? "#eaf1fb" : "#ffffff";
        const Shape = zone.shape.kind === "circle" ? "circle" : "rect";
        return (
          <g key={zone.id}>
            <Shape
              {...(shapeProps(zone.shape) as any)}
              fill={fill}
              stroke={isSelected ? "#1a4d84" : "#dfe6f1"}
              strokeWidth={isSelected ? 3 : 1}
              className={mode === "select" ? "cursor-pointer transition-colors hover:fill-tint" : undefined}
              onClick={mode === "select" ? () => onSelectZone?.(zone.id) : undefined}
            />
            {mode === "display" && zoneLabel && (
              <text
                x={zone.labelPoint.x}
                y={zone.labelPoint.y}
                textAnchor="middle"
                className="pointer-events-none select-none fill-[#0e1a2e] text-[13px] font-semibold"
              >
                {zoneLabel(zone.id) ?? ""}
              </text>
            )}
          </g>
        );
      })}

      {/* Decorative court markings, non-interactive */}
      <g className="pointer-events-none" stroke="#b9c6dc" strokeWidth={2} fill="none">
        <rect x={0} y={0} width={500} height={470} />
        <rect x={170} y={0} width={160} height={190} />
        <circle cx={BASKET.x} cy={190} r={60} />
        <path d="M 30 0 L 30 140 A 220 220 0 0 0 470 140 L 470 0" />
        <circle cx={BASKET.x} cy={BASKET.y} r={7.5} fill="#b9c6dc" />
      </g>
    </svg>
  );
}
