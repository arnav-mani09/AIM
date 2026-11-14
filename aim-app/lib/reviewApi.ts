// API calls for the coach review screen: AIM's drafted shots, team rebounds and turnovers for one
// film, and the coach's fixes.
// In development, if the backend doesn't have these endpoints yet (404) or isn't running,
// the calls fall back to the fake data in lib/reviewMock.ts so the screen can still be built.

import { mockAddPlay, mockAddShot, mockFetchEvents, mockPatchEvent, mockSwapTeams } from "./reviewMock";

export type TeamSide = "valley" | "opponent";
export type ShotType = "fg2" | "fg3" | "ft";
export type EventStatus = "draft" | "confirmed" | "fixed" | "deleted";
/** Team offensive rebound, defensive rebound, turnover. */
export type PlayType = "oreb" | "dreb" | "to";

/** A team rebound or turnover AIM drafted (or the coach added). Not tied to a player yet. */
export type PlayEvent = {
  id: number;
  type: PlayType;
  t: number;
  team: TeamSide;
  confidence: number;
  status: EventStatus;
};

export type ShotEvent = {
  id: number;
  type: "shot";
  t: number;
  team: TeamSide;
  shot_type: ShotType;
  made: boolean;
  confidence: number;
  player_number: number | null;
  status: EventStatus;
  // Where the shooter's feet were, in feet on a half court with the rim at (0, 0): x to the right as
  // you face the basket, y out toward half court. Missing for free throws, shots added by hand and
  // shots where AIM found no shooter. Coach fixes don't move it.
  x?: number | null;
  y?: number | null;
  zone?: string | null;
};

export type TeamLine = {
  fgm: number;
  fga: number;
  fg3m: number;
  fg3a: number;
  ftm: number;
  fta: number;
  pts: number;
  /** Team rebounds and turnovers. Null for a film drafted before AIM found them (rerun to add). */
  oreb?: number | null;
  dreb?: number | null;
  reb?: number | null;
  to?: number | null;
};

export type ReviewData = {
  status: "pending" | "ready" | "failed";
  events: ShotEvent[];
  /** Team rebounds and turnovers. */
  plays?: PlayEvent[];
  /** False for a film drafted before AIM found rebounds and turnovers: rerun to add them. */
  has_plays?: boolean;
  box_score: { valley: TeamLine; opponent: TeamLine } | null;
  /** True when AIM had no jersey colors and guessed which team is Valley. */
  teams_guessed?: boolean;
};

export type EventPatch = Partial<Pick<ShotEvent, "made" | "team" | "shot_type" | "player_number" | "status" | "t">>;
export type NewShot = Pick<ShotEvent, "t" | "team" | "shot_type" | "made">;
export type PlayPatch = Partial<Pick<PlayEvent, "team" | "status" | "t">>;
export type NewPlay = Pick<PlayEvent, "t" | "team" | "type">;

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";
const isDev = process.env.NODE_ENV === "development";

// Film routes live under the team, like the rest of the film API.
const eventsPath = (teamId: number, uploadId: number) => `/api/v1/teams/${teamId}/film/${uploadId}/events`;

class NotAvailable extends Error {}

async function call<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(init?.headers ?? {}) },
    });
  } catch {
    if (isDev) throw new NotAvailable("Can't reach AIM right now. Check your connection and try again.");
    throw new Error("Can't reach AIM right now. Check your connection and try again.");
  }
  if (response.status === 404 && isDev) throw new NotAvailable("That film or event is no longer available.");
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? detail.message ?? "Something went wrong. Please try again.");
  }
  return response.json() as Promise<T>;
}

let usingMock = false;
let loadedReal = false;

/** True once the screen has fallen back to fake data (development only). */
export function isUsingMock(): boolean {
  return usingMock;
}

export function forceMock(): void {
  if (isDev) usingMock = true;
}

async function withMock<T>(real: () => Promise<T>, fake: () => Promise<T>, allowFallback = false): Promise<T> {
  if (usingMock) return fake();
  try {
    return await real();
  } catch (err) {
    if (allowFallback && err instanceof NotAvailable) {
      usingMock = true;
      return fake();
    }
    throw err;
  }
}

export function fetchReviewEvents(token: string, teamId: number, uploadId: number): Promise<ReviewData> {
  return withMock(async () => {
    const result = await call<ReviewData>(eventsPath(teamId, uploadId), token);
    loadedReal = true;
    return result;
  }, mockFetchEvents, !loadedReal);
}

export function patchReviewEvent(
  token: string,
  teamId: number,
  uploadId: number,
  eventId: number,
  patch: EventPatch,
): Promise<ShotEvent> {
  return withMock(
    () => call<ShotEvent>(`${eventsPath(teamId, uploadId)}/${eventId}`, token, { method: "PATCH", body: JSON.stringify(patch) }),
    () => mockPatchEvent(eventId, patch),
  );
}

/** Fix a rebound or turnover. Switching a rebound's team also switches offensive and defensive. */
export function patchReviewPlay(
  token: string,
  teamId: number,
  uploadId: number,
  playId: number,
  patch: PlayPatch,
): Promise<PlayEvent> {
  return withMock(
    () => call<PlayEvent>(`${eventsPath(teamId, uploadId)}/${playId}`, token, { method: "PATCH", body: JSON.stringify(patch) }),
    () => mockPatchEvent(playId, patch) as unknown as Promise<PlayEvent>,
  );
}

export function addReviewPlay(token: string, teamId: number, uploadId: number, play: NewPlay): Promise<PlayEvent> {
  return withMock(
    () =>
      call<PlayEvent>(`/api/v1/teams/${teamId}/film/${uploadId}/plays`, token, {
        method: "POST",
        body: JSON.stringify(play),
      }),
    () => mockAddPlay(play),
  );
}

export function addReviewShot(token: string, teamId: number, uploadId: number, shot: NewShot): Promise<ShotEvent> {
  return withMock(
    () => call<ShotEvent>(eventsPath(teamId, uploadId), token, { method: "POST", body: JSON.stringify(shot) }),
    () => mockAddShot(shot),
  );
}

/** Find the shots again from the film's tracks. Shots a coach already reviewed are kept. */
export function rerunReviewEvents(token: string, teamId: number, uploadId: number): Promise<ReviewData> {
  return withMock(
    () => call<ReviewData>(`${eventsPath(teamId, uploadId)}/rerun`, token, { method: "POST" }),
    mockFetchEvents,
  );
}

/** Flip Valley and Opponent on every shot, for when AIM picked the wrong team. */
export function swapReviewTeams(token: string, teamId: number, uploadId: number): Promise<ReviewData> {
  return withMock(
    () => call<ReviewData>(`${eventsPath(teamId, uploadId)}/swap-teams`, token, { method: "POST" }),
    mockSwapTeams,
  );
}

/** Box score from the shots and plays on screen, so it updates the moment a coach fixes
 * something. Without plays (hasPlays false) rebounds and turnovers stay null, not 0. */
export function boxScore(events: ShotEvent[], plays: PlayEvent[] = [], hasPlays = false): Record<TeamSide, TeamLine> {
  const empty = (): TeamLine => ({
    fgm: 0,
    fga: 0,
    fg3m: 0,
    fg3a: 0,
    ftm: 0,
    fta: 0,
    pts: 0,
    oreb: hasPlays ? 0 : null,
    dreb: hasPlays ? 0 : null,
    reb: hasPlays ? 0 : null,
    to: hasPlays ? 0 : null,
  });
  const lines: Record<TeamSide, TeamLine> = { valley: empty(), opponent: empty() };
  if (hasPlays) {
    for (const p of plays) {
      if (p.status === "deleted") continue;
      const line = lines[p.team];
      line[p.type] = (line[p.type] ?? 0) + 1;
      if (p.type !== "to") line.reb = (line.reb ?? 0) + 1;
    }
  }
  for (const e of events) {
    if (e.status === "deleted") continue;
    const line = lines[e.team];
    if (e.shot_type === "ft") {
      line.fta += 1;
      if (e.made) {
        line.ftm += 1;
        line.pts += 1;
      }
      continue;
    }
    line.fga += 1;
    if (e.shot_type === "fg3") line.fg3a += 1;
    if (e.made) {
      line.fgm += 1;
      line.pts += e.shot_type === "fg3" ? 3 : 2;
      if (e.shot_type === "fg3") line.fg3m += 1;
    }
  }
  return lines;
}
