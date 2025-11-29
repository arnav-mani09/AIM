import { NextResponse } from "next/server";
import { getMockPlatformData } from "@/lib/platformData";

export async function GET() {
  const data = await getMockPlatformData();
  return NextResponse.json(data);
}
