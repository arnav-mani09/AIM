// Team shooting insights (GET /api/v1/teams/{team}/insights?upload_ids=...): advanced shooting
// stats, a zone table and plain-language scouting lines for Valley and the Opponent. Same formulas
// and zone names as ml/tools/insights.py.

import type { TeamSide } from "./reviewApi";

export type InsightZone = "rim" | "paint" | "midrange" | "corner3" | "above_break3" | "unknown";

export type ZoneRow = {
  zone: InsightZone;
  label: string;
  attempts: number;
  makes: number;
  fg_pct: number | null;
  /** Percent of the team's field goal tries. */
  share: number | null;
  points: number;
  small_sample: boolean;
};

export type TeamInsights = {
  games: number;
  pts: number;
  fgm: number;
  fga: number;
  fg2m: number;
  fg2a: number;
  fg3m: number;
  fg3a: number;
  ftm: number;
  fta: number;
  pts_per_game: number | null;
  fg_pct: number | null;
  fg3_pct: number | null;
  ft_pct: number | null;
  efg_pct: number | null;
  ts_pct: number | null;
  /** Free throw tries per field goal try. */
  ft_rate: number | null;
  /** Share of field goal tries that are 3s (0 to 1). */
  fg3a_rate: number | null;
  small_sample: boolean;
  zones: ZoneRow[];
  lines: string[];
};

export type InsightsGame = {
  upload_id: number;
  title: string;
  uploaded_at: string;
  game_matchup?: string | null;
  game_scheduled_at?: string | null;
};

export type Insights = {
  games: InsightsGame[];
  /** Picked films whose shots aren't ready yet. */
  skipped: number;
  teams: Record<TeamSide, TeamInsights>;
  coming_soon: string[];
};

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

/** Insights over the given films, or every ready film when none are given. */
export async function fetchInsights(token: string, teamId: number, uploadIds?: number[]): Promise<Insights> {
  const query = (uploadIds ?? []).map((id) => `upload_ids=${id}`).join("&");
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/insights${query ? `?${query}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error("Can't reach AIM right now. Check your connection and try again.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Couldn't load the insights. Please try again.");
  }
  return response.json() as Promise<Insights>;
}
