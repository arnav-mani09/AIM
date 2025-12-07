"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { ClipRecord, fetchClip } from "@/lib/teamApi";

export default function ClipDetailPage({ params }: { params: { clipId: string } }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const teamId = searchParams.get("team");
  const clipId = Number(params.clipId);
  const [token, setToken] = useState<string | null>(null);
  const [clip, setClip] = useState<ClipRecord | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
    if (!token || !teamId) return;
    fetchClip(token, Number(teamId), clipId)
      .then((data) => {
        setClip(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load clip"));
  }, [token, teamId, clipId]);

  useEffect(() => {
    if (!token || !teamId) {
      setVideoUrl(null);
      return;
    }
    setVideoUrl(`/api/clip-stream?team=${teamId}&clip=${clipId}&token=${token}`);
  }, [token, teamId, clipId]);

  const clipStart = clip?.source_start_second ?? 0;
  const clipEnd = clip?.source_end_second ?? null;

  const handleLoaded = () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      video.currentTime = clipStart;
    } catch {
      requestAnimationFrame(() => {
        if (video.readyState >= 1) {
          video.currentTime = clipStart;
        }
      });
    }
  };

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    if (clipEnd != null && video.currentTime >= clipEnd) {
      video.pause();
      video.currentTime = clipEnd;
    } else if (video.currentTime < clipStart) {
      video.currentTime = clipStart;
    }
  };

  if (!teamId) return null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 px-6 py-10">
      <Link href="/dashboard" className="text-sm text-subtext hover:text-[#0e1a2e]">
        ← Back to dashboard
      </Link>
      {error ? (
        <p className="text-red-500">{error}</p>
      ) : clip ? (
        <section className="section-card space-y-4">
          <div>
            <h1 className="text-3xl font-semibold text-[#0e1a2e]">{clip.title}</h1>
            <p className="text-sm text-subtext">
              Published {new Date(clip.uploaded_at).toLocaleString()}
            </p>
          </div>
          {videoUrl && clip ? (
            <video
              key={`${clip.id}-${videoUrl}`}
              ref={videoRef}
              controls
              src={videoUrl}
              preload="auto"
              onLoadedMetadata={handleLoaded}
              onLoadedData={handleLoaded}
              onTimeUpdate={handleTimeUpdate}
              className="w-full rounded-xl border border-stroke"
            />
          ) : (
            <p className="text-sm text-red-500">Video preview failed to load.</p>
          )}
          {clip.notes && <p className="text-subtext">{clip.notes}</p>}
        </section>
      ) : (
        <p>Loading clip…</p>
      )}
    </main>
  );
}
