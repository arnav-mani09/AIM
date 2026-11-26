"use client";

import { FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import {
  ClipRecord,
  GameRecord,
  GameUploadRecord,
  canManageRoster,
  createGame,
  createInvite,
  createTeam,
  deleteClip,
  deleteGameFilm,
  fetchGameFilm,
  fetchGames,
  fetchTeamClips,
  fetchTeams,
  joinTeam,
  TeamInvite,
  TeamMembership,
  abortFilmUpload,
  importGameFilm,
} from "@/lib/teamApi";
import { formatLocalDateTime } from "@/lib/dateTime";
import { FilmUploadError, FilmUploadSession, uploadFilm } from "@/lib/filmUpload";
import ChatPanel from "@/components/ChatPanel";
import { SeasonView } from "@/components/SeasonView";
import { ScoutingView } from "@/components/ScoutingView";
import FilmLibrary from "@/components/FilmLibrary";
import RosterPanel from "@/components/RosterPanel";
import { validateFilmFile, validateFilmLink } from "@/lib/filmIntake";
import { useFilmCapabilities } from "@/lib/useFilmCapabilities";

const formatGigabytes = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(2)} GB`;

const PAGE_HEADINGS: Record<string, { title: string; description: string }> = {
  film: { title: "Game film", description: "Less time moving files. More time moving your team forward." },
  season: { title: "Season overview", description: "The bigger picture, built from your team's game film." },
  scouting: { title: "Scouting", description: "Turn game film into a clearer plan for the next matchup." },
  games: { title: "Games", description: "Keep your schedule, game film, and breakdowns connected." },
  chat: { title: "Ask AIM", description: "Find answers in your team's available game data." },
  teams: { title: "Team workspace", description: "Your people, permissions, and shared game library." },
};

// useSearchParams needs a Suspense boundary for the page to prerender.
const JERSEY_COLORS = [
  { value: "white", label: "White" },
  { value: "black", label: "Black" },
  { value: "gray", label: "Gray" },
  { value: "navy", label: "Navy" },
  { value: "light blue", label: "Light blue" },
  { value: "royal blue", label: "Royal blue" },
  { value: "red", label: "Red" },
  { value: "maroon", label: "Maroon" },
  { value: "green", label: "Green" },
  { value: "gold", label: "Gold / yellow" },
  { value: "orange", label: "Orange" },
  { value: "purple", label: "Purple" },
];

export default function DashboardPage() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}

function Dashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") ?? "film";
  const activeTab = Object.hasOwn(PAGE_HEADINGS, requestedTab) ? requestedTab : "film";
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [teams, setTeams] = useState<TeamMembership[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(true);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [teamCode, setTeamCode] = useState("");
  const [teamMessage, setTeamMessage] = useState("");
  const [createForm, setCreateForm] = useState({ name: "", level: "", season: "" });
  const [createStatus, setCreateStatus] = useState<"idle" | "loading">("idle");
  const [inviteStatus, setInviteStatus] = useState<"idle" | "loading">("idle");
  const [inviteResult, setInviteResult] = useState<TeamInvite | null>(null);
  const [inviteTeamId, setInviteTeamId] = useState<number | "">("");
  const [clipList, setClipList] = useState<ClipRecord[]>([]);
  const [clipLoading, setClipLoading] = useState(false);
  const [clipError, setClipError] = useState<string | null>(null);
  const [filmTeamId, setFilmTeamId] = useState<number | "">("");
  const [filmList, setFilmList] = useState<GameUploadRecord[]>([]);
  const [filmListTeamId, setFilmListTeamId] = useState<number | "">("");
  const [filmLoading, setFilmLoading] = useState(false);
  const [filmError, setFilmError] = useState<string | null>(null);
  const [filmStatus, setFilmStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [filmFeedback, setFilmFeedback] = useState("");
  const [uploadSelection, setUploadSelection] = useState<{ teamId: number | ""; method: "link" | "file" }>({ teamId: "", method: "file" });
  const filmIntake = useFilmCapabilities(authToken, filmTeamId);
  const linkImportEnabled = filmIntake.capabilities?.link_import_enabled === true;
  const uploadMethod = uploadSelection.teamId === filmTeamId && uploadSelection.method === "link" && linkImportEnabled ? "link" : "file";
  const [filmRefreshTick, setFilmRefreshTick] = useState(0);
  const filmRequestVersion = useRef(0);
  const filmSubmitLock = useRef(false);
  const [filmProgress, setFilmProgress] = useState<{ uploaded: number; total: number } | null>(null);
  // Kept after a failed or paused upload so Resume only sends the missing parts.
  const [pendingFilm, setPendingFilm] = useState<{
    file: File;
    title: string;
    notes: string | null;
    teamId: number;
    valleyJersey: string | null;
    opponentJersey: string | null;
    session: FilmUploadSession | null;
  } | null>(null);
  const filmAbortRef = useRef<AbortController | null>(null);
  const [gamesList, setGamesList] = useState<GameRecord[]>([]);
  const [gamesLoading, setGamesLoading] = useState(false);
  const [gamesError, setGamesError] = useState<string | null>(null);
  const [newGameForm, setNewGameForm] = useState({ matchup: "", scheduledAt: "", location: "" });
  const [newGameStatus, setNewGameStatus] = useState<"idle" | "loading">("idle");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const token = window.localStorage.getItem("aim_access_token");
    if (!token) {
      router.push("/auth/login");
      return;
    }
    setAuthToken(token);
    try {
      const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
      setCurrentUserId(payload?.sub ? Number(payload.sub) : null);
    } catch {
      setCurrentUserId(null);
    }
    fetchTeams(token)
      .then((data) => {
        setTeams(data);
        setTeamsError(null);
        if (data.length > 0 && filmTeamId === "") {
          setFilmTeamId(data[0].team.id);
        }
      })
      .catch((error) => setTeamsError(error instanceof Error ? error.message : "Failed to load teams"))
      .finally(() => setTeamsLoading(false));
  }, [filmTeamId, router]);

  useEffect(() => {
    const version = ++filmRequestVersion.current;
    if (!authToken || filmTeamId === "") {
      setFilmList([]);
      setClipList([]);
      return;
    }
    setFilmLoading(true);
    setClipLoading(true);
    Promise.all([fetchGameFilm(authToken, filmTeamId), fetchTeamClips(authToken, filmTeamId)])
      .then(([uploads, clips]) => {
        if (version !== filmRequestVersion.current) return;
        setFilmList(uploads);
        setFilmListTeamId(filmTeamId);
        setFilmError(null);
        setClipList(clips);
        setClipError(null);
      })
      .catch((error) => {
        if (version !== filmRequestVersion.current) return;
        const message = error instanceof Error ? error.message : "Unable to load film";
        setFilmError(message);
        setClipError(message);
      })
      .finally(() => {
        if (version !== filmRequestVersion.current) return;
        setFilmLoading(false);
        setClipLoading(false);
      });
    return () => { filmRequestVersion.current += 1; };
  }, [authToken, filmTeamId, filmRefreshTick]);

  const filmsAwaitingServer = filmList.some((film) => ["importing", "processing", "pending"].includes(film.status));
  useEffect(() => {
    if (!authToken || filmTeamId === "" || !filmsAwaitingServer) return;
    const timer = window.setInterval(() => setFilmRefreshTick((value) => value + 1), 8000);
    return () => window.clearInterval(timer);
  }, [authToken, filmTeamId, filmsAwaitingServer]);

  useEffect(() => {
    if (!authToken || filmTeamId === "") {
      setGamesList([]);
      return;
    }
    setGamesLoading(true);
    fetchGames(authToken, filmTeamId)
      .then((data) => {
        setGamesList(data);
        setGamesError(null);
      })
      .catch((error) => setGamesError(error instanceof Error ? error.message : "Unable to load games"))
      .finally(() => setGamesLoading(false));
  }, [authToken, filmTeamId]);

  const handleCreateGame = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken || filmTeamId === "" || !newGameForm.matchup || !newGameForm.scheduledAt) return;
    setNewGameStatus("loading");
    try {
      const game = await createGame(authToken, filmTeamId, {
        matchup: newGameForm.matchup,
        scheduled_at: new Date(newGameForm.scheduledAt).toISOString(),
        location: newGameForm.location || undefined,
      });
      setGamesList((prev) => [game, ...prev]);
      setNewGameForm({ matchup: "", scheduledAt: "", location: "" });
    } catch (error) {
      setGamesError(error instanceof Error ? error.message : "Failed to create game");
    } finally {
      setNewGameStatus("idle");
    }
  };

  const coachTeams = useMemo(
    () => teams.filter((membership) => membership.role === "coach" || membership.role === "admin"),
    [teams]
  );

  useEffect(() => {
    if (filmStatus !== "loading") return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [filmStatus]);

  const runFilmUpload = async (job: NonNullable<typeof pendingFilm>): Promise<boolean> => {
    if (!authToken || filmSubmitLock.current) return false;
    filmSubmitLock.current = true;
    const controller = new AbortController();
    filmAbortRef.current = controller;
    setPendingFilm(job);
    setFilmStatus("loading");
    setFilmFeedback("");
    try {
      const upload = await uploadFilm({
        token: authToken,
        teamId: job.teamId,
        file: job.file,
        title: job.title,
        notes: job.notes,
        valleyJersey: job.valleyJersey,
        opponentJersey: job.opponentJersey,
        resume: job.session,
        signal: controller.signal,
        onSession: (session) => setPendingFilm((prev) => (prev ? { ...prev, session } : prev)),
        onProgress: (uploaded, total) => setFilmProgress({ uploaded, total }),
      });
      setFilmList((prev) => [upload, ...(filmListTeamId === job.teamId ? prev : []).filter((item) => item.id !== upload.id)]);
      setFilmListTeamId(job.teamId);
      setFilmRefreshTick((value) => value + 1);
      setPendingFilm(null);
      setFilmProgress(null);
      setFilmStatus("success");
      setFilmFeedback("Film uploaded. Processing has started.");
      return true;
    } catch (error) {
      const session = error instanceof FilmUploadError ? error.session : null;
      setPendingFilm((prev) => (prev ? { ...prev, session: session ?? prev.session } : prev));
      setFilmStatus("error");
      setFilmFeedback(
        `${error instanceof Error ? error.message : "Upload failed"} Resume to continue from where it stopped.`
      );
      return false;
    } finally {
      filmAbortRef.current = null;
      filmSubmitLock.current = false;
    }
  };

  const handleFilmUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken || filmTeamId === "") {
      setFilmStatus("error");
      setFilmFeedback(teams.length === 0 ? "Create a team in the Teams tab first." : "Select a team.");
      return;
    }
    const formElement = event.currentTarget;
    const formData = new FormData(formElement);
    if (filmSubmitLock.current || pendingFilm) return;
    const title = String(formData.get("title") ?? "").trim();
    if (!title) {
      setFilmStatus("error");
      setFilmFeedback("Give this game a title so your staff can find it later.");
      return;
    }
    if (uploadMethod === "link") {
      if (!linkImportEnabled) {
        setFilmStatus("error");
        setFilmFeedback("Link import is not available. Upload a video file or retry the availability check.");
        return;
      }
      const sourceUrl = String(formData.get("source_url") ?? "").trim();
      const problem = validateFilmLink(sourceUrl);
      if (problem) {
        setFilmStatus("error");
        setFilmFeedback(problem);
        return;
      }
      filmSubmitLock.current = true;
      setFilmStatus("loading");
      setFilmFeedback("");
      try {
        const upload = await importGameFilm(authToken, filmTeamId, {
          title, source_url: sourceUrl,
          notes: String(formData.get("notes") ?? "").trim() || null,
          valley_jersey: String(formData.get("valley_jersey") ?? "") || null,
          opponent_jersey: String(formData.get("opponent_jersey") ?? "") || null,
        });
        setFilmList((prev) => [upload, ...(filmListTeamId === filmTeamId ? prev : []).filter((item) => item.id !== upload.id)]);
        setFilmListTeamId(filmTeamId);
        setFilmRefreshTick((value) => value + 1);
        setFilmStatus("success");
        setFilmFeedback("Import queued. You can leave this page; AIM will transfer the video and prepare it in the background.");
        if (formElement.isConnected) formElement.reset();
      } catch (error) {
        setFilmStatus("error");
        setFilmRefreshTick((value) => value + 1);
        setFilmFeedback(error instanceof Error && !(error instanceof TypeError) ? error.message : "Could not confirm the import. Refresh the library before trying again.");
      } finally {
        filmSubmitLock.current = false;
      }
      return;
    }
    const fileInput = formElement.querySelector('input[name="file"]') as HTMLInputElement | null;
    const file = fileInput?.files?.[0] ?? null;
    if (!file) {
      setFilmStatus("error");
      setFilmFeedback("Pick a file to upload.");
      return;
    }
    const problem = validateFilmFile(file);
    if (problem) {
      setFilmStatus("error");
      setFilmFeedback(problem);
      return;
    }
    setFilmProgress({ uploaded: 0, total: file.size });
    const uploaded = await runFilmUpload({
      file,
      title,
      notes: (formData.get("notes") as string | null) || null,
      teamId: filmTeamId,
      valleyJersey: (formData.get("valley_jersey") as string | null) || null,
      opponentJersey: (formData.get("opponent_jersey") as string | null) || null,
      session: null,
    });
    if (uploaded && formElement.isConnected) formElement.reset();
  };

  const handlePauseFilmUpload = () => filmAbortRef.current?.abort();

  const handleCancelFilmUpload = async () => {
    const job = pendingFilm;
    setPendingFilm(null);
    setFilmProgress(null);
    setFilmStatus("idle");
    setFilmFeedback("");
    if (authToken && job?.session) {
      await abortFilmUpload(authToken, job.teamId, job.session.uploadId).catch(() => {
        /* the server cleans up abandoned uploads when the film is deleted */
      });
      setFilmList((prev) => prev.filter((item) => item.id !== job.session?.uploadId));
    }
  };

  const handleTeamJoin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken) {
      router.push("/auth/login");
      return;
    }
    try {
      const membership = await joinTeam(authToken, teamCode);
      setTeams((prev) => {
        const exists = prev.find((item) => item.id === membership.id);
        if (exists) {
          return prev;
        }
        return [membership, ...prev];
      });
      setTeamMessage(`Joined ${membership.team.name} as ${membership.role}.`);
      setTeamCode("");
    } catch (error) {
      setTeamMessage(error instanceof Error ? error.message : "Unable to join team");
    }
  };

  const handleCreateTeam = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken) {
      router.push("/auth/login");
      return;
    }
    setCreateStatus("loading");
    try {
      const membership = await createTeam(authToken, {
        name: createForm.name,
        level: createForm.level || undefined,
        season_label: createForm.season || undefined,
      });
      setTeams((prev) => [membership, ...prev]);
      setCreateForm({ name: "", level: "", season: "" });
    } catch (error) {
      setTeamsError(error instanceof Error ? error.message : "Unable to create team");
    } finally {
      setCreateStatus("idle");
    }
  };

  const handleCreateInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken || inviteTeamId === "") {
      return;
    }
    setInviteStatus("loading");
    const formData = new FormData(event.currentTarget);
    const expires = formData.get("expires")?.toString();
    const maxUsesRaw = formData.get("maxUses")?.toString();
    try {
      const invite = await createInvite(authToken, Number(inviteTeamId), {
        expires_in_hours: expires ? Number(expires) : undefined,
        max_uses: maxUsesRaw ? Number(maxUsesRaw) : undefined,
      });
      setInviteResult(invite);
    } catch (error) {
      setInviteResult(null);
      setTeamMessage(error instanceof Error ? error.message : "Failed to create invite");
    } finally {
      setInviteStatus("idle");
    }
  };

  const handleDeleteUpload = async (uploadId: number) => {
    if (!authToken || filmTeamId === "") return;
    if (!window.confirm("Remove this film from the library?")) {
      return;
    }
    try {
      await deleteGameFilm(authToken, filmTeamId, uploadId);
      setFilmList((prev) => prev.filter((upload) => upload.id !== uploadId));
    } catch (error) {
      setFilmStatus("error");
      setFilmFeedback(error instanceof Error ? error.message : "Failed to delete film");
    }
  };

  const handleDeleteClip = async (clipId: number) => {
    if (!authToken || filmTeamId === "") return;
    try {
      await deleteClip(authToken, filmTeamId, clipId);
      setClipList((prev) => prev.filter((clip) => clip.id !== clipId));
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to delete clip");
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="label-text">{teams.find((membership) => membership.team.id === filmTeamId)?.team.name ?? "Your workspace"}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">{PAGE_HEADINGS[activeTab].title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-subtext">{PAGE_HEADINGS[activeTab].description}</p>
        </div>
        {activeTab !== "film" && <Link href="/dashboard?tab=film#add-game" className="rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white">Add game film <span aria-hidden="true">＋</span></Link>}
      </header>

      {activeTab === "film" && (
        <>
          <section id="add-game" className="section-card scroll-mt-20" aria-labelledby="add-film-heading">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="add-film-heading" className="text-xl font-semibold tracking-tight text-ink">Add game film</h2>
                <p className="mt-1 text-sm leading-6 text-subtext">Bring the video. AIM handles the preparation. No box score needed.</p>
              </div>
              <span className="rounded-md bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-subtext">MP4 / MOV · Up to 5 GB</span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2" role="group" aria-label="Choose how to add film">
              {(["link", "file"] as const).map((method) => (
                <button key={method} type="button" aria-pressed={uploadMethod === method} aria-describedby={method === "link" ? "film-import-availability" : undefined} disabled={filmStatus === "loading" || pendingFilm !== null || (method === "link" && !linkImportEnabled)} onClick={() => {
                  setUploadSelection({ teamId: filmTeamId, method });
                  setFilmStatus("idle");
                  setFilmFeedback("");
                }} className={`flex items-center gap-3 rounded-xl border p-4 text-left transition-colors disabled:opacity-60 ${uploadMethod === method ? "border-accent bg-tint ring-1 ring-accent" : "border-stroke bg-white hover:bg-slate-50"}`}>
                  <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="shrink-0 text-accent">
                    {method === "link" ? <><path d="m10 13 4-4M8 15l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 3 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 1)" /></> : <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5" /></>}
                  </svg>
                  <span><span className="block text-sm font-semibold text-ink">{method === "link" ? "Import from a link" : "Upload from your device"}</span><span className="mt-1 block text-xs leading-5 text-subtext">{method === "link" ? (linkImportEnabled ? "Authorized direct video downloads" : "Available when link import is configured") : "Resumable uploads for large game files"}</span></span>
                </button>
              ))}
            </div>
            <div id="film-import-availability" className="mt-3 text-xs leading-5 text-subtext" role="status">
              {filmIntake.loading ? "Checking link-import availability…" : filmIntake.error ? (
                <span>{filmIntake.error}{" "}<button type="button" onClick={filmIntake.retry} className="font-semibold underline">Retry check</button></span>
              ) : filmIntake.capabilities ? filmIntake.capabilities.link_import_message : "Select a team to check link-import availability. File upload remains available."}
            </div>
            <form onSubmit={handleFilmUpload} className="mt-5 space-y-5" aria-busy={filmStatus === "loading"}>
              <fieldset disabled={filmStatus === "loading" || pendingFilm !== null} className="grid min-w-0 gap-4 md:grid-cols-2 disabled:opacity-70">
              <label className="flex flex-col gap-2 text-sm">
                Team
                <select
                  value={filmTeamId}
                  onChange={(event) =>
                    setFilmTeamId(event.target.value === "" ? "" : Number(event.target.value))
                  }
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                >
                  <option value="">Select a team</option>
                  {teams.map((membership) => (
                    <option key={membership.team.id} value={membership.team.id}>
                      {membership.team.name}
                    </option>
                  ))}
                </select>
                {!teamsLoading && teams.length === 0 && (
                  <span className="text-xs text-subtext">
                    You&apos;re not on a team yet.{" "}
                    <Link href="/dashboard?tab=teams" className="underline">
                      Create one in Teams
                    </Link>{" "}
                    first.
                  </span>
                )}
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Film title
                <input
                  type="text"
                  name="title"
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="e.g. Valley vs Central · Nov 13"
                  maxLength={200}
                  required
                />
              </label>
              {uploadMethod === "link" ? (
                <label className="flex min-w-0 flex-col gap-2 text-sm md:col-span-2">
                  Video download link
                  <input type="url" name="source_url" autoComplete="off" spellCheck={false} required placeholder="https://… / your authorized video download link" aria-describedby="film-link-help" className="w-full min-w-0 rounded-xl border border-stroke px-3 py-3 text-ink" />
                  <span id="film-link-help" className="text-xs leading-5 text-subtext">Paste an authorized direct video download link or the video link from a Hudl download-ready email. The source must be enabled by your AIM administrator. Hudl watch pages, stats links, and links requiring sign-in will not work. Never paste a password.</span>
                </label>
              ) : (
                <label className="flex min-w-0 flex-col gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm md:col-span-2">
                  <span className="font-semibold text-ink">Choose the original game video</span>
                  <input type="file" name="file" accept="video/mp4,video/quicktime,.mp4,.mov" className="w-full min-w-0 text-sm text-subtext file:mr-3 file:rounded-lg file:border-0 file:bg-white file:px-3 file:py-2 file:font-semibold file:text-ink" required />
                  <span className="text-xs leading-5 text-subtext">Keep this page open until the upload completes. You can pause and resume while this page stays open; processing continues on AIM afterward.</span>
                </label>
              )}
              <details className="rounded-xl border border-stroke px-4 py-3 md:col-span-2">
                <summary className="cursor-pointer text-sm font-medium text-ink">Optional game details <span className="font-normal text-subtext">· jerseys & notes</span></summary>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm md:col-span-2">
                Notes <span className="sr-only">(optional)</span>
                <textarea
                  name="notes"
                  rows={2}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="Optional · quarter, camera angle, or anything your staff should know"
                />
              </label>
              {/* Jersey colors tell AIM which team is yours. Values match the worker's color names. */}
              {(["valley_jersey", "opponent_jersey"] as const).map((name) => (
                <label key={name} className="flex flex-col gap-2 text-sm">
                  {name === "valley_jersey" ? "Your team's jersey color" : "Other team's jersey color"}
                  <select name={name} defaultValue="" className="rounded-xl border border-stroke px-3 py-2 text-ink">
                    <option value="">Not sure</option>
                    {JERSEY_COLORS.map((color) => (
                      <option key={color.value} value={color.value}>
                        {color.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
                </div>
              </details>
              </fieldset>
              <div className="flex flex-wrap items-center gap-3 border-t border-stroke pt-4">
                <button
                  type="submit"
                  className="rounded-2xl bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
                  disabled={filmStatus === "loading" || pendingFilm !== null || teamsLoading || filmTeamId === ""}
                >
                  {filmStatus === "loading" ? uploadMethod === "link" ? "Starting import…" : "Uploading video…" : uploadMethod === "link" ? "Import game film" : "Upload game film"}
                </button>
                {filmStatus === "loading" && pendingFilm && (
                  <button
                    type="button"
                    onClick={handlePauseFilmUpload}
                    className="rounded-2xl border border-stroke px-4 py-2 font-semibold text-ink"
                  >
                    Pause
                  </button>
                )}
                {filmStatus !== "loading" && pendingFilm && (
                  <>
                    <button
                      type="button"
                      onClick={() => runFilmUpload(pendingFilm)}
                      className="rounded-2xl bg-ink px-4 py-2 font-semibold text-white"
                    >
                      Resume upload
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelFilmUpload}
                      className="rounded-2xl border border-stroke px-4 py-2 font-semibold text-ink"
                    >
                      Cancel
                    </button>
                  </>
                )}
                {filmFeedback && (
                  <p role={filmStatus === "error" ? "alert" : "status"} className={`max-w-xl text-sm leading-6 ${filmStatus === "error" ? "text-red-700" : "text-emerald-700"}`}>
                    {filmFeedback}
                  </p>
                )}
              </div>
              <p className="text-xs leading-5 text-subtext">Only add film you are authorized to share. Import availability depends on your team&apos;s configuration and the download link&apos;s permissions.</p>
              {filmProgress && (
                <div className="md:col-span-2 space-y-1">
                  <div
                    className="h-2 w-full overflow-hidden rounded-full bg-stroke"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.floor((filmProgress.uploaded / filmProgress.total) * 100)}
                  >
                    <div
                      className="h-full bg-ink transition-[width]"
                      style={{ width: `${(filmProgress.uploaded / filmProgress.total) * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-subtext">
                    {Math.floor((filmProgress.uploaded / filmProgress.total) * 100)}% ·{" "}
                    {formatGigabytes(filmProgress.uploaded)} of {formatGigabytes(filmProgress.total)}
                    {pendingFilm ? ` · ${pendingFilm.file.name}` : ""}
                  </p>
                </div>
              )}
            </form>

          </section>

          <FilmLibrary
            films={filmListTeamId === filmTeamId ? filmList : []}
            teamId={filmTeamId}
            loading={filmLoading}
            error={filmError}
            onDelete={handleDeleteUpload}
            onRefresh={() => setFilmRefreshTick((value) => value + 1)}
          />

          <section className="section-card">
            <h2 className="text-2xl font-semibold text-ink">Published clips</h2>
            <p className="mt-2 text-sm text-subtext">
              Clips appear here after you trim segments from a full game upload. Use the film library above to
              open the editor and publish highlights.
            </p>
            <div className="mt-4 rounded-2xl border border-stroke p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-ink">Recent clips</p>
                {filmTeamId && (
                  <p className="text-xs text-subtext">
                    Showing clips for{" "}
                    {teams.find((membership) => membership.team.id === filmTeamId)?.team.name ?? ""}
                  </p>
                )}
              </div>
              {filmTeamId === "" ? (
                <p className="mt-2 text-sm text-subtext">Select a team to view clips.</p>
              ) : clipLoading ? (
                <p className="mt-2 text-sm text-subtext">Loading clips…</p>
              ) : clipError ? (
                <p className="mt-2 text-sm text-red-500">{clipError}</p>
              ) : clipList.length === 0 ? (
                <p className="mt-2 text-sm text-subtext">No clips published yet.</p>
              ) : (
                <ul className="mt-4 space-y-3 text-sm">
              {clipList.map((clip) => (
                <li key={clip.id} className="rounded-2xl border border-stroke p-4">
                  <div className="flex items-center justify-between gap-3">
                    <Link
                      href={`/dashboard/clips/${clip.id}?team=${filmTeamId}`}
                      className="flex flex-col"
                    >
                      <p className="font-semibold text-ink">{clip.title}</p>
                      <p className="text-xs text-subtext">
                        Uploaded {formatLocalDateTime(clip.uploaded_at)}
                        {clip.game_matchup && (
                          <span className="ml-2 text-xs text-subtext">
                            • {clip.game_matchup}
                            {clip.game_scheduled_at
                              ? ` (${formatLocalDateTime(clip.game_scheduled_at)})`
                              : ""}
                          </span>
                        )}
                      </p>
                    </Link>
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-tint px-3 py-1 text-xs text-ink">
                            {clip.status}
                          </span>
                          {clip.uploaded_by_id && clip.uploaded_by_id === currentUserId && (
                            <button
                              onClick={() => handleDeleteClip(clip.id)}
                              className="text-xs text-red-500 hover:underline"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                      </div>
                      {clip.notes && <p className="mt-2 text-subtext">{clip.notes}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </>
      )}

      {activeTab === "games" && (
        <section className="section-card">
          <h2 className="text-2xl font-semibold text-ink">Games</h2>
          <p className="mt-2 text-sm text-subtext">
            Create a game, then break it down: log shot locations while reviewing film to build a live team
            shot chart.
          </p>

          <form onSubmit={handleCreateGame} className="mt-6 grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm">
              Team
              <select
                value={filmTeamId}
                onChange={(event) => setFilmTeamId(event.target.value === "" ? "" : Number(event.target.value))}
                className="rounded-xl border border-stroke px-3 py-2 text-ink"
              >
                <option value="">Select a team</option>
                {teams.map((membership) => (
                  <option key={membership.team.id} value={membership.team.id}>
                    {membership.team.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Matchup
              <input
                type="text"
                value={newGameForm.matchup}
                onChange={(event) => setNewGameForm((prev) => ({ ...prev, matchup: event.target.value }))}
                className="rounded-xl border border-stroke px-3 py-2 text-ink"
                placeholder="Valley vs Central"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Date & time
              <input
                type="datetime-local"
                value={newGameForm.scheduledAt}
                onChange={(event) => setNewGameForm((prev) => ({ ...prev, scheduledAt: event.target.value }))}
                className="rounded-xl border border-stroke px-3 py-2 text-ink"
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              Location
              <input
                type="text"
                value={newGameForm.location}
                onChange={(event) => setNewGameForm((prev) => ({ ...prev, location: event.target.value }))}
                className="rounded-xl border border-stroke px-3 py-2 text-ink"
                placeholder="Home gym"
              />
            </label>
            <div className="md:col-span-2">
              <button
                type="submit"
                className="rounded-2xl bg-accent px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={filmTeamId === "" || newGameStatus === "loading"}
              >
                {newGameStatus === "loading" ? "Creating…" : "Create game"}
              </button>
            </div>
          </form>

          <div className="mt-6 rounded-2xl border border-stroke p-4">
            <p className="text-sm font-semibold text-ink">Team games</p>
            {filmTeamId === "" ? (
              <p className="mt-2 text-sm text-subtext">Select a team to view games.</p>
            ) : gamesLoading ? (
              <p className="mt-2 text-sm text-subtext">Loading games…</p>
            ) : gamesError ? (
              <p className="mt-2 text-sm text-red-500">{gamesError}</p>
            ) : gamesList.length === 0 ? (
              <p className="mt-2 text-sm text-subtext">No games yet. Create one above.</p>
            ) : (
              <ul className="mt-4 space-y-3 text-sm">
                {gamesList.map((game) => (
                  <li key={game.id} className="flex items-center justify-between gap-3 rounded-2xl border border-stroke p-4">
                    <div>
                      <p className="font-semibold text-ink">{game.matchup}</p>
                      <p className="text-xs text-subtext">{formatLocalDateTime(game.scheduled_at)}</p>
                    </div>
                    <Link
                      href={`/dashboard/games/${game.id}/breakdown?team=${filmTeamId}`}
                      className="rounded-full bg-accent px-4 py-2 text-xs font-semibold text-white"
                    >
                      Breakdown →
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {activeTab === "season" && (
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-ink">Season</h2>
              <p className="mt-1 text-sm text-subtext">
                Built from your own game film. Scores are drafts until you review each game.
              </p>
            </div>
            <TeamPicker teams={teams} value={filmTeamId} onChange={setFilmTeamId} />
          </div>
          {teamsLoading ? (
            <p className="text-sm text-subtext">Loading teams…</p>
          ) : !authToken || filmTeamId === "" ? (
            <p className="text-sm text-subtext">
              You&apos;re not on a team yet.{" "}
              <Link href="/dashboard?tab=teams" className="underline">
                Create one in Teams
              </Link>{" "}
              first.
            </p>
          ) : (
            <SeasonView key={filmTeamId} token={authToken} teamId={filmTeamId} />
          )}
        </section>
      )}

      {activeTab === "scouting" && (
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-ink">Scouting</h2>
              <p className="mt-1 text-sm text-subtext">Where a team shoots from and how well, built from your film.</p>
            </div>
            <TeamPicker teams={teams} value={filmTeamId} onChange={setFilmTeamId} />
          </div>
          {teamsLoading ? (
            <p className="text-sm text-subtext">Loading teams…</p>
          ) : !authToken || filmTeamId === "" ? (
            <p className="text-sm text-subtext">You&apos;re not on a team yet. Create one in Team Spaces first.</p>
          ) : (
            <ScoutingView key={filmTeamId} token={authToken} teamId={filmTeamId} />
          )}
        </section>
      )}

      {activeTab === "chat" && (
        <section className="flex flex-col gap-4">
          <TeamPicker teams={teams} value={filmTeamId} onChange={setFilmTeamId} />
          {teamsLoading ? (
            <p className="text-sm text-subtext">Loading teams…</p>
          ) : filmTeamId === "" ? (
            <p className="text-sm text-subtext">
              You&apos;re not on a team yet.{" "}
              <Link href="/dashboard?tab=teams" className="underline">
                Create one in Teams
              </Link>{" "}
              first.
            </p>
          ) : (
            <ChatPanel key={filmTeamId} token={authToken} teamId={filmTeamId} />
          )}
        </section>
      )}

      {activeTab === "teams" && (
        <>
        <section className="section-card space-y-6">
          <div>
            <h3 className="text-xl font-semibold text-ink">Team spaces</h3>
            <p className="mt-2 text-sm text-subtext">
              Coaches create codes so players, staff, and recruiters can collaborate securely.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Your memberships</p>
              {teamsLoading ? (
                <p className="mt-2 text-sm text-subtext">Loading teams…</p>
              ) : teamsError ? (
                <p className="mt-2 text-sm text-red-500">{teamsError}</p>
              ) : teams.length === 0 ? (
                <p className="mt-2 text-sm text-subtext">No teams yet. Create one or join with a code.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {teams.map((membership) => (
                    <li key={membership.id} className="rounded-2xl border border-stroke p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-lg font-semibold text-ink">{membership.team.name}</p>
                          <p className="text-sm text-subtext">
                            {membership.team.level ?? "Program"} • {membership.team.season_label ?? "Season TBD"}
                          </p>
                        </div>
                        <span className="rounded-full border border-stroke px-3 py-1 text-xs uppercase tracking-widest text-subtext">
                          {membership.role}
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-subtext">
                        Joined {new Date(membership.joined_at).toLocaleDateString()}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <form
              onSubmit={handleCreateTeam}
              className="flex flex-col gap-3 rounded-2xl border border-dashed border-stroke p-4 text-sm"
            >
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Create team</p>
              <label className="flex flex-col gap-1">
                Team name
                <input
                  type="text"
                  value={createForm.name}
                  onChange={(event) => setCreateForm((prev) => ({ ...prev, name: event.target.value }))}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                Level / squad
                <input
                  type="text"
                  value={createForm.level}
                  onChange={(event) => setCreateForm((prev) => ({ ...prev, level: event.target.value }))}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="Varsity, JV, etc."
                />
              </label>
              <label className="flex flex-col gap-1">
                Season label
                <input
                  type="text"
                  value={createForm.season}
                  onChange={(event) => setCreateForm((prev) => ({ ...prev, season: event.target.value }))}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="2024-25"
                />
              </label>
              <button
                type="submit"
                className="rounded-2xl bg-accent px-4 py-2 font-semibold text-white"
                disabled={createStatus === "loading"}
              >
                {createStatus === "loading" ? "Creating…" : "Create team"}
              </button>
            </form>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <form onSubmit={handleTeamJoin} className="flex flex-col gap-3 rounded-2xl border border-stroke p-4 text-sm">
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Join via code</p>
              <label className="flex flex-col gap-1">
                Enter invite code
                <input
                  type="text"
                  value={teamCode}
                  onChange={(event) => setTeamCode(event.target.value)}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                  placeholder="e.g., VALLEY-BOYS-2025"
                  required
                />
              </label>
              <button
                type="submit"
                className="w-fit rounded-2xl border border-stroke px-4 py-2 font-semibold text-ink"
              >
                Request access
              </button>
              {teamMessage && <p className="text-xs text-green-600">{teamMessage}</p>}
            </form>

            <form onSubmit={handleCreateInvite} className="flex flex-col gap-3 rounded-2xl border border-stroke p-4 text-sm">
              <p className="text-xs uppercase tracking-[0.3em] text-subtext">Generate invite</p>
              <label className="flex flex-col gap-1">
                Select team
                <select
                  value={inviteTeamId}
                  onChange={(event) =>
                    setInviteTeamId(event.target.value === "" ? "" : Number(event.target.value))
                  }
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                >
                  <option value="">Choose a team</option>
                  {coachTeams.map((membership) => (
                    <option key={membership.team.id} value={membership.team.id}>
                      {membership.team.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                Expires in hours
                <input
                  name="expires"
                  type="number"
                  min={1}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                />
              </label>
              <label className="flex flex-col gap-1">
                Max uses
                <input
                  name="maxUses"
                  type="number"
                  min={1}
                  className="rounded-xl border border-stroke px-3 py-2 text-ink"
                />
              </label>
              <button
                type="submit"
                className="rounded-2xl bg-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={inviteTeamId === "" || inviteStatus === "loading"}
              >
                {inviteStatus === "loading" ? "Creating…" : "Generate code"}
              </button>
              {inviteResult && (
                <div className="rounded-xl bg-tint px-3 py-2 text-sm text-ink">
                  Share code <strong>{inviteResult.code}</strong> ({inviteResult.role})
                </div>
              )}
              {!inviteResult && inviteTeamId === "" && (
                <p className="text-xs text-subtext">Select a coach team to generate invites.</p>
              )}
            </form>
          </div>
        </section>
        <section className="section-card space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><h3 className="text-xl font-semibold text-ink">Team roster</h3>
              <p className="mt-1 text-sm text-subtext">Your players, in one place.</p>
            </div>
            <TeamPicker teams={teams} value={filmTeamId} onChange={setFilmTeamId} />
          </div>
          {teamsLoading ? <p className="text-sm text-subtext">Loading teams…</p> : teamsError ? (
            <p role="alert" className="text-sm text-red-700">{teamsError}</p>
          ) : authToken && teams.some((membership) => membership.team.id === filmTeamId) ? (
            <>
              <p className="text-sm font-semibold text-ink">{teams.find((membership) => membership.team.id === filmTeamId)?.team.name}</p>
              <RosterPanel key={`${filmTeamId}:${authToken}`} token={authToken} teamId={Number(filmTeamId)}
                canEdit={canManageRoster(teams.find((membership) => membership.team.id === filmTeamId))} />
            </>
          ) : <p className="text-sm text-subtext">Create or join a team to view its roster.</p>}
        </section>
        </>
      )}

    </main>
  );
}

function TeamPicker({
  teams,
  value,
  onChange,
}: {
  teams: TeamMembership[];
  value: number | "";
  onChange: (value: number | "") => void;
}) {
  if (teams.length < 2) return null;
  return (
    <label className="flex flex-col gap-2 text-sm md:w-72">
      Team
      <select
        value={value}
        onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))}
        className="rounded-xl border border-stroke px-3 py-2 text-ink"
      >
        {teams.map((membership) => (
          <option key={membership.team.id} value={membership.team.id}>
            {membership.team.name}
          </option>
        ))}
      </select>
    </label>
  );
}
