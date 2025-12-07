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

- `POST /api/v1/teams/{teamId}/film` – multipart upload endpoint for full-game or quarter footage. Stores files under `media_root/raw` and records metadata in the `game_upload` table.
- `GET /api/v1/teams/{teamId}/film` – lists all raw uploads for a team so the UI can display processing status before clips are generated.
- `GET /api/v1/teams/{teamId}/film/{uploadId}` – fetch metadata for a specific upload when loading the clip editor view.
- Frontend dashboard now includes a "Full game film" card wired to these routes; next step is a processing worker that turns each `game_upload` into possession timelines and enables clip-trimming from the raw source.

### Segment / clip workflow

- `GET /api/v1/teams/{teamId}/film/{uploadId}/segments` – retrieve auto-detected or coach-created segments for that game upload.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/segments` – create a manual segment (start/end seconds, label, notes). This is available now to unblock the editor UI.
- `POST /api/v1/teams/{teamId}/film/{uploadId}/segments/{segmentId}/publish` – promote a segment into a regular `Clip` tied to the team, preserving the source upload/timecode.

Planned: background worker populates `film_segment` rows automatically; the UI then lets coaches tweak those bounds before publishing to team spaces.
