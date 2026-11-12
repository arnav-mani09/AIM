"use client";

// Coach review screen: AIM drafts every shot, the coach confirms or fixes each one.
// Least sure shots come first. Everything works with big buttons or keyboard shortcuts.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import ChatPanel from "@/components/ChatPanel";
import { fetchFilmPlaybackUrl } from "@/lib/teamApi";
import {
  addReviewShot,
  boxScore,
  EventPatch,
  fetchReviewEvents,
  forceMock,
  isUsingMock,
  patchReviewEvent,
  rerunReviewEvents,
  ReviewData,
  swapReviewTeams,
  ShotEvent,
  ShotType,
  TeamLine,
} from "@/lib/reviewApi";

type Filter = "all" | "unsure" | "unreviewed";

const UNSURE_BELOW = 0.7;
const LEAD_IN_SECONDS = 3;
const SHOT_LABEL: Record<ShotType, string> = { fg2: "2", fg3: "3", ft: "FT" };
const TEAM_LABEL = { valley: "Valley", opponent: "Opponent" } as const;

function clock(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export default function ReviewPage() {
  const params = useParams<{ uploadId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const uploadId = Number(params.uploadId);
  const teamParam = searchParams.get("team");
  const teamId = teamParam ? Number(teamParam) : 0;
  // Development only: ?mock=1 opens the screen with fake shots, no login needed.
  const mockOnly = process.env.NODE_ENV === "development" && searchParams.get("mock") === "1";

  const [token, setToken] = useState<string | null>(null);
  const [data, setData] = useState<ReviewData | null>(null);
  const [events, setEvents] = useState<ShotEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Sign-in check, same as the film page.
  useEffect(() => {
    if (mockOnly) {
      forceMock();
      setToken("mock");
      return;
    }
    if (!teamParam) {
      router.push("/dashboard");
      return;
    }
    const stored = window.localStorage.getItem("aim_access_token");
    if (!stored) {
      router.push("/auth/login");
      return;
    }
    setToken(stored);
  }, [mockOnly, router, teamParam]);

  const load = useCallback(() => {
    if (!token) return;
    fetchReviewEvents(token, teamId, uploadId)
      .then((result) => {
        setData(result);
        setEvents(result.events);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load the shots."));
  }, [token, teamId, uploadId]);

  useEffect(load, [load]);

  // Films uploaded before the shot finder existed (or after it improves) need it run again.
  const rerun = useCallback(() => {
    if (!token) return;
    setActionError(null);
    rerunReviewEvents(token, teamId, uploadId)
      .then((result) => {
        setData(result);
        setEvents(result.events);
      })
      .catch((err) => setActionError(err instanceof Error ? err.message : "Couldn't start finding shots."));
  }, [token, teamId, uploadId]);

  // Swap teams: flip Valley and Opponent on every shot when AIM picked the wrong team.
  const [swapping, setSwapping] = useState(false);
  const swapTeams = useCallback(() => {
    if (!token) return;
    setActionError(null);
    setSwapping(true);
    swapReviewTeams(token, teamId, uploadId)
      .then((result) => {
        setData(result);
        setEvents(result.events);
      })
      .catch((err) => setActionError(err instanceof Error ? err.message : "Couldn't swap the teams."))
      .finally(() => setSwapping(false));
  }, [token, teamId, uploadId]);

  // Keep checking while AIM is still working on the film.
  useEffect(() => {
    if (data?.status !== "pending") return;
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [data?.status, load]);

  useEffect(() => {
    if (!token || mockOnly) return;
    let cancelled = false;
    fetchFilmPlaybackUrl(token, teamId, uploadId)
      .then(({ url }) => !cancelled && setVideoUrl(url))
      .catch(() => !cancelled && setVideoUrl(null));
    return () => {
      cancelled = true;
    };
  }, [token, teamId, uploadId, mockOnly]);

  // Least sure first; ties go in game order.
  const queue = useMemo(() => {
    const visible = events.filter((e) => {
      if (filter === "unsure") return e.confidence < UNSURE_BELOW && e.status !== "deleted";
      if (filter === "unreviewed") return e.status === "draft";
      return true;
    });
    return visible.sort((a, b) => a.confidence - b.confidence || a.t - b.t);
  }, [events, filter]);

  const selected = events.find((e) => e.id === selectedId) ?? null;
  const reviewed = events.filter((e) => e.status !== "draft").length;
  const lines = useMemo(() => boxScore(events), [events]);

  const playFrom = useCallback((t: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, t - LEAD_IN_SECONDS);
    video.play().catch(() => {
      /* browser blocked autoplay; the coach can press play */
    });
  }, []);

  const select = useCallback(
    (event: ShotEvent | undefined) => {
      if (!event) return;
      setSelectedId(event.id);
      playFrom(event.t);
    },
    [playFrom],
  );

  const step = useCallback(
    (direction: 1 | -1) => {
      if (queue.length === 0) return;
      const index = queue.findIndex((e) => e.id === selectedId);
      const next = index < 0 ? 0 : Math.min(queue.length - 1, Math.max(0, index + direction));
      select(queue[next]);
    },
    [queue, selectedId, select],
  );

  // Change a shot right away on screen, then save. If saving fails, put it back and say so.
  const update = useCallback(
    async (event: ShotEvent, patch: EventPatch) => {
      if (!token) return;
      const before = event;
      setEvents((all) => all.map((e) => (e.id === event.id ? { ...e, ...patch } : e)));
      setActionError(null);
      try {
        const saved = await patchReviewEvent(token, teamId, uploadId, event.id, patch);
        setEvents((all) => all.map((e) => (e.id === saved.id ? saved : e)));
      } catch (err) {
        setEvents((all) => all.map((e) => (e.id === before.id ? before : e)));
        setActionError(
          `Your change to the shot at ${clock(before.t)} didn't save, so it was undone. ${
            err instanceof Error ? err.message : ""
          }`,
        );
      }
    },
    [token, teamId, uploadId],
  );

  const fix = useCallback(
    (patch: EventPatch) => {
      if (selected) update(selected, { ...patch, status: "fixed" });
    },
    [selected, update],
  );

  const confirmAndNext = useCallback(() => {
    if (!selected) return;
    const index = queue.findIndex((e) => e.id === selected.id);
    // In "Not reviewed yet" the confirmed shot leaves the list, so the next one slides into its place.
    const next = filter === "unreviewed" ? queue[index + 1] ?? queue[index - 1] : queue[index + 1];
    if (selected.status === "draft" || selected.status === "deleted") {
      update(selected, { status: selected.status === "deleted" ? "fixed" : "confirmed" });
    }
    if (next && next.id !== selected.id) select(next);
  }, [selected, queue, filter, update, select]);

  const remove = useCallback(() => {
    if (selected && selected.status !== "deleted") update(selected, { status: "deleted" });
  }, [selected, update]);

  const addShot = useCallback(async () => {
    if (!token) return;
    const t = Math.round((videoRef.current?.currentTime ?? selected?.t ?? 0) * 10) / 10;
    setActionError(null);
    try {
      const created = await addReviewShot(token, teamId, uploadId, {
        t,
        team: selected?.team ?? "valley",
        shot_type: "fg2",
        made: false,
      });
      setEvents((all) => [...all, created]);
      setSelectedId(created.id);
    } catch (err) {
      setActionError(`The new shot didn't save. ${err instanceof Error ? err.message : ""}`);
    }
  }, [token, teamId, uploadId, selected]);

  // Keyboard shortcuts. Ignored while typing in a box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === " ") {
        const video = videoRef.current;
        if (video) {
          if (video.paused) video.play().catch(() => {});
          else video.pause();
        }
      } else if (key === "j") step(-1);
      else if (key === "k") step(1);
      else if (key === "m" && selected) fix({ made: !selected.made });
      else if (key === "t" && selected) fix({ team: selected.team === "valley" ? "opponent" : "valley" });
      else if (key === "2") fix({ shot_type: "fg2" });
      else if (key === "3") fix({ shot_type: "fg3" });
      else if (key === "f") fix({ shot_type: "ft" });
      else if (key === "enter") confirmAndNext();
      else if (key === "delete" || key === "backspace") remove();
      else if (key === "a") addShot();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, selected, fix, confirmAndNext, remove, addShot]);

  const backHref = teamParam ? `/dashboard/film/${uploadId}?team=${teamParam}` : "/dashboard";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <Link href={backHref} className="text-sm text-subtext hover:text-ink">
        ← Back to film
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-ink">Review shots</h1>
          <p className="mt-1 text-sm text-subtext">
            AIM drafted these shots. Check each one, fix anything wrong, and confirm it. The ones AIM is least
            sure about are at the top.
          </p>
        </div>
        {isUsingMock() && (
          <span className="rounded-full bg-yellow-100 px-3 py-1 text-xs font-semibold text-yellow-700">
            Sample data (development only)
          </span>
        )}
      </div>

      {actionError && (
        <div className="flex items-start justify-between gap-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p>{actionError}</p>
          <button onClick={() => setActionError(null)} className="font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {/* Swap teams: a banner when AIM guessed which team is yours, a small link otherwise. */}
      {data?.status === "ready" &&
        (data.teams_guessed ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
            <p>AIM guessed which team is yours. Wrong? Swap teams.</p>
            <button
              onClick={swapTeams}
              disabled={swapping}
              className="rounded-2xl bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
            >
              {swapping ? "Swapping…" : "Swap teams"}
            </button>
          </div>
        ) : (
          <div className="flex justify-end">
            <button
              onClick={swapTeams}
              disabled={swapping}
              className="text-xs text-subtext underline hover:text-ink disabled:opacity-60"
            >
              {swapping ? "Swapping…" : "Wrong team labels? Swap teams"}
            </button>
          </div>
        ))}

      {loadError ? (
        <section className="section-card">
          <p className="text-red-600">{loadError}</p>
          <button onClick={load} className="mt-4 rounded-2xl bg-accent px-4 py-2 font-semibold text-white">
            Try again
          </button>
        </section>
      ) : !data ? (
        <p>Loading shots…</p>
      ) : data.status === "pending" ? (
        <section className="section-card">
          <h2 className="text-xl font-semibold text-ink">AIM is still working on this film</h2>
          <p className="mt-2 text-subtext">
            The shots will show up here when it&apos;s done. A full game usually takes about 30 minutes. This page
            checks again on its own.
          </p>
          <p className="mt-4 text-sm text-subtext">Uploaded this film before shots were added, or stuck for over an hour?</p>
          <button onClick={rerun} className="mt-2 rounded-2xl bg-accent px-4 py-2 font-semibold text-white">
            Find shots now
          </button>
        </section>
      ) : data.status === "failed" ? (
        <section className="section-card">
          <h2 className="text-xl font-semibold text-red-600">AIM couldn&apos;t finish this film</h2>
          <p className="mt-2 text-subtext">
            Something went wrong while finding shots. Try again below, or contact us and we&apos;ll look into it.
          </p>
          <button onClick={rerun} className="mt-4 rounded-2xl bg-accent px-4 py-2 font-semibold text-white">
            Try finding shots again
          </button>
        </section>
      ) : (
        <>
          <section className="section-card flex flex-col gap-4">
            {videoUrl ? (
              <video ref={videoRef} controls src={videoUrl} className="w-full rounded-xl border border-stroke" />
            ) : (
              <div className="flex aspect-video w-full items-center justify-center rounded-xl border border-stroke bg-accentMuted text-subtext">
                {mockOnly ? "Video goes here (sample data has no film)" : "The video didn't load. Try refreshing."}
              </div>
            )}
            <ProgressBar reviewed={reviewed} total={events.length} />
          </section>

          <BoxScore valley={lines.valley} opponent={lines.opponent} />

          <ChatPanel token={token} teamId={teamId} uploadId={uploadId} onSeek={playFrom} />

          <section className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
            <div className="section-card flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xl font-semibold text-ink">Shots</h2>
                <div className="flex gap-2 text-sm">
                  {(
                    [
                      ["all", "All"],
                      ["unsure", "Unsure"],
                      ["unreviewed", "Not reviewed yet"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => setFilter(value)}
                      className={`rounded-full px-4 py-2 font-semibold ${
                        filter === value ? "bg-accent text-white" : "border border-stroke text-ink"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {events.length === 0 ? (
                <p className="text-subtext">
                  AIM didn&apos;t find any shots in this film. If that looks wrong, play the film and use &quot;Add shot
                  here&quot; for each one.
                </p>
              ) : queue.length === 0 ? (
                <p className="text-subtext">Nothing left in this list. Nice work.</p>
              ) : (
                <ul className="flex max-h-[32rem] flex-col gap-2 overflow-y-auto pr-1">
                  {queue.map((e) => (
                    <EventRow key={e.id} event={e} active={e.id === selectedId} onClick={() => select(e)} />
                  ))}
                </ul>
              )}
            </div>

            <div className="section-card flex flex-col gap-5">
              {selected ? (
                <ShotEditor
                  event={selected}
                  onFix={fix}
                  onConfirm={confirmAndNext}
                  onDelete={remove}
                  onReplay={() => playFrom(selected.t)}
                />
              ) : (
                <p className="text-subtext">
                  Pick a shot from the list, or press K to start with the one AIM is least sure about.
                </p>
              )}
              <button
                onClick={addShot}
                className="rounded-2xl border-2 border-dashed border-accent px-4 py-3 text-lg font-semibold text-accent"
              >
                + Add shot here (missed by AIM)
              </button>
              <Shortcuts />
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function ProgressBar({ reviewed, total }: { reviewed: number; total: number }) {
  const share = total === 0 ? 0 : Math.round((reviewed / total) * 100);
  return (
    <div>
      <div className="flex justify-between text-sm font-semibold text-ink">
        <span>
          Reviewed {reviewed} of {total}
        </span>
        <span>{share}%</span>
      </div>
      <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-stroke">
        <div className="h-full rounded-full bg-green-600 transition-all" style={{ width: `${share}%` }} />
      </div>
    </div>
  );
}

function BoxScore({ valley, opponent }: { valley: TeamLine; opponent: TeamLine }) {
  const rows: Array<[string, TeamLine]> = [
    ["Valley", valley],
    ["Opponent", opponent],
  ];
  return (
    <section className="section-card overflow-x-auto">
      <h2 className="text-xl font-semibold text-ink">Box score</h2>
      <p className="text-sm text-subtext">Updates as you fix shots. Deleted shots don&apos;t count.</p>
      <table className="mt-4 w-full min-w-[28rem] text-left text-lg">
        <thead className="text-xs uppercase tracking-[0.14em] text-subtext">
          <tr>
            <th className="py-2">Team</th>
            <th>FG</th>
            <th>3PT</th>
            <th>FT</th>
            <th>Points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, line]) => (
            <tr key={name} className="border-t border-stroke">
              <td className="py-3 font-semibold text-ink">{name}</td>
              <td>
                {line.fgm}/{line.fga}
              </td>
              <td>
                {line.fg3m}/{line.fg3a}
              </td>
              <td>
                {line.ftm}/{line.fta}
              </td>
              <td className="text-2xl font-bold text-ink">{line.pts}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function EventRow({ event, active, onClick }: { event: ShotEvent; active: boolean; onClick: () => void }) {
  const unsure = event.confidence < UNSURE_BELOW;
  const deleted = event.status === "deleted";
  const badge =
    event.status === "confirmed"
      ? ["Confirmed", "bg-green-100 text-green-700"]
      : event.status === "fixed"
        ? ["Fixed", "bg-blue-100 text-blue-700"]
        : deleted
          ? ["Deleted", "bg-gray-200 text-gray-600"]
          : unsure
            ? ["Unsure", "bg-yellow-100 text-yellow-800"]
            : ["To check", "bg-accentMuted text-accent"];
  return (
    <li>
      <button
        onClick={onClick}
        className={`flex w-full items-center justify-between gap-3 rounded-2xl border p-3 text-left ${
          active ? "border-accent bg-accentMuted" : "border-stroke"
        } ${deleted ? "opacity-50" : ""}`}
      >
        <span className="flex items-center gap-3">
          <span className="w-14 font-mono text-sm text-subtext">{clock(event.t)}</span>
          <span className={`font-semibold text-ink ${deleted ? "line-through" : ""}`}>
            {TEAM_LABEL[event.team]} {SHOT_LABEL[event.shot_type]} {event.made ? "make" : "miss"}
          </span>
        </span>
        <span className="flex items-center gap-2">
          <span className="text-xs text-subtext">{Math.round(event.confidence * 100)}% sure</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badge[1]}`}>{badge[0]}</span>
        </span>
      </button>
    </li>
  );
}

function Choice({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-2xl px-4 py-4 text-lg font-semibold ${
        on ? "bg-accent text-white" : "border border-stroke text-ink hover:bg-accentMuted"
      }`}
    >
      {children}
    </button>
  );
}

function ShotEditor({
  event,
  onFix,
  onConfirm,
  onDelete,
  onReplay,
}: {
  event: ShotEvent;
  onFix: (patch: EventPatch) => void;
  onConfirm: () => void;
  onDelete: () => void;
  onReplay: () => void;
}) {
  const deleted = event.status === "deleted";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-ink">Shot at {clock(event.t)}</h2>
        <button onClick={onReplay} className="rounded-full border border-stroke px-4 py-2 text-sm font-semibold text-ink">
          ↺ Watch again
        </button>
      </div>
      {deleted && <p className="text-sm text-subtext">This shot is deleted. Press Confirm to bring it back.</p>}
      <div className="flex gap-2">
        <Choice on={event.made} onClick={() => onFix({ made: true })}>
          Make
        </Choice>
        <Choice on={!event.made} onClick={() => onFix({ made: false })}>
          Miss
        </Choice>
      </div>
      <div className="flex gap-2">
        <Choice on={event.team === "valley"} onClick={() => onFix({ team: "valley" })}>
          Valley
        </Choice>
        <Choice on={event.team === "opponent"} onClick={() => onFix({ team: "opponent" })}>
          Opponent
        </Choice>
      </div>
      <div className="flex gap-2">
        {(["fg2", "fg3", "ft"] as const).map((type) => (
          <Choice key={type} on={event.shot_type === type} onClick={() => onFix({ shot_type: type })}>
            {SHOT_LABEL[type]}
          </Choice>
        ))}
      </div>
      <div className="flex gap-2">
        <button onClick={onConfirm} className="flex-[2] rounded-2xl bg-green-600 px-4 py-4 text-lg font-semibold text-white">
          {deleted ? "Bring back" : "✓ Confirm"}
        </button>
        <button
          onClick={onDelete}
          disabled={deleted}
          className="flex-1 rounded-2xl border border-red-300 px-4 py-4 text-lg font-semibold text-red-600 disabled:opacity-40"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function Shortcuts() {
  const keys: Array<[string, string]> = [
    ["Space", "Play or pause"],
    ["J / K", "Previous / next shot"],
    ["M", "Make or miss"],
    ["T", "Switch team"],
    ["2 / 3 / F", "2, 3 or free throw"],
    ["Enter", "Confirm and go to next"],
    ["Delete", "Delete shot"],
    ["A", "Add shot here"],
  ];
  return (
    <div className="rounded-2xl bg-accentMuted p-4 text-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-subtext">Keyboard shortcuts</p>
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        {keys.map(([key, what]) => (
          <li key={key} className="flex gap-2">
            <kbd className="min-w-[4.5rem] rounded border border-stroke bg-white px-1.5 text-center font-mono text-xs text-ink">
              {key}
            </kbd>
            <span className="text-subtext">{what}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
