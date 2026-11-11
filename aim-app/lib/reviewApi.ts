// API calls for the coach review screen: AIM's drafted shots for one film, and the coach's fixes.
// In development, if the backend doesn't have these endpoints yet (404) or isn't running,
// the calls fall back to the fake data in lib/reviewMock.ts so the screen can still be built.

import { mockAddShot, mockFetchEvents, mockPatchEvent } from "./reviewMock";

export type TeamSide = "valley" | "opponent";
export type ShotType = "fg2" | "fg3" | "ft";
export type EventStatus = "draft" | "confirmed" | "fixed" | "deleted";

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
};

export type TeamLine = {
  fgm: number;
  fga: number;
  fg3m: number;
  fg3a: number;
  ftm: number;
  fta: number;
  pts: number;
};

export type ReviewData = {
  status: "pending" | "ready" | "failed";
  events: ShotEvent[];
  box_score: { valley: TeamLine; opponent: TeamLine } | null;
};

export type EventPatch = Partial<Pick<ShotEvent, "made" | "team" | "shot_type" | "player_number" | "status" | "t">>;
export type NewShot = Pick<ShotEvent, "t" | "team" | "shot_type" | "made">;

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
    if (isDev) throw new NotAvailable();
    throw new Error("Can't reach AIM right now. Check your connection and try again.");
  }
  if (response.status === 404 && isDev) throw new NotAvailable();
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? detail.message ?? "Something went wrong. Please try again.");
  }
  return response.json() as Promise<T>;
}

let usingMock = false;

/** True once the screen has fallen back to fake data (development only). */
export function isUsingMock(): boolean {
  return usingMock;
}

export function forceMock(): void {
  if (isDev) usingMock = true;
}

async function withMock<T>(real: () => Promise<T>, fake: () => Promise<T>): Promise<T> {
  if (usingMock) return fake();
  try {
    return await real();
  } catch (err) {
    if (err instanceof NotAvailable) {
      usingMock = true;
      return fake();
    }
    throw err;
  }
}

export function fetchReviewEvents(token: string, teamId: number, uploadId: number): Promise<ReviewData> {
  return withMock(() => call<ReviewData>(eventsPath(teamId, uploadId), token), mockFetchEvents);
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

/** Box score from the shots on screen, so it updates the moment a coach fixes something. */
export function boxScore(events: ShotEvent[]): Record<TeamSide, TeamLine> {
  const empty = (): TeamLine => ({ fgm: 0, fga: 0, fg3m: 0, fg3a: 0, ftm: 0, fta: 0, pts: 0 });
  const lines: Record<TeamSide, TeamLine> = { valley: empty(), opponent: empty() };
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
