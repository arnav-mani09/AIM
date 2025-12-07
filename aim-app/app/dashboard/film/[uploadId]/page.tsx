"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import {
  ClipRecord,
  createFilmSegment,
  fetchFilmSegments,
  fetchGameUpload,
  FilmSegment,
  GameUploadRecord,
  publishFilmSegment,
} from "@/lib/teamApi";

type Params = {
  uploadId: string;
};

export default function FilmEditorPage({ params }: { params: Params }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamId = searchParams.get("team");
  const uploadId = Number(params.uploadId);
  const [token, setToken] = useState<string | null>(null);
  const [upload, setUpload] = useState<GameUploadRecord | null>(null);
  const [segments, setSegments] = useState<FilmSegment[]>([]);
  const [clips, setClips] = useState<ClipRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState<number>(0);
  const [startValue, setStartValue] = useState<number>(0);
  const [endValue, setEndValue] = useState<number>(0);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [formStatus, setFormStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [formMessage, setFormMessage] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

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

  useEffect(() => {
    if (!token || !teamId) {
      return;
    }
    setLoading(true);
    Promise.all([
      fetchGameUpload(token, Number(teamId), uploadId),
      fetchFilmSegments(token, Number(teamId), uploadId),
    ])
      .then(([uploadData, segmentsData]) => {
        setUpload(uploadData);
        setSegments(segmentsData);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load film"))
      .finally(() => setLoading(false));
  }, [token, teamId, uploadId]);

  useEffect(() => {
    if (!token || !teamId) {
      setVideoUrl(null);
      return;
    }
    const qs = new URLSearchParams({
      team: teamId,
      upload: String(uploadId),
      token,
    });
    setVideoUrl(`/api/film-stream?${qs.toString()}`);
  }, [token, teamId, uploadId]);

  const durationMinutes = useMemo(() => {
    if (!upload?.duration_seconds) return null;
    return (upload.duration_seconds / 60).toFixed(1);
  }, [upload]);

  const handleMetadataLoaded = () => {
    const video = videoRef.current;
    if (!video) return;
    const total = Math.floor(video.duration);
    setDuration(total);
    setStartValue(0);
    setEndValue(total);
  };

  const handleStartChange = (value: number) => {
    if (value >= endValue) {
      setStartValue(endValue - 1);
    } else {
      setStartValue(value);
    }
  };

  const handleEndChange = (value: number) => {
    if (value <= startValue) {
      setEndValue(startValue + 1);
    } else {
      setEndValue(value);
    }
  };

  const handleSetFromCurrent = (type: "start" | "end") => {
    const video = videoRef.current;
    if (!video) return;
    const current = Math.floor(video.currentTime);
    if (type === "start") {
      handleStartChange(current);
    } else {
      handleEndChange(current);
    }
  };

  const formatTimestamp = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0");
    const secs = Math.floor(seconds % 60)
      .toString()
      .padStart(2, "0");
    return `${mins}:${secs}`;
  };

  const handleCreateSegment = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !teamId) return;
    setFormStatus("loading");
    setFormMessage("");
    try {
      const segment = await createFilmSegment(token, Number(teamId), uploadId, {
        start_second: startValue,
        end_second: endValue,
        label: label || undefined,
        notes: notes || undefined,
      });
      setSegments((prev) => [...prev, segment].sort((a, b) => a.start_second - b.start_second));
      setLabel("");
      setNotes("");
      setFormStatus("success");
      setFormMessage("Segment saved.");
    } catch (err) {
      setFormStatus("error");
      setFormMessage(err instanceof Error ? err.message : "Failed to save segment");
    }
  };

  const handlePublish = async (segmentId: number) => {
    if (!token || !teamId) return;
    try {
      const clip = await publishFilmSegment(token, Number(teamId), uploadId, segmentId);
      setClips((prev) => [clip, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to publish clip");
    }
  };

  if (!teamId) {
    return null;
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <Link href="/dashboard" className="text-sm text-subtext hover:text-[#0e1a2e]">
        ← Back to dashboard
      </Link>
      {loading ? (
        <p>Loading film…</p>
      ) : error ? (
        <p className="text-red-500">{error}</p>
      ) : upload ? (
        <>
          <section className="section-card">
            <h1 className="text-3xl font-semibold text-[#0e1a2e]">{upload.title}</h1>
            <p className="mt-1 text-sm text-subtext">
              Uploaded {new Date(upload.uploaded_at).toLocaleString()}
              {durationMinutes && ` • ${durationMinutes} min`}
            </p>
            {upload.notes && <p className="mt-2 text-subtext">{upload.notes}</p>}
            <p className="mt-4 text-sm text-subtext">
              Once AIM finishes processing, suggested segments will show below. You can also create manual
              segments now by entering start/end points (in seconds).
            </p>
            {videoUrl ? (
              <div className="mt-6">
                <video
                  ref={videoRef}
                  controls
                  src={videoUrl}
                  className="w-full rounded-xl border border-stroke"
                  onLoadedMetadata={handleMetadataLoaded}
                />
              </div>
            ) : (
              <p className="mt-6 text-sm text-red-500">Video preview failed to load.</p>
            )}
          </section>

          <section className="section-card grid gap-6 md:grid-cols-2">
            <form onSubmit={handleCreateSegment} className="flex flex-col gap-3 rounded-2xl border border-stroke p-4 text-sm">
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Add segment</p>
              <div className="flex flex-col gap-2">
                <label className="text-xs uppercase tracking-[0.3em] text-subtext">Start</label>
                <input
                  type="range"
                  min={0}
                  max={Math.max(duration, endValue)}
                  value={startValue}
                  onChange={(event) => handleStartChange(Number(event.target.value))}
                />
                <div className="flex items-center justify-between text-xs text-subtext">
                  <span>{formatTimestamp(startValue)}</span>
                  <button
                    type="button"
                    className="text-accent"
                    onClick={() => handleSetFromCurrent("start")}
                  >
                    Use current time
                  </button>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-xs uppercase tracking-[0.3em] text-subtext">End</label>
                <input
                  type="range"
                  min={startValue + 1}
                  max={Math.max(duration, endValue)}
                  value={endValue}
                  onChange={(event) => handleEndChange(Number(event.target.value))}
                />
                <div className="flex items-center justify-between text-xs text-subtext">
                  <span>{formatTimestamp(endValue)}</span>
                  <button
                    type="button"
                    className="text-accent"
                    onClick={() => handleSetFromCurrent("end")}
                  >
                    Use current time
                  </button>
                </div>
              </div>
              <label className="flex flex-col gap-1">
                Label
                <input
                  type="text"
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  placeholder="e.g., Lane crunch-time floater"
                />
              </label>
              <label className="flex flex-col gap-1">
                Notes
                <textarea
                  rows={3}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                />
              </label>
              <button
                type="submit"
                className="rounded-2xl bg-accent px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={formStatus === "loading"}
              >
                {formStatus === "loading" ? "Saving…" : "Save segment"}
              </button>
              {formMessage && (
                <p className={`text-xs ${formStatus === "error" ? "text-red-500" : "text-green-600"}`}>
                  {formMessage}
                </p>
              )}
            </form>

            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Published clips</p>
              {clips.length === 0 ? (
                <p className="mt-3 text-sm text-subtext">Publish a segment to send it to the team workspace.</p>
              ) : (
                <ul className="mt-3 space-y-3 text-sm">
                  {clips.map((clip) => (
                    <li key={clip.id} className="rounded-2xl border border-stroke p-4">
                      <p className="font-semibold text-[#0e1a2e]">{clip.title}</p>
                      {clip.notes && <p className="text-subtext">{clip.notes}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="section-card">
            <h2 className="text-xl font-semibold text-[#0e1a2e]">Segments</h2>
            {segments.length === 0 ? (
              <p className="mt-2 text-sm text-subtext">No segments yet.</p>
            ) : (
              <ul className="mt-4 space-y-3 text-sm">
                {segments.map((segment) => (
                  <li key={segment.id} className="rounded-2xl border border-stroke p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-[#0e1a2e]">
                          {segment.label ?? "Untitled"} ({segment.start_second}s–{segment.end_second}s)
                        </p>
                        {segment.notes && <p className="text-subtext">{segment.notes}</p>}
                      </div>
                      <button
                        onClick={() => handlePublish(segment.id)}
                        className="rounded-full border border-stroke px-3 py-1 text-xs font-semibold text-[#0e1a2e]"
                      >
                        Publish clip
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
