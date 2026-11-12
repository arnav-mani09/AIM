"use client";

// Ask AIM about a game in plain words. Times in answers are buttons that jump the film there.

import { FormEvent, useState } from "react";

import { askChat, ChatCitation, ChatTurn, splitAnswer } from "@/lib/chatApi";

type Shown = ChatTurn & { citations?: ChatCitation[] };

const EXAMPLES = ["How did we shoot from three?", "What was the final score?", "How did their number 25 shoot?"];

function clock(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export default function ChatPanel({
  token,
  teamId,
  uploadId,
  onSeek,
}: {
  token: string | null;
  teamId: number;
  uploadId?: number;
  onSeek?: (t: number) => void;
}) {
  const [turns, setTurns] = useState<Shown[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy || !token) return;
    const next: Shown[] = [...turns, { role: "user", content: text }];
    setTurns(next);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      const reply = await askChat(
        token,
        teamId,
        next.map(({ role, content }) => ({ role, content })),
        uploadId,
      );
      setTurns([...next, { role: "assistant", content: reply.answer, citations: reply.citations }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The assistant couldn't answer just now. Try again.");
      setTurns(turns);
      setDraft(text);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(draft);
  };

  return (
    <section className="section-card flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold text-ink">{uploadId ? "Ask about this game" : "Ask about your games"}</h2>
        <p className="text-sm text-subtext">
          Answers come from AIM&apos;s shots, including your fixes.
          {onSeek ? " Click a time to watch that shot." : ""}
        </p>
      </div>

      {turns.length === 0 ? (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              onClick={() => ask(q)}
              disabled={busy || !token}
              className="rounded-full border border-stroke px-4 py-2 text-base text-ink hover:bg-accentMuted disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex max-h-[28rem] flex-col gap-3 overflow-y-auto">
          {turns.map((turn, i) => (
            <div
              key={i}
              className={
                turn.role === "user"
                  ? "self-end rounded-2xl bg-accent px-4 py-3 text-lg text-white"
                  : "self-start whitespace-pre-wrap rounded-2xl bg-accentMuted px-4 py-3 text-lg text-ink"
              }
            >
              {turn.role === "user"
                ? turn.content
                : splitAnswer(turn.content, turn.citations ?? []).map((part, j) =>
                    "text" in part ? (
                      <span key={j}>{part.text}</span>
                    ) : (
                      <button
                        key={j}
                        onClick={() => onSeek?.(part.cite.t)}
                        disabled={!onSeek || part.cite.upload_id !== uploadId}
                        title="Watch this shot"
                        className="mx-1 rounded-full bg-white px-2 py-0.5 text-base font-semibold text-accent underline disabled:no-underline"
                      >
                        {clock(part.cite.t)}
                      </button>
                    ),
                  )}
            </div>
          ))}
          {busy && <p className="text-subtext">Thinking…</p>}
        </div>
      )}

      {error && <p className="text-red-600">{error}</p>}

      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a question, like: who scored the most for us?"
          maxLength={1000}
          className="flex-1 rounded-2xl border border-stroke px-4 py-3 text-lg"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim() || !token}
          className="rounded-2xl bg-accent px-6 py-3 text-lg font-semibold text-white disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </section>
  );
}
