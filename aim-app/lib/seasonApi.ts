// The season view: every film whose shots are ready, each game's team box score, the season
// totals and every shot for the season shot chart, from one call (GET /api/v1/teams/{team}/season).

import type { ShotEvent, TeamLine, TeamSide } from "./reviewApi";

export type SeasonGame = {
  upload_id: number;
  title: string;
  uploaded_at: string;
  game_id?: number | null;
  game_matchup?: string | null;
  game_scheduled_at?: string | null;
  /** Shots that count (not deleted). */
  shots: number;
  /** Shots a coach has confirmed, fixed or deleted. */
  reviewed: number;
  /** Team rebounds and turnovers were drafted for this film. */
  has_plays?: boolean;
  box_score: Record<TeamSide, TeamLine>;
};

export type SeasonShot = ShotEvent & { upload_id: number };

export type SeasonSummary = {
  /** Newest film first. */
  games: SeasonGame[];
  /** Rebounds and turnovers add up over the plays_games films that have them. */
  totals: Record<TeamSide, TeamLine>;
  plays_games?: number;
  /** Films still being processed, not counted yet. */
  pending: number;
  shots: SeasonShot[];
};

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchSeason(token: string, teamId: number): Promise<SeasonSummary> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/season`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error("Can't reach AIM right now. Check your connection and try again.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Couldn't load the season. Please try again.");
  }
  return response.json() as Promise<SeasonSummary>;
}

/** "45%" from makes and attempts, or "-" when there were no attempts. */
export function pct(made: number, attempts: number): string {
  return attempts > 0 ? `${Math.round((made / attempts) * 100)}%` : "-";
}
