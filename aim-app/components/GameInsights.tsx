"use client";

// Compact "Game insights" panel for one film on the review screen: each team's shooting stats,
// rebound and turnover rates, scouting notes and zones. Refetches a moment after the coach changes a shot, so fixes show up.

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
  const [loaded, setLoaded] = useState<{ resource: string; version: string; data: Insights } | null>(null);
  const [failure, setFailure] = useState<{ resource: string; version: string; message: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const [team, setTeam] = useState<TeamSide>("opponent");
  const resource = JSON.stringify([token, teamId, uploadId]);
  const data = loaded?.resource === resource ? loaded.data : null;
  const error = failure?.resource === resource && failure.version === version ? failure.message : null;
  const refreshing = !error && (!data || loaded?.version !== version);

  useEffect(() => {
    if (!token) return;
    let live = true;
    const timer = window.setTimeout(() => {
      fetchInsights(token, teamId, [uploadId])
        .then((result) => {
          if (!live) return;
          if (result.skipped) throw new Error("Insights are waiting for processing to finish.");
          setLoaded({ resource, version, data: result });
          setFailure(null);
        })
        .catch((err) => live && setFailure({ resource, version, message: err instanceof Error ? err.message : "Couldn't load the insights." }));
    }, 600);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [token, teamId, uploadId, version, resource, retry]);

  if (!token) return null;

  const current = data?.teams[team];
  return (
    <section className="section-card flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">Game insights</h2>
          <p className="text-sm text-subtext">
            Estimates from saved events, including automatic drafts. No coach confirmation is required;
            model confidence does not verify accuracy.
          </p>
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
      {error && (
        <div className="text-sm text-red-500">
          <p>{error} {current ? "Last loaded insights remain shown and may be out of date." : ""}</p>
          <button onClick={() => setRetry((value) => value + 1)} className="mt-2 font-semibold underline">Retry insights</button>
        </div>
      )}
      {current && refreshing && <p role="status" className="text-sm text-subtext">Updating insights… Last loaded values remain shown.</p>}
      {!current ? (
        !error && <p className="text-sm text-subtext">Loading insights…</p>
      ) : !current.fga && !current.fta && !current.play_games ? (
        <p className="text-sm text-subtext">No saved shots or team plays counted yet. Processing may have missed events; this is not a verified score.</p>
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
