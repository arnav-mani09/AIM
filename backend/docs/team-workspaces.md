# Team workspace API & frontend notes

## New backend capabilities

- `POST /api/v1/teams` – create a team + coach membership from an authenticated user body `{ name, level?, season_label? }`. Returns the membership payload with nested team fields.
- `GET /api/v1/teams` – list every membership for the authenticated user so the UI can render their workspaces (each item includes `role`, `joined_at`, and the team metadata).
- `POST /api/v1/teams/{teamId}/invites` – coaches/admins mint new invite codes by supplying `{ role?, expires_in_hours?, max_uses? }`. Response contains the generated code and limits so it can be copied in the UI.
- `POST /api/v1/teams/join` – accept an invite via `{ code }`, validating expiration and max uses, and returning the resulting membership.

Refer to `backend/app/api/v1/routes/teams.py` for implementation details.

## Frontend integration roadmap

1. **Persist auth token** – continue storing the JWT from `/auth/login` so client-side requests to `/api/v1/teams` include the `Authorization` header (Next.js route handlers can proxy if we keep secrets server-side).
2. **Workspace list view** – call `GET /api/v1/teams` after login and render each membership (team name, season label, role). Provide CTA buttons for “Create team” and “Join via code”.
3. **Create team modal/form** – capture `name`, `level`, and `season_label`, post to `/api/v1/teams`, then push the new membership into local state so the dashboard updates instantly.
4. **Invite management UI** – inside a team detail page, allow coaches to click “Generate invite link”, hit `POST /api/v1/teams/{id}/invites`, and show the returned `code`, `max_uses`, and expiration. Optional copy-to-clipboard behavior.
5. **Join via code flow** – simple modal that hits `/api/v1/teams/join` with the user-entered code and, on success, adds the membership to state. Surface backend errors (expired/invalid) inline.
6. **Link clips & stats** – once teams exist on the frontend, scope film uploads, chat prompts, and stat dashboards by `team_id` so every feature knows which workspace data to show.

These steps let us demonstrate team onboarding immediately while we continue building clip uploads and AI chat on top of the same workspace identifiers.

## Raw film uploads

Film is stored in Cloudflare R2 (bucket `aim-film`, see `app/services/storage.py`) and referenced in the database as `r2://aim-film/<key>`. The browser uploads straight to R2 in 64 MB parts (`aim-app/lib/filmUpload.ts`); the file never passes through FastAPI.

- `POST /api/v1/teams/{teamId}/film/uploads` – start an upload `{ title, notes?, game_id?, filename, content_type, size_bytes }` (MP4/MOV, up to 5 GB). Creates the `game_upload` row with status `uploading` and returns `{ upload, part_size, part_count }`.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/upload/sign` – `{ part_numbers }` → a signed R2 PUT link per part (valid 1 hour; the client signs each part right before sending it).
- `GET /api/v1/teams/{teamId}/film/{uploadId}/upload/parts` – parts R2 already has, so an interrupted upload resumes where it stopped.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/upload/complete` – checks R2's parts against the expected size, finishes the upload, sets status `processing` and starts processing.
- `DELETE /api/v1/teams/{teamId}/film/{uploadId}/upload` – cancel an in-progress upload.
- `GET /api/v1/teams/{teamId}/film/{uploadId}/playback` – signed R2 link (valid 12 hours) the `<video>` element loads directly; supports seeking. Clips have the same at `/clips/{clipId}/playback`.
- `GET /api/v1/teams/{teamId}/film` and `GET .../film/{uploadId}` – list and fetch uploads.

The R2 bucket's CORS rules must list every frontend origin that uploads (currently `http://localhost:3000` and `https://aim-app-seven.vercel.app`).

### Processing (Modal worker)

When an upload completes, the backend starts `make_proxy` in the Modal app `aim-film` (`worker/film_worker.py`). It downloads the original from R2, writes a 720p H.264 proxy (`<key>.proxy-720p.mp4`, keyframe every 2 s) and a thumbnail (`<key>.thumb.jpg`) next to it, and returns the exact duration. The backend stores the job id in `game_upload.processing_job_id` and collects the result on page polls and every 20 s in a background thread (`app.main`), then sets `proxy_url`, `thumbnail_url`, `duration_seconds`, creates segments, and marks the upload `ready`. Playback serves the proxy once it exists. If Modal can't be reached, the upload falls back to ffprobe-only processing with no proxy.

- Deploy the worker: `backend/.venv/bin/modal deploy worker/film_worker.py`
- The worker reads R2 credentials from the Modal secret `aim-r2`.
- The backend authenticates to Modal with `~/.modal.toml` locally, or `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` env vars on Render.

### Segment / clip workflow

- `GET /api/v1/teams/{teamId}/film/{uploadId}/segments` – retrieve auto-detected or coach-created segments for that game upload.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/segments` – create a manual segment (start/end seconds, label, notes). This is available now to unblock the editor UI.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/segments/{segmentId}/publish` – promote a segment into a regular `Clip` tied to the team, preserving the source upload/timecode.

Planned: background worker populates `film_segment` rows automatically; the UI then lets coaches tweak those bounds before publishing to team spaces.
