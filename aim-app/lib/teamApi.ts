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
};

export type GameUploadRecord = {
  id: number;
  title: string;
  notes?: string | null;
  status: string;
  storage_url: string;
  uploaded_at: string;
  duration_seconds?: number | null;
};

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

export async function uploadGameFilm(
  token: string,
  teamId: number,
  formData: FormData
): Promise<GameUploadRecord> {
  const response = await fetch(`${baseUrl}/api/v1/teams/${teamId}/film`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Failed to upload film");
  }
  return response.json();
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
