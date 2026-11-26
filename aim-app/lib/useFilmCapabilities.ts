"use client";

import { useEffect, useState } from "react";
import { fetchFilmIntakeCapabilities, FilmIntakeCapabilities } from "./teamApi";

export function useFilmCapabilities(token: string | null, teamId: number | "") {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    capabilities: FilmIntakeCapabilities | null;
    error: string | null;
  } | null>(null);
  const key = JSON.stringify([token, teamId, revision]);

  useEffect(() => {
    if (!token || teamId === "") return;
    let active = true;
    const controller = new AbortController();
    fetchFilmIntakeCapabilities(token, teamId, controller.signal)
      .then((capabilities) => {
        if (active) setResult({ key, capabilities, error: null });
      })
      .catch(() => {
        if (active) setResult({ key, capabilities: null, error: "Could not check link-import availability. You can still upload a video file." });
      });
    return () => { active = false; controller.abort(); };
  }, [token, teamId, key]);

  const current = result?.key === key ? result : null;
  return {
    capabilities: current?.capabilities ?? null,
    loading: Boolean(token && teamId !== "" && !current),
    error: current?.error ?? null,
    retry: () => setRevision((value) => value + 1),
  };
}
