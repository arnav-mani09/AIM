import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const backend = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const teamId = params.get("team");
  const clipId = params.get("clip");
  const token = params.get("token");
  if (!teamId || !clipId || !token) {
    return new Response("Missing params", { status: 400 });
  }

  const upstream = await fetch(`${backend}/api/v1/teams/${teamId}/clips/${clipId}/stream`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!upstream.ok || !upstream.body) {
    const body = await upstream.text();
    return new Response(body, { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}
