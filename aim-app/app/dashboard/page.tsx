'use client';

import { FormEvent, useState } from "react";

export default function DashboardPage() {
  const [videoMessage, setVideoMessage] = useState("");
  const [teamCode, setTeamCode] = useState("");
  const [teamMessage, setTeamMessage] = useState("");

  const handleVideoSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setVideoMessage("Upload pipeline coming soon—your clip will sync to the coaching staff.");
  };

  const handleTeamJoin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTeamMessage(`Request sent to join team code: ${teamCode}`);
    setTeamCode("");
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="label-text">Workspace</p>
        <h1 className="mt-2 text-3xl font-semibold text-[#0e1a2e]">Your AIM operations center</h1>
        <p className="text-subtext">
          Upload film, collaborate in chat, review past insights, and manage teams—all powered by AIM.
        </p>
      </header>

      <section className="section-card">
        <h2 className="text-2xl font-semibold text-[#0e1a2e]">Upload game film</h2>
        <p className="mt-2 text-sm text-subtext">
          Drag in MP4/MOV files and AIM will route them through the possession-tracking models.
        </p>
        <form onSubmit={handleVideoSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-2 text-sm">
            Select file
            <input type="file" className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]" required />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            Notes for staff
            <textarea className="rounded-xl border border-stroke px-3 py-2 text-[#0e1a2e]" rows={3} />
          </label>
          <button type="submit" className="self-start rounded-2xl bg-accent px-4 py-2 font-semibold text-white">
            Upload to AIM
          </button>
          {videoMessage && <p className="text-sm text-green-600">{videoMessage}</p>}
        </form>
      </section>

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

      <section className="section-card">
        <h3 className="text-xl font-semibold text-[#0e1a2e]">Team spaces</h3>
        <p className="mt-2 text-sm text-subtext">
          Coaches create codes so players, staff, and recruiters can collaborate securely.
        </p>
        <form onSubmit={handleTeamJoin} className="mt-4 flex flex-col gap-3 text-sm">
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
          <button type="submit" className="w-fit rounded-2xl border border-stroke px-4 py-2 font-semibold text-[#0e1a2e]">
            Request access
          </button>
          {teamMessage && <p className="text-sm text-green-600">{teamMessage}</p>}
        </form>
      </section>
    </main>
  );
}
