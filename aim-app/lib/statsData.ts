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

const mockStats: GameStats = {
  matchup: "Valley vs Central",
  possession: [
    { team: "Valley", percentage: 64 },
    { team: "Central", percentage: 36 },
  ],
  insights: [
    { player: "#24 Lane", label: "Shooter spotlight", detail: "64% eFG last five games" },
    { player: "#12 Brooks", label: "Handle watch", detail: "18% TO vs press" },
    { player: "ATO slip finish", label: "Clip callout", detail: "Shared with staff in 30s" },
  ],
  summary: {
    offensiveRating: 109.4,
    effectiveFG: 58.7,
    turnoverRate: 11.2,
  },
};

export async function getMockStats(): Promise<GameStats> {
  return structuredClone(mockStats);
}

export async function getGameStats(baseUrl?: string): Promise<GameStats> {
  const target = new URL("/api/stats", baseUrl ?? process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:3000");
  const response = await fetch(target);
  if (!response.ok) {
    throw new Error("Failed to fetch stats");
  }
  return response.json();
}
