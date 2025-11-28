import { NextResponse } from "next/server";

import type { PlatformData } from "@/lib/platformData";
import { getMockPlatformData } from "@/lib/platformData";

export async function GET() {
  const data: PlatformData = await getMockPlatformData();
  return NextResponse.json(data);
}
