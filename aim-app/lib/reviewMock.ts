// Fake shot events for building the review screen before the backend is live.
// Only used in development (see lib/reviewApi.ts). Changes are kept in memory until reload.

import type { EventPatch, NewShot, ReviewData, ShotEvent, ShotType, TeamSide } from "./reviewApi";

const seed: Array<[number, TeamSide, ShotType, boolean, number]> = [
  [241, "valley", "fg2", true, 0.93],
  [268, "opponent", "fg3", false, 0.81],
  [302, "opponent", "fg2", true, 0.88],
  [355, "valley", "fg3", false, 0.42],
  [391, "valley", "ft", true, 0.97],
  [404, "valley", "ft", false, 0.95],
  [455, "opponent", "fg2", false, 0.55],
  [512, "valley", "fg2", true, 0.61],
  [570, "opponent", "fg3", true, 0.77],
  [633, "valley", "fg2", false, 0.38],
  [688, "opponent", "ft", true, 0.9],
  [701, "opponent", "ft", true, 0.92],
  [759, "valley", "fg3", true, 0.84],
  [812, "opponent", "fg2", false, 0.49],
  [866, "valley", "fg2", true, 0.73],
  [921, "opponent", "fg2", true, 0.66],
  [978, "valley", "fg3", false, 0.58],
  [1034, "opponent", "fg3", false, 0.86],
  [1090, "valley", "fg2", false, 0.31],
  [1142, "opponent", "fg2", true, 0.79],
];

let events: ShotEvent[] = seed.map(([t, team, shot_type, made, confidence], i) => ({
  id: i + 1,
  type: "shot",
  t,
  team,
  shot_type,
  made,
  confidence,
  player_number: null,
  status: "draft",
}));
let nextId = events.length + 1;

const pause = () => new Promise((resolve) => setTimeout(resolve, 150));

export async function mockFetchEvents(): Promise<ReviewData> {
  await pause();
  return { status: "ready", events: events.map((e) => ({ ...e })), box_score: null };
}

export async function mockPatchEvent(eventId: number, patch: EventPatch): Promise<ShotEvent> {
  await pause();
  const index = events.findIndex((e) => e.id === eventId);
  if (index < 0) throw new Error("That shot no longer exists.");
  events[index] = { ...events[index], ...patch };
  return { ...events[index] };
}

export async function mockAddShot(shot: NewShot): Promise<ShotEvent> {
  await pause();
  const created: ShotEvent = {
    id: nextId++,
    type: "shot",
    ...shot,
    confidence: 1,
    player_number: null,
    status: "fixed",
  };
  events = [...events, created];
  return { ...created };
}
