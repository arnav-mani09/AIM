"use client";

import { useState } from "react";
import Link from "next/link";
import { GameUploadRecord } from "@/lib/teamApi";
import { formatLocalDateTime } from "@/lib/dateTime";
import { filmStatusLabel } from "@/lib/filmIntake";

type Props = {
  films: GameUploadRecord[];
  teamId: number | "";
  loading: boolean;
  error: string | null;
  onDelete: (uploadId: number) => Promise<void>;
  onRefresh: () => void;
};

export default function FilmLibrary({ films, teamId, loading, error, onDelete, onRefresh }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [removing, setRemoving] = useState<number | null>(null);
  const visible = films.filter((film) => {
    const matches = `${film.title} ${film.game_matchup ?? ""}`.toLowerCase().includes(query.trim().toLowerCase());
    return matches && (filter === "all" || (filter === "ready" ? film.status === "ready" : film.status !== "ready"));
  });

  return (
    <section className="section-card" aria-labelledby="film-library-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="film-library-heading" className="text-xl font-semibold tracking-tight text-ink">Your film library</h2>
          <p className="mt-1 text-sm text-subtext">Open a game to watch, explore its stats, or create clips.</p>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading || teamId === ""} className="rounded-xl border border-stroke px-3 py-2 text-sm font-medium text-ink disabled:opacity-50">Refresh library</button>
      </div>
      {teamId !== "" && (
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <label className="flex-1">
            <span className="sr-only">Search game film</span>
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by game or opponent…" className="w-full rounded-xl border border-stroke bg-white px-3 py-2.5 text-sm" />
          </label>
          <label>
            <span className="sr-only">Filter film by status</span>
            <select value={filter} onChange={(event) => setFilter(event.target.value)} className="w-full rounded-xl border border-stroke bg-white px-3 py-2.5 text-sm sm:w-44">
              <option value="all">All film</option><option value="ready">Video ready</option><option value="pending">In progress / issues</option>
            </select>
          </label>
        </div>
      )}
      <div className="mt-5" aria-live="polite">
        {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error} Your last loaded films are kept below.</p>}
        {teamId === "" ? (
          <p className="rounded-xl border border-dashed border-stroke p-8 text-center text-sm text-subtext">Choose a team to see its game film.</p>
        ) : loading && films.length === 0 ? (
          <p role="status" className="py-8 text-center text-sm text-subtext">Loading your film library…</p>
        ) : !error && films.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stroke bg-slate-50 px-6 py-10 text-center">
            <p className="font-semibold text-ink">Your next game starts here</p>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-subtext">Add a download link or choose a video above. No email attachments or box score required.</p>
          </div>
        ) : visible.length === 0 && films.length > 0 ? (
          <p className="py-8 text-center text-sm text-subtext">No games match your search. Try another title or filter.</p>
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {visible.map((film) => (
              <li key={film.id} className="flex min-w-0 flex-col rounded-2xl border border-stroke bg-white p-4 transition-shadow hover:shadow-sm">
                <div className="flex items-start gap-3">
                  <div aria-hidden="true" className="flex h-12 w-14 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="4" width="18" height="16" rx="3" /><path d="m10 8 6 4-6 4Z" /></svg>
                  </div>
                  <div className="min-w-0 flex-1">
                    <Link href={`/dashboard/film/${film.id}?team=${teamId}`} className="break-words font-semibold text-ink hover:text-accent">{film.title}</Link>
                    <p className="mt-1 text-xs leading-5 text-subtext">{formatLocalDateTime(film.uploaded_at)}</p>
                    {film.game_matchup && <p className="truncate text-xs text-subtext">{film.game_matchup}</p>}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className={`rounded-md px-2 py-1 text-xs font-medium ${film.status === "ready" ? "bg-emerald-50 text-emerald-800" : film.status === "error" ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-700"}`}>{filmStatusLabel(film.status)}</span>
                  {film.duration_seconds != null && <span className="text-xs text-subtext">{Math.ceil(film.duration_seconds / 60)} min</span>}
                </div>
                {film.notes && <p className="mt-3 line-clamp-2 break-words text-sm text-subtext">{film.notes}</p>}
                {film.processing_error && <p className="mt-3 break-words text-sm text-red-700">{film.processing_error}</p>}
                <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-stroke pt-3 text-sm" style={{ marginTop: "1rem" }}>
                  <Link href={`/dashboard/film/${film.id}?team=${teamId}`} className="font-semibold text-accent hover:underline">{film.status === "ready" ? "Open game" : "View status"}<span aria-hidden="true"> →</span></Link>
                  {film.status === "ready" && <Link href={`/dashboard/film/${film.id}/review?team=${teamId}`} className="text-subtext hover:text-ink">Stats & plays</Link>}
                  {film.game_id && <Link href={`/dashboard/games/${film.game_id}/breakdown?team=${teamId}`} className="text-subtext hover:text-ink">Shot breakdown</Link>}
                  <button type="button" disabled={removing !== null} aria-label={`Remove ${film.title}`} onClick={async () => {
                    setRemoving(film.id);
                    try { await onDelete(film.id); } finally { setRemoving(null); }
                  }} className="ml-auto text-xs text-subtext hover:text-red-700 disabled:opacity-50">{removing === film.id ? "Removing…" : "Remove"}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
