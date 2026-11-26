"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { createPlayer, fetchPlayers, PlayerRecord, updatePlayer } from "@/lib/teamApi";

type RosterPanelProps = {
  token: string;
  teamId: number;
  canEdit: boolean;
};

export default function RosterPanel(props: RosterPanelProps) {
  return <TeamRosterPanel key={`${props.teamId}:${props.token}`} {...props} />;
}

function TeamRosterPanel({ token, teamId, canEdit }: RosterPanelProps) {
  const [players, setPlayers] = useState<PlayerRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [jersey, setJersey] = useState("");
  const [saving, setSaving] = useState(false);
  const saveLock = useRef(false);
  const nameInput = useRef<HTMLInputElement>(null);
  const requestVersion = useRef(0);

  useEffect(() => {
    const version = ++requestVersion.current;
    let active = true;
    fetchPlayers(token, teamId)
      .then((data) => { if (active && version === requestVersion.current) setPlayers(data); })
      .catch((error) => {
        if (active && version === requestVersion.current) {
          setLoadError(error instanceof Error ? error.message : "Unable to load roster.");
        }
      })
      .finally(() => { if (active && version === requestVersion.current) setLoading(false); });
    return () => { active = false; };
  }, [token, teamId, refresh]);

  function resetForm() {
    setEditingId(null);
    setName("");
    setJersey("");
    setSaveError(null);
  }

  function editPlayer(player: PlayerRecord) {
    if (saveLock.current) return;
    setEditingId(player.id);
    setName(player.name);
    setJersey(player.jersey_number);
    setSaveError(null);
    setNotice("");
    nameInput.current?.focus();
  }

  async function savePlayer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit || loading || loadError || saveLock.current) return;
    const payload = { name: name.trim(), jersey_number: jersey.trim() };
    if (!payload.name || !payload.jersey_number) {
      setSaveError("Enter a player name and jersey number.");
      return;
    }
    if (players.some((player) => player.id !== editingId && player.jersey_number === payload.jersey_number)) {
      setSaveError("That jersey number is already on this roster. Edit the existing player instead.");
      return;
    }
    saveLock.current = true;
    setSaving(true);
    setSaveError(null);
    setNotice("");
    try {
      const saved = editingId === null
        ? await createPlayer(token, teamId, payload)
        : await updatePlayer(token, teamId, editingId, payload);
      requestVersion.current += 1;
      setPlayers((current) => [...current.filter((player) => player.id !== saved.id), saved]
        .sort((first, second) => first.name.localeCompare(second.name)));
      resetForm();
      setNotice(`${saved.name} saved to the roster.`);
      nameInput.current?.focus();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Unable to save player. Your entries are still here.");
    } finally {
      saveLock.current = false;
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm leading-6 text-subtext">
        Add names and jersey numbers once, whenever you&apos;re ready. Film uploads do not require a roster.
        Roster entries alone do not identify players in video or verify individual statistics.
      </p>
      {loading ? <p role="status" className="text-sm text-subtext">Loading roster…</p> : loadError ? (
        <div role="alert" className="space-y-2 text-sm text-red-700">
          <p>{loadError}</p>
          <button type="button" onClick={() => {
            setLoading(true);
            setLoadError(null);
            setRefresh((value) => value + 1);
          }} className="underline">Retry roster</button>
        </div>
      ) : players.length === 0 ? (
        <div className="dashboard-empty"><p className="font-semibold text-ink">No players added yet</p>
          <p className="mt-1 text-sm text-subtext">{canEdit ? "Start with a name and jersey number below." : "Ask a team owner, coach, or admin to add players."}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-stroke">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Team roster</caption>
            <thead className="bg-tint text-subtext"><tr>
              <th scope="col" className="px-4 py-3">Jersey</th><th scope="col" className="px-4 py-3">Player</th>
              {canEdit && <th scope="col" className="px-4 py-3"><span className="sr-only">Actions</span></th>}
            </tr></thead>
            <tbody>{players.map((player) => (
              <tr key={player.id} className="border-t border-stroke">
                <td className="px-4 py-3 font-semibold text-subtext">#{player.jersey_number}</td>
                <th scope="row" className="px-4 py-3 font-medium text-ink">{player.name}</th>
                {canEdit && <td className="px-4 py-3 text-right"><button type="button" disabled={saving}
                  onClick={() => editPlayer(player)} aria-label={`Edit ${player.name}`}
                  className="font-semibold text-ink underline disabled:opacity-50">Edit</button></td>}
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {canEdit ? (
        <form onSubmit={savePlayer} className="space-y-4 rounded-2xl border border-stroke p-4">
          <h4 className="font-semibold text-ink">{editingId === null ? "Add a player" : "Edit player"}</h4>
          <fieldset disabled={saving || loading || Boolean(loadError)} className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <label className="flex flex-col gap-2 text-sm text-ink">Player name
              <input ref={nameInput} value={name} onChange={(event) => setName(event.target.value)}
                required maxLength={100} autoComplete="off" className="rounded-xl border border-stroke px-3 py-2" />
            </label>
            <label className="flex flex-col gap-2 text-sm text-ink">Jersey number
              <input value={jersey} onChange={(event) => setJersey(event.target.value)}
                required maxLength={10} autoComplete="off" placeholder="e.g. 00"
                className="rounded-xl border border-stroke px-3 py-2" />
            </label>
          </fieldset>
          <div className="flex flex-wrap gap-3">
            <button type="submit" disabled={saving || loading || Boolean(loadError)}
              className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {saving ? "Saving…" : editingId === null ? "Add player" : "Save changes"}
            </button>
            {editingId !== null && <button type="button" disabled={saving} onClick={resetForm}
              className="rounded-xl border border-stroke px-4 py-2 text-sm text-ink">Cancel edit</button>}
          </div>
          {saveError && <p role="alert" className="text-sm text-red-700">{saveError}</p>}
        </form>
      ) : <p className="text-xs text-subtext">Roster is read-only here. Team owners, coaches, and admins can manage players.</p>}
      <p role="status" className="text-sm text-emerald-700">{notice}</p>
    </div>
  );
}
