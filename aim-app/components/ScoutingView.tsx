"use client";

// Scouting: the coach picks the games against the team they're scouting (opponents differ by game,
// so AIM can't group them on its own yet) and sees that opponent's shooting tendencies, zones and
// scouting notes. Below it, our own season tendencies from every game with film.

import { useEffect, useState } from "react";
import Link from "next/link";

import { TeamInsightsCard } from "@/components/InsightsPanel";
import { formatLocalDateTime } from "@/lib/dateTime";
import { fetchInsights, Insights } from "@/lib/insightsApi";

export function ScoutingView({ token, teamId }: { token: string; teamId: number }) {
  const [season, setSeason] = useState<Insights | null>(null);
  const [seasonError, setSeasonError] = useState<string | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [scout, setScout] = useState<{ key: string; data: Insights } | null>(null);
  const [scoutError, setScoutError] = useState<string | null>(null);
  const [view, setView] = useState<"opponent" | "us">("opponent");

  useEffect(() => {
    let live = true;
    fetchInsights(token, teamId)
      .then((data) => live && setSeason(data))
      .catch((err) => live && setSeasonError(err instanceof Error ? err.message : "Couldn't load your games."));
    return () => {
      live = false;
    };
  }, [token, teamId]);

  const key = [...picked].sort((a, b) => a - b).join(",");
  useEffect(() => {
    if (!key) return;
    let live = true;
    const ids = key.split(",").map(Number);
    fetchInsights(token, teamId, ids)
      .then((data) => {
        if (!live) return;
        setScout({ key, data });
        setScoutError(null);
      })
      .catch((err) => live && setScoutError(err instanceof Error ? err.message : "Couldn't load the report."));
    return () => {
      live = false;
    };
  }, [token, teamId, key]);

  if (seasonError) return <p className="text-sm text-red-500">{seasonError}</p>;
  if (!season) return <p className="text-sm text-subtext">Loading games…</p>;

  if (season.games.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-stroke p-6 text-sm">
        <p className="font-semibold text-ink">No games yet</p>
        <p className="mt-1 text-subtext">
          Upload a game film and AIM will read every shot. Scouting reports build from there.
        </p>
        <Link
          href="/dashboard?tab=film"
          className="mt-4 inline-block rounded-2xl bg-accent px-4 py-2 font-semibold text-white"
        >
          Upload a game
        </Link>
      </div>
    );
  }

  const toggle = (id: number) =>
    setPicked((now) => (now.includes(id) ? now.filter((x) => x !== id) : [...now, id]));
  const report = key && scout?.key === key ? scout.data : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex gap-2 text-sm">
        {(
          [
            ["opponent", "Scout an opponent"],
            ["us", "Our team"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setView(value)}
            className={`rounded-full px-4 py-2 font-semibold ${
              view === value ? "bg-accent text-white" : "border border-stroke text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {view === "opponent" ? (
        <>
          <section className="section-card">
            <h2 className="text-xl font-semibold text-ink">Pick the games</h2>
            <p className="text-sm text-subtext">
              Check every game you have against the team you&apos;re scouting. AIM adds up their shots from those
              games.
            </p>
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {season.games.map((g) => (
                <li key={g.upload_id}>
                  <label
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 text-sm ${
                      picked.includes(g.upload_id) ? "border-accent bg-tint" : "border-stroke"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-1 accent-[#1a4d84]"
                      checked={picked.includes(g.upload_id)}
                      onChange={() => toggle(g.upload_id)}
                    />
                    <span className="flex flex-col">
                      <span className="font-semibold text-ink">{g.game_matchup ?? g.title}</span>
                      <span className="text-xs text-subtext">
                        {formatLocalDateTime(g.game_scheduled_at ?? g.uploaded_at)}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>

          {!key ? (
            <p className="rounded-2xl border border-dashed border-stroke p-6 text-sm text-subtext">
              Pick one or more games above to see the opponent&apos;s tendencies.
            </p>
          ) : scoutError ? (
            <p className="text-sm text-red-500">{scoutError}</p>
          ) : !report ? (
            <p className="text-sm text-subtext">Building the report…</p>
          ) : (
            <section className="section-card">
              <h2 className="text-xl font-semibold text-ink">Opponent tendencies</h2>
              <p className="mb-4 text-sm text-subtext">
                From {report.games.length} {report.games.length === 1 ? "game" : "games"}.
                {report.skipped > 0 && ` ${report.skipped} picked film${report.skipped === 1 ? " is" : "s are"} still processing.`}{" "}
                Built from the shots AIM found plus your fixes.
              </p>
              <TeamInsightsCard team={report.teams.opponent} name="Opponent" comingSoon={report.coming_soon} />
            </section>
          )}
        </>
      ) : (
        <section className="section-card">
          <h2 className="text-xl font-semibold text-ink">Our team this season</h2>
          <p className="mb-4 text-sm text-subtext">
            Valley&apos;s shooting over all {season.games.length} {season.games.length === 1 ? "game" : "games"} with
            film. Player tendencies come once AIM reads jersey numbers on the site.
          </p>
          <TeamInsightsCard team={season.teams.valley} name="Valley" comingSoon={season.coming_soon} />
        </section>
      )}
    </div>
  );
}
