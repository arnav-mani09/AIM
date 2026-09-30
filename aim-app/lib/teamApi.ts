export type TeamSummary = {
  id: number;
  name: string;
  level?: string | null;
  season_label?: string | null;
  created_at: string;
};

export type TeamMembership = {
  id: number;
  role: string;
  joined_at: string;
  team: TeamSummary;
};

export type TeamInvite = {
  id: number;
  code: string;
  role: string;
  expires_at?: string | null;
  max_uses?: number | null;
  uses: number;
};

const baseUrl = process.env.NEXT_PUBLIC_BASE_URL ?? "http://127.0.0.1:8000";

export type ClipPlayerTouch = {
  player: string;
  touches: number;
};

export type ClipStatSummary = {
  total_possessions: number;
  players: ClipPlayerTouch[];
};

export type ClipPossessionContext = {
  possession_id: number;
  label: string;
  outcome?: string | null;
  player?: string | null;
  team?: string | null;
  start_second?: number | null;
  end_second?: number | null;
};

export type ClipRecord = {
  id: number;
  title: string;
  notes?: string | null;
  status: string;
  storage_url: string;
  team_id?: number | null;
  game_id?: number | null;
  uploaded_at: string;
  uploaded_by_id?: number | null;
  source_upload_id?: number | null;
  source_start_second?: number | null;
  source_end_second?: number | null;
  game_matchup?: string | null;
  game_scheduled_at?: string | null;
  stats_summary?: ClipStatSummary | null;
  possession_context?: ClipPossessionContext[];
};

export type GameUploadRecord = {
  id: number;
  title: string;
  notes?: string | null;
  status: string;
  storage_url: string;
  uploaded_at: string;
  size_bytes?: number | null;
  duration_seconds?: number | null;
  game_id?: number | null;
  game_matchup?: string | null;
  game_scheduled_at?: string | null;
};

export type FilmUploadStarted = {
  upload: GameUploadRecord;
  part_size: number;
  part_count: number;
};

export type SignedPart = { part_number: number; url: string };
export type UploadedPart = { part_number: number; size: number };
export type PlaybackUrl = { url: string; expires_in: number };

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? detail.message ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function fetchTeams(token: string): Promise<TeamMembership[]> {
  return request<TeamMembership[]>("/api/v1/teams", token);
}

export function createTeam(
  token: string,
  payload: { name: string; level?: string; season_label?: string }
): Promise<TeamMembership> {
  return request<TeamMembership>("/api/v1/teams", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function joinTeam(token: string, code: string): Promise<TeamMembership> {
  return request<TeamMembership>("/api/v1/teams/join", token, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function createInvite(
  token: string,
  teamId: number,
  payload: { role?: string; expires_in_hours?: number; max_uses?: number }
): Promise<TeamInvite> {
  return request<TeamInvite>(`/api/v1/teams/${teamId}/invites`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function uploadTeamClip(
  token: string,
  teamId: number,
  formData: FormData
): Promise<ClipRecord> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/clips`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to upload clip");
  }
  return response.json();
}

export async function fetchTeamClips(token: string, teamId: number): Promise<ClipRecord[]> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/clips`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to load clips");
  }
  return response.json();
}

export async function deleteClip(token: string, teamId: number, clipId: number): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/clips/${clipId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to delete clip");
  }
}

export async function fetchClip(token: string, teamId: number, clipId: number): Promise<ClipRecord> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/clips/${clipId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to load clip");
  }
  return response.json();
}

export function startFilmUpload(
  token: string,
  teamId: number,
  payload: {
    title: string;
    notes?: string | null;
    game_id?: number | null;
    filename: string;
    content_type: string;
    size_bytes: number;
  }
): Promise<FilmUploadStarted> {
  return request<FilmUploadStarted>(`/api/v1/teams/${teamId}/film/uploads`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function signFilmUploadParts(
  token: string,
  teamId: number,
  uploadId: number,
  partNumbers: number[]
): Promise<SignedPart[]> {
  return request<SignedPart[]>(`/api/v1/teams/${teamId}/film/${uploadId}/upload/sign`, token, {
    method: "POST",
    body: JSON.stringify({ part_numbers: partNumbers }),
  });
}

export function listFilmUploadParts(token: string, teamId: number, uploadId: number): Promise<UploadedPart[]> {
  return request<UploadedPart[]>(`/api/v1/teams/${teamId}/film/${uploadId}/upload/parts`, token);
}

export function completeFilmUpload(token: string, teamId: number, uploadId: number): Promise<GameUploadRecord> {
  return request<GameUploadRecord>(`/api/v1/teams/${teamId}/film/${uploadId}/upload/complete`, token, {
    method: "POST",
  });
}

export async function abortFilmUpload(token: string, teamId: number, uploadId: number): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}/upload`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to cancel upload");
  }
}

export function fetchFilmPlaybackUrl(token: string, teamId: number, uploadId: number): Promise<PlaybackUrl> {
  return request<PlaybackUrl>(`/api/v1/teams/${teamId}/film/${uploadId}/playback`, token);
}

export function fetchClipPlaybackUrl(token: string, teamId: number, clipId: number): Promise<PlaybackUrl> {
  return request<PlaybackUrl>(`/api/v1/teams/${teamId}/clips/${clipId}/playback`, token);
}

export async function fetchGameFilm(token: string, teamId: number): Promise<GameUploadRecord[]> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to load film");
  }
  return response.json();
}

export async function fetchGameUpload(token: string, teamId: number, uploadId: number): Promise<GameUploadRecord> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to load film");
  }
  return response.json();
}

export async function deleteGameFilm(token: string, teamId: number, uploadId: number): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to delete film");
  }
}

export type FilmSegment = {
  id: number;
  upload_id: number;
  start_second: number;
  end_second: number;
  label?: string | null;
  confidence?: number | null;
  notes?: string | null;
  created_at: string;
};

export async function fetchFilmSegments(
  token: string,
  teamId: number,
  uploadId: number
): Promise<FilmSegment[]> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}/segments`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to load segments");
  }
  return response.json();
}

export async function createFilmSegment(
  token: string,
  teamId: number,
  uploadId: number,
  payload: { start_second: number; end_second: number; label?: string; notes?: string }
): Promise<FilmSegment> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}/segments`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to create segment");
  }
  return response.json();
}

export async function publishFilmSegment(
  token: string,
  teamId: number,
  uploadId: number,
  segmentId: number
): Promise<ClipRecord> {
  const response = await fetch(
    `${baseUrl}/api/v1/teams/${teamId}/film/${uploadId}/segments/${segmentId}/publish`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to publish clip");
  }
  return response.json();
}

export type PlayerRecord = {
  id: number;
  name: string;
  jersey_number: string;
  team_id?: number | null;
};

export type GameRecord = {
  id: number;
  matchup: string;
  scheduled_at: string;
  location?: string | null;
  home_team_id?: number | null;
  away_team_id?: number | null;
  primary_upload_id?: number | null;
};

export type ShotZone =
  | "restricted_area"
  | "paint"
  | "mid_range_left"
  | "mid_range_right"
  | "corner_three_left"
  | "corner_three_right"
  | "wing_three_left"
  | "wing_three_right"
  | "top_of_key_three";

export type PossessionSource = "manual" | "csv" | "ai";
export type ReviewStatus = "pending" | "confirmed" | "rejected";

export type PossessionRecord = {
  id: number;
  game_id: number;
  player_id?: number | null;
  player_name?: string | null;
  label: string;
  outcome?: string | null;
  shot_made?: boolean | null;
  shot_zone?: ShotZone | null;
  shot_x?: number | null;
  shot_y?: number | null;
  shot_value?: 2 | 3 | null;
  video_start_second?: number | null;
  video_end_second?: number | null;
  source: PossessionSource;
  review_status: ReviewStatus;
  created_by_id?: number | null;
  reviewed_by_id?: number | null;
  created_at: string;
  updated_at?: string | null;
};

export type ZoneStat = {
  zone: ShotZone;
  attempts: number;
  makes: number;
  fg_pct: number | null;
};

export type ShotChartRecord = {
  game_id: number;
  team_id: number;
  total_attempts: number;
  total_makes: number;
  overall_fg_pct: number | null;
  zones: ZoneStat[];
};

export function fetchPlayers(token: string, teamId: number): Promise<PlayerRecord[]> {
  return request<PlayerRecord[]>(`/api/v1/teams/${teamId}/players`, token);
}

export function createPlayer(
  token: string,
  teamId: number,
  payload: { name: string; jersey_number: string }
): Promise<PlayerRecord> {
  return request<PlayerRecord>(`/api/v1/teams/${teamId}/players`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchGames(token: string, teamId: number): Promise<GameRecord[]> {
  return request<GameRecord[]>(`/api/v1/teams/${teamId}/games`, token);
}

export function createGame(
  token: string,
  teamId: number,
  payload: { matchup: string; scheduled_at: string; location?: string }
): Promise<GameRecord> {
  return request<GameRecord>(`/api/v1/teams/${teamId}/games`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchGame(token: string, teamId: number, gameId: number): Promise<GameRecord> {
  return request<GameRecord>(`/api/v1/teams/${teamId}/games/${gameId}`, token);
}

export function fetchPossessions(
  token: string,
  teamId: number,
  gameId: number,
  opts?: { reviewStatus?: ReviewStatus; shotOnly?: boolean }
): Promise<PossessionRecord[]> {
  const params = new URLSearchParams();
  if (opts?.reviewStatus) params.set("review_status", opts.reviewStatus);
  if (opts?.shotOnly) params.set("shot_only", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<PossessionRecord[]>(`/api/v1/teams/${teamId}/games/${gameId}/possessions${query}`, token);
}

export type PossessionPayload = {
  player_id?: number | null;
  label?: string;
  outcome?: string;
  shot_made?: boolean;
  shot_zone?: ShotZone;
  shot_x?: number;
  shot_y?: number;
  shot_value?: 2 | 3;
  video_start_second?: number;
  video_end_second?: number;
};

export function createPossession(
  token: string,
  teamId: number,
  gameId: number,
  payload: PossessionPayload
): Promise<PossessionRecord> {
  return request<PossessionRecord>(`/api/v1/teams/${teamId}/games/${gameId}/possessions`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePossession(
  token: string,
  teamId: number,
  gameId: number,
  possessionId: number,
  payload: Partial<PossessionPayload> & { review_status?: ReviewStatus }
): Promise<PossessionRecord> {
  return request<PossessionRecord>(
    `/api/v1/teams/${teamId}/games/${gameId}/possessions/${possessionId}`,
    token,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
}

export async function deletePossession(
  token: string,
  teamId: number,
  gameId: number,
  possessionId: number
): Promise<void> {
  const response = await fetch(
    `${baseUrl}/api/v1/teams/${teamId}/games/${gameId}/possessions/${possessionId}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    }
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to delete possession");
  }
}

export function fetchShotChart(token: string, teamId: number, gameId: number): Promise<ShotChartRecord> {
  return request<ShotChartRecord>(`/api/v1/teams/${teamId}/games/${gameId}/shot-chart`, token);
}
