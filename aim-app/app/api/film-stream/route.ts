import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const backend = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const teamId = searchParams.get("team");
  const uploadId = searchParams.get("upload");
  const token = searchParams.get("token");
  if (!teamId || !uploadId || !token) {
    return new Response("Missing params", { status: 400 });
  }

  const upstream = await fetch(`${backend}/api/v1/teams/${teamId}/film/${uploadId}/stream`, {
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new Response(text, { status: upstream.status });
  }

  const headers = new Headers(upstream.headers);
  return new Response(upstream.body, {
    status: upstream.status,
    headers,
  });
}
