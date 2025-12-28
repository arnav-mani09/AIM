"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import {
  ClipRecord,
  GameUploadRecord,
  createInvite,
  createTeam,
  deleteClip,
  deleteGameFilm,
  fetchGameFilm,
  fetchTeamClips,
  fetchTeams,
  joinTeam,
  TeamInvite,
  TeamMembership,
  uploadGameFilm,
} from "@/lib/teamApi";
import { formatLocalDateTime } from "@/lib/dateTime";

export default function DashboardPage() {
  const router = useRouter();
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
  const [filmLoading, setFilmLoading] = useState(false);
  const [filmError, setFilmError] = useState<string | null>(null);
  const [filmStatus, setFilmStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [filmFeedback, setFilmFeedback] = useState("");
  const [activeTab, setActiveTab] = useState<"film" | "chat" | "teams">("film");
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
    if (!authToken || filmTeamId === "") {
      setFilmList([]);
      setClipList([]);
      return;
    }
    setFilmLoading(true);
    setClipLoading(true);
    Promise.all([fetchGameFilm(authToken, filmTeamId), fetchTeamClips(authToken, filmTeamId)])
      .then(([uploads, clips]) => {
        setFilmList(uploads);
        setFilmError(null);
        setClipList(clips);
        setClipError(null);
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : "Unable to load film";
        setFilmError(message);
        setClipError(message);
      })
      .finally(() => {
        setFilmLoading(false);
        setClipLoading(false);
      });
  }, [authToken, filmTeamId]);

  const coachTeams = useMemo(
    () => teams.filter((membership) => membership.role === "coach" || membership.role === "admin"),
    [teams]
  );

  const handleFilmUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authToken || filmTeamId === "") {
      setFilmStatus("error");
      setFilmFeedback("Select a team.");
      return;
    }
    const formElement = event.currentTarget;
    const formData = new FormData(formElement);
    const fileInput = formElement.querySelector('input[name="file"]') as HTMLInputElement | null;
    const file = fileInput?.files?.[0] ?? null;
    if (!file) {
      setFilmStatus("error");
      setFilmFeedback("Pick a file to upload.");
      return;
    }
    setFilmStatus("loading");
    setFilmFeedback("");
    try {
      const upload = await uploadGameFilm(authToken, filmTeamId, formData);
      setFilmList((prev) => [upload, ...prev]);
      setFilmStatus("success");
      setFilmFeedback("Raw film uploaded. Processing queue will begin soon.");
    } catch (error) {
      setFilmStatus("error");
      setFilmFeedback(error instanceof Error ? error.message : "Upload failed");
    } finally {
      formElement.reset();
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

  const handleSignOut = () => {
    window.localStorage.removeItem("aim_access_token");
    router.push("/");
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-full border border-stroke text-[#0e1a2e]"
            aria-label="Open menu"
          >
            ☰
          </button>
          <div className="text-right">
            <p className="label-text">Workspace</p>
            <h1 className="mt-1 text-2xl font-semibold text-[#0e1a2e]">Your AIM operations center</h1>
          </div>
        </div>
        <p className="text-subtext">
          Upload film, collaborate in chat, review past insights, and manage teams—all powered by AIM.
        </p>
      </header>

      <nav className="flex flex-wrap gap-2 rounded-2xl border border-stroke bg-white p-2">
        {[
          { id: "film", label: "Film + Clips" },
          { id: "chat", label: "AI Chat" },
          { id: "teams", label: "Team Spaces" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${
              activeTab === tab.id ? "bg-[#0e1a2e] text-white" : "text-[#0e1a2e] hover:bg-[#ecf2fb]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "film" && (
        <>
          <section className="section-card">
            <h2 className="text-2xl font-semibold text-[#0e1a2e]">Full game film</h2>
            <p className="mt-2 text-sm text-subtext">
              Upload complete quarters or games. AIM will process them, then you can trim and share highlight clips.
            </p>
            <form onSubmit={handleFilmUpload} className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm">
                Team
                <select
                  value={filmTeamId}
                  onChange={(event) =>
                    setFilmTeamId(event.target.value === "" ? "" : Number(event.target.value))
                  }
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
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
                Film title
                <input
                  type="text"
                  name="title"
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  placeholder="Valley vs Central - Q1"
                  required
                />
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Select file
                <input
                  type="file"
                  name="file"
                  accept="video/mp4,video/quicktime"
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  required
                />
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Notes
                <textarea
                  name="notes"
                  rows={3}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  placeholder="Quarter, opponent, angle…"
                />
              </label>
              <div className="md:col-span-2 flex items-center gap-3">
                <button
                  type="submit"
                  className="rounded-2xl bg-[#0e1a2e] px-4 py-2 font-semibold text-white disabled:opacity-60"
                  disabled={filmStatus === "loading"}
                >
                  {filmStatus === "loading" ? "Uploading…" : "Upload raw film"}
                </button>
                {filmFeedback && (
                  <p className={`text-sm ${filmStatus === "error" ? "text-red-500" : "text-green-600"}`}>
                    {filmFeedback}
                  </p>
                )}
              </div>
            </form>

            <div className="mt-6 rounded-2xl border border-stroke p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-[#0e1a2e]">Film library</p>
                {filmTeamId && (
                  <p className="text-xs text-subtext">
                    Showing film for{" "}
                    {teams.find((membership) => membership.team.id === filmTeamId)?.team.name ?? ""}
                  </p>
                )}
              </div>
              {filmTeamId === "" ? (
                <p className="mt-2 text-sm text-subtext">Select a team to view uploads.</p>
              ) : filmLoading ? (
                <p className="mt-2 text-sm text-subtext">Loading film…</p>
              ) : filmError ? (
                <p className="mt-2 text-sm text-red-500">{filmError}</p>
              ) : filmList.length === 0 ? (
                <p className="mt-2 text-sm text-subtext">No film uploaded yet.</p>
              ) : (
                <ul className="mt-4 space-y-3 text-sm">
              {filmList.map((upload) => (
                <li key={upload.id} className="rounded-2xl border border-stroke p-4 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Link
                      href={`/dashboard/film/${upload.id}?team=${filmTeamId}`}
                      className="flex flex-col"
                    >
                      <p className="font-semibold text-[#0e1a2e]">{upload.title}</p>
                      <p className="text-xs text-subtext">
                        Uploaded {formatLocalDateTime(upload.uploaded_at)}
                        {upload.game_matchup && (
                          <span className="ml-2 text-xs text-subtext">
                            • {upload.game_matchup}
                            {upload.game_scheduled_at
                              ? ` (${formatLocalDateTime(upload.game_scheduled_at)})`
                              : ""}
                          </span>
                        )}
                      </p>
                    </Link>
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-[#ecf2fb] px-3 py-1 text-xs text-[#0e1a2e]">
                            {upload.status}
                          </span>
                          <button
                            onClick={() => handleDeleteUpload(upload.id)}
                            className="text-xs text-red-500 hover:underline"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                      {upload.notes && <p className="text-subtext">{upload.notes}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="section-card">
            <h2 className="text-2xl font-semibold text-[#0e1a2e]">Published clips</h2>
            <p className="mt-2 text-sm text-subtext">
              Clips appear here after you trim segments from a full game upload. Use the film library above to
              open the editor and publish highlights.
            </p>
            <div className="mt-4 rounded-2xl border border-stroke p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-[#0e1a2e]">Recent clips</p>
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
                      <p className="font-semibold text-[#0e1a2e]">{clip.title}</p>
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
                          <span className="rounded-full bg-[#ecf2fb] px-3 py-1 text-xs text-[#0e1a2e]">
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

      {activeTab === "chat" && (
        <section className="section-card grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-xl font-semibold text-[#0e1a2e]">AI chat</h3>
            <p className="mt-2 text-sm text-subtext">
              Ask about lineups, shooters, or scouting adjustments. Responses will use the latest stats feed.
            </p>
            <div className="mt-4 rounded-2xl border border-stroke p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-subtext">Chat thread</p>
              <div className="mt-3 flex flex-col gap-3 text-sm">
                <div className="rounded-2xl bg-[#ecf2fb] px-3 py-2 text-[#0e1a2e]">
                  Which player is most reliable in crunch time?
                </div>
                <div className="self-end rounded-2xl bg-accent px-3 py-2 text-white">
                  #24 Lane has 64% eFG in final 2 minutes. Feature him in ATO sets.
                </div>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xl font-semibold text-[#0e1a2e]">Past insights</h3>
            <ul className="mt-3 space-y-3 text-sm text-subtext">
              <li className="rounded-2xl border border-stroke p-4">
                <strong className="text-[#0e1a2e]">Valley vs Central</strong>
                <p>Possession split 64/36 with Lane flagged as premier shooter.</p>
              </li>
              <li className="rounded-2xl border border-stroke p-4">
                <strong className="text-[#0e1a2e]">Northside vs Westfield</strong>
                <p>Press break turnover issues for #12 Brooks—recommend extra reps.</p>
              </li>
            </ul>
          </div>
        </section>
      )}

      {activeTab === "teams" && (
        <section className="section-card space-y-6">
          <div>
            <h3 className="text-xl font-semibold text-[#0e1a2e]">Team spaces</h3>
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
                <p className="mt-2 text-sm text-subtext">No teams yet—create one or join with a code.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {teams.map((membership) => (
                    <li key={membership.id} className="rounded-2xl border border-stroke p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-lg font-semibold text-[#0e1a2e]">{membership.team.name}</p>
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
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                Level / squad
                <input
                  type="text"
                  value={createForm.level}
                  onChange={(event) => setCreateForm((prev) => ({ ...prev, level: event.target.value }))}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  placeholder="Varsity, JV, etc."
                />
              </label>
              <label className="flex flex-col gap-1">
                Season label
                <input
                  type="text"
                  value={createForm.season}
                  onChange={(event) => setCreateForm((prev) => ({ ...prev, season: event.target.value }))}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
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
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                  placeholder="e.g., VALLEY-BOYS-2025"
                  required
                />
              </label>
              <button
                type="submit"
                className="w-fit rounded-2xl border border-stroke px-4 py-2 font-semibold text-[#0e1a2e]"
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
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
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
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                />
              </label>
              <label className="flex flex-col gap-1">
                Max uses
                <input
                  name="maxUses"
                  type="number"
                  min={1}
                  className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]"
                />
              </label>
              <button
                type="submit"
                className="rounded-2xl bg-[#0e1a2e] px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={inviteTeamId === "" || inviteStatus === "loading"}
              >
                {inviteStatus === "loading" ? "Creating…" : "Generate code"}
              </button>
              {inviteResult && (
                <div className="rounded-xl bg-[#ecf2fb] px-3 py-2 text-sm text-[#0e1a2e]">
                  Share code <strong>{inviteResult.code}</strong> ({inviteResult.role})
                </div>
              )}
              {!inviteResult && inviteTeamId === "" && (
                <p className="text-xs text-subtext">Select a coach team to generate invites.</p>
              )}
            </form>
          </div>
        </section>
      )}

      {sidebarOpen && (
        <div className="fixed inset-0 z-50 flex">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close menu"
          />
          <aside className="relative z-10 h-full w-72 bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-[#0e1a2e]">AIM Menu</p>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="rounded-full border border-stroke px-3 py-1 text-xs text-[#0e1a2e]"
              >
                Close
              </button>
            </div>
            <nav className="mt-6 flex flex-col gap-3 text-sm">
              <button onClick={handleSignOut} className="rounded-xl border border-stroke px-3 py-2 text-left">
                Sign out
              </button>
              <a href="#" className="rounded-xl border border-stroke px-3 py-2">
                License
              </a>
              <a href="mailto:support@aimsports.com" className="rounded-xl border border-stroke px-3 py-2">
                Get help
              </a>
              <a href="#" className="rounded-xl border border-stroke px-3 py-2">
                Privacy & terms
              </a>
            </nav>
          </aside>
        </div>
      )}
    </main>
  );
}
