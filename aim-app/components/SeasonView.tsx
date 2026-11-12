"use client";

// The season from the coach's own films: each game's final score and team box score, the season
// totals and a season shot chart. Every number comes from AIM's drafted shots plus the coach's
// fixes. Stats AIM can't read from film yet are listed as coming soon, never filled with made-up numbers.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { FilmShotChart } from "@/components/FilmShotChart";
import { formatLocalDateTime } from "@/lib/dateTime";
import type { TeamLine, TeamSide } from "@/lib/reviewApi";
import { fetchSeason, pct, SeasonGame, SeasonSummary } from "@/lib/seasonApi";

const TEAMS: Array<[TeamSide, string]> = [
  ["valley", "Valley"],
  ["opponent", "Opponent"],
];

const COMING_SOON = ["Rebounds", "Assists", "Turnovers", "Steals", "Player names"];

export function SeasonView({ token, teamId }: { token: string; teamId: number }) {
  const router = useRouter();
  const [season, setSeason] = useState<SeasonSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The page remounts this per team (key={teamId}), so state starts empty for each team.
    let live = true;
    fetchSeason(token, teamId)
      .then((data) => live && setSeason(data))
      .catch((err) => live && setError(err instanceof Error ? err.message : "Couldn't load the season."));
    return () => {
      live = false;
    };
  }, [token, teamId]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!season) return <p className="text-sm text-subtext">Loading season…</p>;

  const reviewHref = (uploadId: number) => `/dashboard/film/${uploadId}/review?team=${teamId}`;

  if (season.games.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-stroke p-6 text-sm">
        {season.pending > 0 ? (
          <p className="text-ink">
            AIM is still reading {season.pending === 1 ? "your film" : `${season.pending} films`}. The season fills in
            once the shots are ready.
          </p>
        ) : (
          <>
            <p className="font-semibold text-ink">No games yet</p>
            <p className="mt-1 text-subtext">
              Upload a game film and AIM will draft the box score. Your season totals and shot chart build from there.
            </p>
            <Link
              href="/dashboard?tab=film"
              className="mt-4 inline-block rounded-2xl bg-accent px-4 py-2 font-semibold text-white"
            >
              Upload a game
            </Link>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {season.pending > 0 && (
        <p className="rounded-xl bg-tint px-3 py-2 text-sm text-ink">
          {season.pending} more {season.pending === 1 ? "film is" : "films are"} still processing and not counted yet.
        </p>
      )}

      <SeasonTotals season={season} />

      <section className="section-card">
        <h2 className="text-xl font-semibold text-ink">Games</h2>
        <p className="text-sm text-subtext">
          Scores come from the shots AIM found. Review a game to fix anything it got wrong.
        </p>
        <ul className="mt-4 space-y-3 text-sm">
          {season.games.map((game) => (
            <GameRow key={game.upload_id} game={game} reviewHref={reviewHref(game.upload_id)} />
          ))}
        </ul>
      </section>

      <FilmShotChart
        title="Season shot chart"
        events={season.shots}
        onPick={(shot) => {
          const film = season.shots.find((s) => s.id === shot.id);
          if (film) router.push(reviewHref(film.upload_id));
        }}
      />
    </div>
  );
}

function SeasonTotals({ season }: { season: SeasonSummary }) {
  const games = season.games.length;
  return (
    <section className="section-card overflow-x-auto">
      <h2 className="text-xl font-semibold text-ink">Season totals</h2>
      <p className="text-sm text-subtext">
        {games} {games === 1 ? "game" : "games"} with film. Deleted shots don&apos;t count.
      </p>
      <table className="mt-4 w-full min-w-[36rem] text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.14em] text-subtext">
          <tr>
            <th className="py-2">Team</th>
            <th>Points</th>
            <th>Per game</th>
            <th>FG</th>
            <th>FG%</th>
            <th>3PT</th>
            <th>3PT%</th>
            <th>FT</th>
            <th>FT%</th>
          </tr>
        </thead>
        <tbody>
          {TEAMS.map(([side, name]) => {
            const line = season.totals[side];
            return (
              <tr key={side} className="border-t border-stroke text-ink">
                <td className="py-3 font-semibold">{name}</td>
                <td className="font-bold">{line.pts}</td>
                <td>{(line.pts / games).toFixed(1)}</td>
                <td>
                  {line.fgm}/{line.fga}
                </td>
                <td>{pct(line.fgm, line.fga)}</td>
                <td>
                  {line.fg3m}/{line.fg3a}
                </td>
                <td>{pct(line.fg3m, line.fg3a)}</td>
                <td>
                  {line.ftm}/{line.fta}
                </td>
                <td>{pct(line.ftm, line.fta)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-subtext">
        <span>Coming soon:</span>
        {COMING_SOON.map((stat) => (
          <span key={stat} className="rounded-full border border-dashed border-stroke px-3 py-1">
            {stat}
          </span>
        ))}
      </div>
    </section>
  );
}

function GameRow({ game, reviewHref }: { game: SeasonGame; reviewHref: string }) {
  const { valley, opponent } = game.box_score;
  const fullyReviewed = game.shots > 0 && game.reviewed >= game.shots;
  return (
    <li className="rounded-2xl border border-stroke p-4">
      <details>
        <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
          <span className="flex flex-col">
            <span className="font-semibold text-ink">{game.game_matchup ?? game.title}</span>
            <span className="text-xs text-subtext">
              {formatLocalDateTime(game.game_scheduled_at ?? game.uploaded_at)}
            </span>
          </span>
          <span className="flex items-center gap-3">
            <span className="text-base font-semibold text-ink">
              Valley {valley.pts} - {opponent.pts} Opponent
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                fullyReviewed ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-800"
              }`}
            >
              {fullyReviewed ? "Reviewed" : `Draft · ${game.reviewed}/${game.shots} checked`}
            </span>
          </span>
        </summary>
        <div className="mt-4 overflow-x-auto">
          <BoxTable valley={valley} opponent={opponent} />
          <Link href={reviewHref} className="mt-3 inline-block text-xs font-semibold text-accent hover:underline">
            Review shots and watch film
          </Link>
        </div>
      </details>
    </li>
  );
}

function BoxTable({ valley, opponent }: { valley: TeamLine; opponent: TeamLine }) {
  const rows: Array<[string, TeamLine]> = [
    ["Valley", valley],
    ["Opponent", opponent],
  ];
  return (
    <table className="w-full min-w-[30rem] text-left text-sm">
      <thead className="text-xs uppercase tracking-[0.14em] text-subtext">
        <tr>
          <th className="py-1">Team</th>
          <th>FG</th>
          <th>3PT</th>
          <th>FT</th>
          <th>Points</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, line]) => (
          <tr key={name} className="border-t border-stroke text-ink">
            <td className="py-2 font-semibold">{name}</td>
            <td>
              {line.fgm}/{line.fga} ({pct(line.fgm, line.fga)})
            </td>
            <td>
              {line.fg3m}/{line.fg3a} ({pct(line.fg3m, line.fg3a)})
            </td>
            <td>
              {line.ftm}/{line.fta} ({pct(line.ftm, line.fta)})
            </td>
            <td className="font-bold">{line.pts}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
