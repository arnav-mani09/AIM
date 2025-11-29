import { NextResponse } from "next/server";

import { getMockStats } from "@/lib/statsData";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const matchup = searchParams.get("matchup") ?? undefined;
  const stats = await getMockStats(matchup);
  return NextResponse.json(stats);
}
