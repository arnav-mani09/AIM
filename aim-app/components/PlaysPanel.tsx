"use client";

// Team rebounds and turnovers on the review screen: a simple list in game order. The coach can
// jump to each one in the film, switch its team, delete it (or bring it back), and add one AIM
// missed at the film's current time. Steals and assists aren't shown: AIM can't read them well yet.

import { useState } from "react";

import type { PlayEvent, PlayType, TeamSide } from "@/lib/reviewApi";

const PLAY_LABEL: Record<PlayType, string> = { oreb: "Off. rebound", dreb: "Def. rebound", to: "Turnover" };
const TEAM_LABEL: Record<TeamSide, string> = { valley: "Valley", opponent: "Opponent" };
const UNSURE_BELOW = 0.7;

function clock(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export function PlaysPanel({
  plays,
  hasPlays,
  busy = false,
  onWatch,
  onSwitchTeam,
  onDelete,
  onRestore,
  onAdd,
  onFind,
}: {
  plays: PlayEvent[];
  hasPlays: boolean;
  busy?: boolean;
  onWatch: (t: number) => void;
  onSwitchTeam: (play: PlayEvent) => void;
  onDelete: (play: PlayEvent) => void;
  onRestore: (play: PlayEvent) => void;
  /** Add a play at the film's current time. */
  onAdd: (type: PlayType, team: TeamSide) => void;
  /** Draft rebounds and turnovers for a film from before AIM found them. */
  onFind: () => void;
}) {
  const [kind, setKind] = useState<"all" | "reb" | "to">("all");
  const [team, setTeam] = useState<TeamSide>("valley");
  const shown = [...plays]
    .filter((p) => kind === "all" || (kind === "to" ? p.type === "to" : p.type !== "to"))
    .sort((a, b) => a.t - b.t);

  return (
    <fieldset disabled={busy} className="section-card flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">Rebounds and turnovers</h2>
          <p className="text-sm text-subtext">
            Team totals AIM drafted from who had the ball. Rough, so check the ones that look off. Switching a
            rebound&apos;s team also switches offensive and defensive.
          </p>
        </div>
        {hasPlays && (
          <div className="flex gap-2 text-sm">
            {(
              [
                ["all", "All"],
                ["reb", "Rebounds"],
                ["to", "Turnovers"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setKind(value)}
                className={`rounded-full px-4 py-2 font-semibold ${
                  kind === value ? "bg-accent text-white" : "border border-stroke text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {!hasPlays ? (
        <div className="rounded-2xl border border-dashed border-stroke p-4 text-sm">
          <p className="text-ink">
            Rebounds and turnovers aren&apos;t available for this film, not zero. Shooting stats are still
            available. Optionally rerun processing to try finding these events; shots you already checked stay as they are.
          </p>
          <button onClick={onFind} className="mt-3 rounded-2xl bg-accent px-4 py-2 font-semibold text-white">
            Find rebounds and turnovers
          </button>
        </div>
      ) : shown.length === 0 ? (
        <p className="text-sm text-subtext">None in this list.</p>
      ) : (
        <ul className="flex max-h-[24rem] flex-col gap-2 overflow-y-auto pr-1">
          {shown.map((p) => {
            const deleted = p.status === "deleted";
            return (
              <li
                key={p.id}
                className={`flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-stroke p-3 ${
                  deleted ? "opacity-50" : ""
                }`}
              >
                <button onClick={() => onWatch(p.t)} className="flex items-center gap-3 text-left" title="Watch in the film">
                  <span className="w-14 font-mono text-sm text-subtext">{clock(p.t)}</span>
                  <span className={`font-semibold text-ink ${deleted ? "line-through" : ""}`}>
                    {TEAM_LABEL[p.team]} {PLAY_LABEL[p.type].toLowerCase()}
                  </span>
                  {p.status === "draft" && p.confidence < UNSURE_BELOW && (
                    <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-semibold text-yellow-800">
                      Unsure
                    </span>
                  )}
                  {p.status === "fixed" && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">Fixed</span>
                  )}
                </button>
                <span className="flex gap-2 text-sm">
                  <button
                    onClick={() => onWatch(p.t)}
                    className="rounded-full border border-stroke px-3 py-1 font-semibold text-ink"
                  >
                    Watch
                  </button>
                  {!deleted && (
                    <button
                      onClick={() => onSwitchTeam(p)}
                      className="rounded-full border border-stroke px-3 py-1 font-semibold text-ink"
                    >
                      Switch team
                    </button>
                  )}
                  {deleted ? (
                    <button
                      onClick={() => onRestore(p)}
                      className="rounded-full border border-stroke px-3 py-1 font-semibold text-ink"
                    >
                      Bring back
                    </button>
                  ) : (
                    <button
                      onClick={() => onDelete(p)}
                      className="rounded-full border border-red-300 px-3 py-1 font-semibold text-red-600"
                    >
                      Delete
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {hasPlays && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-accentMuted p-3 text-sm">
          <span className="font-semibold text-ink">Add at the film&apos;s current time:</span>
          <select
            value={team}
            onChange={(e) => setTeam(e.target.value as TeamSide)}
            className="rounded-full border border-stroke bg-white px-3 py-1 text-ink"
            aria-label="Team"
          >
            <option value="valley">Valley</option>
            <option value="opponent">Opponent</option>
          </select>
          {(["oreb", "dreb", "to"] as const).map((type) => (
            <button
              key={type}
              onClick={() => onAdd(type, team)}
              className="rounded-full border-2 border-dashed border-accent px-3 py-1 font-semibold text-accent"
            >
              + {PLAY_LABEL[type]}
            </button>
          ))}
        </div>
      )}
    </fieldset>
  );
}
