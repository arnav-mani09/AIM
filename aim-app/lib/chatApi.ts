// Coach chatbot: ask questions about a team's games. Answers can point at shots in the film.

export type ChatRole = "user" | "assistant";
export type ChatTurn = { role: ChatRole; content: string };
export type ChatCitation = { event_id: number; upload_id: number; t: number };
export type ChatReply = { answer: string; citations: ChatCitation[] };

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export async function askChat(
  token: string,
  teamId: number,
  messages: ChatTurn[],
  uploadId?: number,
): Promise<ChatReply> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ upload_id: uploadId ?? null, messages }),
    });
  } catch {
    throw new Error("Can't reach AIM right now. Check your connection and try again.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The assistant couldn't answer just now. Try again.");
  }
  return response.json() as Promise<ChatReply>;
}

/** Split an answer into text and cited shots ([[event:ID]] markers), in order. */
export function splitAnswer(answer: string, citations: ChatCitation[]) {
  const byId = new Map(citations.map((c) => [c.event_id, c]));
  const parts: Array<{ text: string } | { cite: ChatCitation }> = [];
  let last = 0;
  for (const match of answer.matchAll(/\[\[event:(\d+)\]\]/g)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ text: answer.slice(last, index) });
    const cite = byId.get(Number(match[1]));
    if (cite) parts.push({ cite });
    last = index + match[0].length;
  }
  if (last < answer.length) parts.push({ text: answer.slice(last) });
  return parts;
}
