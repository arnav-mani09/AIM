import statsDataset from "@/data/gameStats.json";

export type PossessionSplit = {
  team: string;
  percentage: number;
};

export type PlayerInsight = {
  player: string;
  label: string;
  detail: string;
};

export type GameStats = {
  matchup: string;
  possession: PossessionSplit[];
  insights: PlayerInsight[];
  summary: {
    offensiveRating: number;
    effectiveFG: number;
    turnoverRate: number;
  };
};

type StatsRecord = GameStats & { id: string };

const records: StatsRecord[] = statsDataset as StatsRecord[];

export function findStats(matchup?: string): GameStats {
  const normalized = matchup?.toLowerCase();
  const match = records.find((record) => record.matchup.toLowerCase() === normalized) ?? records[0];
  return structuredClone(match);
}

export async function getMockStats(matchup?: string): Promise<GameStats> {
  return findStats(matchup);
}

export async function getGameStats(baseUrl?: string, matchup?: string): Promise<GameStats> {
  const origin = baseUrl ?? process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";
  const target = new URL("/api/v1/stats/game", origin);
  if (matchup) {
    target.searchParams.set("matchup", matchup);
  }
  const response = await fetch(target);
  if (!response.ok) {
    throw new Error("Failed to fetch stats");
  }
  return response.json();
}
