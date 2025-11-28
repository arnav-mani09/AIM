import { NextResponse } from "next/server";

import { getMockStats } from "@/lib/statsData";

export async function GET() {
  const stats = await getMockStats();
  return NextResponse.json(stats);
}
