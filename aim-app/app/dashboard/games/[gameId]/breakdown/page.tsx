"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import {
  GameRecord,
  PlayerRecord,
  PossessionRecord,
  ShotChartRecord,
  ShotZone,
  createPlayer,
  createPossession,
  deletePossession,
  fetchGame,
  fetchPlayers,
  fetchPossessions,
  fetchShotChart,
  updatePossession,
  fetchFilmPlaybackUrl,
} from "@/lib/teamApi";
import { formatLocalDateTime } from "@/lib/dateTime";
import { CourtDiagram } from "@/components/CourtDiagram";
import { ShotChart } from "@/components/ShotChart";

type Params = {
  gameId: string;
};

const ZONE_TITLES: Record<ShotZone, string> = {
  restricted_area: "Restricted area",
  paint: "Paint",
  mid_range_left: "Mid-range (L)",
  mid_range_right: "Mid-range (R)",
  corner_three_left: "Corner 3 (L)",
  corner_three_right: "Corner 3 (R)",
  wing_three_left: "Wing 3 (L)",
  wing_three_right: "Wing 3 (R)",
  top_of_key_three: "Top of key 3",
};

const THREE_POINT_ZONES = new Set<ShotZone>([
  "corner_three_left",
  "corner_three_right",
  "wing_three_left",
  "wing_three_right",
  "top_of_key_three",
]);

export default function GameBreakdownPage({ params }: { params: Params }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamId = searchParams.get("team");
  const gameId = Number(params.gameId);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const [game, setGame] = useState<GameRecord | null>(null);
  const [players, setPlayers] = useState<PlayerRecord[]>([]);
  const [possessions, setPossessions] = useState<PossessionRecord[]>([]);
  const [shotChart, setShotChart] = useState<ShotChartRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedZone, setSelectedZone] = useState<ShotZone | null>(null);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | "">("");
  const [made, setMade] = useState<"made" | "missed">("made");
  const [value, setValue] = useState<2 | 3>(2);
  const [videoSecond, setVideoSecond] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formStatus, setFormStatus] = useState<"idle" | "loading" | "error">("idle");
  const [formMessage, setFormMessage] = useState("");

  const [newPlayerName, setNewPlayerName] = useState("");
  const [newPlayerJersey, setNewPlayerJersey] = useState("");

  useEffect(() => {
    if (!teamId) {
      router.push("/dashboard");
      return;
    }
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("aim_access_token");
    if (!stored) {
      router.push("/auth/login");
      return;
    }
    setToken(stored);
  }, [router, teamId]);

  const loadAll = async (authToken: string, team: number) => {
    setLoading(true);
    try {
      const [gameData, playersData, possessionsData, chartData] = await Promise.all([
        fetchGame(authToken, team, gameId),
        fetchPlayers(authToken, team),
        fetchPossessions(authToken, team, gameId, { shotOnly: true }),
        fetchShotChart(authToken, team, gameId),
      ]);
      setGame(gameData);
      setPlayers(playersData);
      setPossessions(possessionsData);
      setShotChart(chartData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load game breakdown");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token || !teamId) return;
    loadAll(token, Number(teamId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, teamId, gameId]);

  const refresh = () => {
    if (!token || !teamId) return;
    Promise.all([
      fetchPossessions(token, Number(teamId), gameId, { shotOnly: true }),
      fetchShotChart(token, Number(teamId), gameId),
    ]).then(([possessionsData, chartData]) => {
      setPossessions(possessionsData);
      setShotChart(chartData);
    });
  };

  const resetForm = () => {
    setSelectedZone(null);
    setSelectedPlayerId("");
    setMade("made");
    setValue(2);
    setVideoSecond(null);
    setNotes("");
    setEditingId(null);
  };

  const handleSelectZone = (zone: ShotZone) => {
    setSelectedZone(zone);
    setValue(THREE_POINT_ZONES.has(zone) ? 3 : 2);
  };

  const handleUseCurrentTime = () => {
    const video = videoRef.current;
    if (!video) return;
    setVideoSecond(Math.floor(video.currentTime));
  };

  const handleEdit = (possession: PossessionRecord) => {
    setEditingId(possession.id);
    setSelectedZone((possession.shot_zone as ShotZone) ?? null);
    setSelectedPlayerId(possession.player_id ?? "");
    setMade(possession.shot_made ? "made" : "missed");
    setValue((possession.shot_value as 2 | 3) ?? 2);
    setVideoSecond(possession.video_start_second ?? null);
    setNotes(possession.outcome ?? "");
  };

  const handleDelete = async (possessionId: number) => {
    if (!token || !teamId) return;
    try {
      await deletePossession(token, Number(teamId), gameId, possessionId);
      refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete shot");
    }
  };

  const handleAddPlayer = async () => {
    if (!token || !teamId || !newPlayerName || !newPlayerJersey) return;
    try {
      const player = await createPlayer(token, Number(teamId), {
        name: newPlayerName,
        jersey_number: newPlayerJersey,
      });
      setPlayers((prev) => [...prev, player]);
      setSelectedPlayerId(player.id);
      setNewPlayerName("");
      setNewPlayerJersey("");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add player");
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !teamId || !selectedZone) {
      setFormStatus("error");
      setFormMessage("Tap a zone on the court diagram first.");
      return;
    }
    if (selectedPlayerId === "") {
      setFormStatus("error");
      setFormMessage("Select who took the shot — shots need a player to show up in the team chart.");
      return;
    }
    setFormStatus("loading");
    setFormMessage("");
    const payload = {
      player_id: selectedPlayerId,
      shot_made: made === "made",
      shot_zone: selectedZone,
      shot_value: value,
      video_start_second: videoSecond ?? undefined,
      outcome: notes || undefined,
    };
    try {
      if (editingId) {
        await updatePossession(token, Number(teamId), gameId, editingId, payload);
      } else {
        await createPossession(token, Number(teamId), gameId, payload);
      }
      resetForm();
      setFormStatus("idle");
      refresh();
    } catch (err) {
      setFormStatus("error");
      setFormMessage(err instanceof Error ? err.message : "Failed to save shot");
    }
  };

  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const primaryUploadId = game?.primary_upload_id ?? null;
  useEffect(() => {
    if (!token || !teamId || !primaryUploadId) {
      setVideoUrl(null);
      return;
    }
    let cancelled = false;
    fetchFilmPlaybackUrl(token, Number(teamId), primaryUploadId)
      .then(({ url }) => {
        if (!cancelled) setVideoUrl(url);
      })
      .catch(() => {
        if (!cancelled) setVideoUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, teamId, primaryUploadId]);

  if (!teamId) return null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <Link href={`/dashboard?tab=games`} className="text-sm text-subtext hover:text-ink">
        ← Back to games
      </Link>

      {loading ? (
        <p>Loading game breakdown…</p>
      ) : error ? (
        <p className="text-red-500">{error}</p>
      ) : game ? (
        <>
          <section className="section-card">
            <h1 className="text-3xl font-semibold text-ink">{game.matchup}</h1>
            <p className="mt-1 text-sm text-subtext">{formatLocalDateTime(game.scheduled_at)}</p>

            {videoUrl ? (
              <video ref={videoRef} controls src={videoUrl} className="mt-6 w-full rounded-xl border border-stroke" />
            ) : (
              <p className="mt-6 text-sm text-subtext">No film linked to this game yet — you can still log shots.</p>
            )}

            <div className="mt-6">
              <p className="label-text">Tap a zone to log a shot</p>
              <div className="mt-3 max-w-md">
                <CourtDiagram mode="select" selectedZone={selectedZone} onSelectZone={handleSelectZone} />
              </div>
            </div>
          </section>

          <section className="section-card">
            <p className="label-text">{editingId ? "Edit shot" : "Log shot"}</p>
            <form onSubmit={handleSubmit} className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-2 text-sm">
                <span>Zone</span>
                <p className="rounded-xl border border-stroke px-3 py-2 text-ink">
                  {selectedZone ? ZONE_TITLES[selectedZone] : "Tap the court diagram above"}
                </p>
              </div>

              <label className="flex flex-col gap-2 text-sm">
                Player
                <div className="flex gap-2">
                  <select
                    value={selectedPlayerId}
                    onChange={(event) =>
                      setSelectedPlayerId(event.target.value === "" ? "" : Number(event.target.value))
                    }
                    className="w-full rounded-xl border border-stroke px-3 py-2 text-ink"
                  >
                    <option value="">Select player…</option>
                    {players.map((player) => (
                      <option key={player.id} value={player.id}>
                        #{player.jersey_number} {player.name}
                      </option>
                    ))}
                  </select>
                </div>
              </label>

              <div className="flex flex-col gap-2 text-sm">
                <span>Result</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setMade("made")}
                    className={`flex-1 rounded-xl border px-3 py-2 font-semibold ${
                      made === "made" ? "border-accent bg-accent text-white" : "border-stroke text-ink"
                    }`}
                  >
                    Made
                  </button>
                  <button
                    type="button"
                    onClick={() => setMade("missed")}
                    className={`flex-1 rounded-xl border px-3 py-2 font-semibold ${
                      made === "missed" ? "border-accent bg-accent text-white" : "border-stroke text-ink"
                    }`}
                  >
                    Missed
                  </button>
                </div>
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <span>Shot value</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setValue(2)}
                    className={`flex-1 rounded-xl border px-3 py-2 font-semibold ${
                      value === 2 ? "border-accent bg-accent text-white" : "border-stroke text-ink"
                    }`}
                  >
                    2 pt
                  </button>
                  <button
                    type="button"
                    onClick={() => setValue(3)}
                    className={`flex-1 rounded-xl border px-3 py-2 font-semibold ${
                      value === 3 ? "border-accent bg-accent text-white" : "border-stroke text-ink"
                    }`}
                  >
                    3 pt
                  </button>
                </div>
              </div>

              <label className="flex flex-col gap-2 text-sm">
                Notes
                <input
                  type="text"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="e.g., catch-and-shoot off screen"
                />
              </label>

              <div className="flex flex-col gap-2 text-sm">
                <span>Video timestamp</span>
                <div className="flex items-center gap-3">
                  <span className="text-subtext">{videoSecond ?? "—"}</span>
                  <button
                    type="button"
                    onClick={handleUseCurrentTime}
                    disabled={!videoUrl}
                    className="rounded-full border border-stroke px-3 py-1 text-xs font-semibold text-ink disabled:opacity-50"
                  >
                    Use current video time
                  </button>
                </div>
              </div>

              <div className="md:col-span-2 flex items-center gap-3">
                <button
                  type="submit"
                  className="rounded-2xl bg-accent px-4 py-2 font-semibold text-white disabled:opacity-60"
                  disabled={formStatus === "loading"}
                >
                  {formStatus === "loading" ? "Saving…" : editingId ? "Save changes" : "Log shot"}
                </button>
                {editingId && (
                  <button type="button" onClick={resetForm} className="text-sm text-subtext hover:text-ink">
                    Cancel edit
                  </button>
                )}
                {formMessage && <p className="text-sm text-red-500">{formMessage}</p>}
              </div>
            </form>

            <div className="mt-6 rounded-2xl border border-dashed border-stroke p-4 text-sm">
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Add player</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  type="text"
                  value={newPlayerName}
                  onChange={(event) => setNewPlayerName(event.target.value)}
                  placeholder="Name"
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                />
                <input
                  type="text"
                  value={newPlayerJersey}
                  onChange={(event) => setNewPlayerJersey(event.target.value)}
                  placeholder="Jersey #"
                  className="w-24 rounded-xl border border-stroke px-3 py-2 text-ink"
                />
                <button
                  type="button"
                  onClick={handleAddPlayer}
                  className="rounded-xl border border-stroke px-3 py-2 font-semibold text-ink hover:bg-tint"
                >
                  Add
                </button>
              </div>
            </div>
          </section>

          <section className="grid gap-6 md:grid-cols-2">
            <div className="section-card">
              <p className="label-text">Logged shots ({possessions.length})</p>
              {possessions.length === 0 ? (
                <p className="mt-3 text-sm text-subtext">No shots logged yet.</p>
              ) : (
                <ul className="mt-4 space-y-3 text-sm">
                  {possessions.map((possession) => (
                    <li key={possession.id} className="rounded-2xl border border-stroke p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold text-ink">
                            {possession.player_name ?? "Unassigned"} —{" "}
                            {possession.shot_made ? "Made" : "Missed"} {possession.shot_value}pt
                          </p>
                          <p className="text-xs text-subtext">
                            {possession.shot_zone ? ZONE_TITLES[possession.shot_zone] : ""}
                            {possession.outcome ? ` • ${possession.outcome}` : ""}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                          <button onClick={() => handleEdit(possession)} className="text-accent hover:underline">
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(possession.id)}
                            className="text-red-500 hover:underline"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {shotChart && <ShotChart data={shotChart} />}
          </section>
        </>
      ) : null}
    </main>
  );
}
