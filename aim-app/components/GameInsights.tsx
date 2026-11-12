"use client";

// Compact "Game insights" panel for one film on the review screen: each team's shooting stats,
// scouting notes and zones. Refetches a moment after the coach changes a shot, so fixes show up.

import { useEffect, useState } from "react";

import { ComingSoon, ScoutingLines, SmallSampleNote, StatTiles, ZoneTable } from "@/components/InsightsPanel";
import { fetchInsights, Insights } from "@/lib/insightsApi";
import type { TeamSide } from "@/lib/reviewApi";

const TEAMS: Array<[TeamSide, string]> = [
  ["valley", "Valley"],
  ["opponent", "Opponent"],
];

export function GameInsights({
  token,
  teamId,
  uploadId,
  version,
}: {
  /** Null skips loading (sample data mode). */
  token: string | null;
  teamId: number;
  uploadId: number;
  /** Changes whenever the shots change, to refresh the numbers. */
  version: string;
}) {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [team, setTeam] = useState<TeamSide>("opponent");

  useEffect(() => {
    if (!token) return;
    let live = true;
    const timer = window.setTimeout(() => {
      fetchInsights(token, teamId, [uploadId])
        .then((result) => {
          if (!live) return;
          setData(result);
          setError(null);
        })
        .catch((err) => live && setError(err instanceof Error ? err.message : "Couldn't load the insights."));
    }, 600);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [token, teamId, uploadId, version]);

  if (!token) return null;

  const current = data?.teams[team];
  return (
    <section className="section-card flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">Game insights</h2>
          <p className="text-sm text-subtext">How each team shot in this game, from the shots below.</p>
        </div>
        <div className="flex gap-2 text-sm">
          {TEAMS.map(([value, label]) => (
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
      {error && <p className="text-sm text-red-500">{error}</p>}
      {!current ? (
        !error && <p className="text-sm text-subtext">Loading insights…</p>
      ) : !current.fga && !current.fta ? (
        <p className="text-sm text-subtext">No shots counted for this team yet.</p>
      ) : (
        <>
          <SmallSampleNote team={current} />
          <ScoutingLines team={current} />
          <StatTiles team={current} compact />
          <details>
            <summary className="cursor-pointer text-sm font-semibold text-accent">Shots by zone</summary>
            <div className="mt-3 overflow-x-auto">
              <ZoneTable zones={current.zones} />
            </div>
          </details>
          <ComingSoon stats={data?.coming_soon ?? []} />
        </>
      )}
    </section>
  );
}
