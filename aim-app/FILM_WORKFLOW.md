# Coach film workflow

## Adding a game

The Film + Clips workspace provides two intake methods with the same required
team and game title. Notes and jersey colors live under optional game details.
A box score is not required.

Device upload is selected initially. A team-authenticated capability check enables
the link option only when the backend reports it configured. Disabled or missing
provider configuration is explained before a coach enters a URL. Failed checks
offer a retry and leave device upload selectable; they do not block the library.
Configuration status is not proof of worker deployment or provider compatibility.

- **Import from a link:** submit an authorized HTTPS direct video download link
  or a supported Hudl download-ready video email link.
  Ordinary watch pages, sign-in pages, passwords, and arbitrary cloud-sharing
  pages are not supported. The server determines permitted source hosts and
  validates the download; client-side checks are only input guidance. Once AIM
  acknowledges the queued import, the transfer runs independently of the browser.
- **Upload from your device:** choose an MP4 or MOV, up to 5 GB. The existing
  chunked upload supports pause/resume while its session and selected file remain
  in this mounted workspace. It does not promise cross-reload or cross-device
  resume. Keep the browser open until the transfer completes; subsequent video
  processing runs on AIM.

The interface does not store pasted source links in browser storage. Import
availability depends on backend configuration and worker deployment. A disabled
import service reports an actionable error and leaves direct upload available.
A bounded live check of the supplied Mitty video target on November 26, 2026
returned HTTP 206, an MP4 header and a roughly 4.0-GB total size. Only 1 KiB was
read; no full transfer, worker import or processing was verified. Its stats
target redirected to Hudl sign-in. The backend now locally unwraps the specific
Hudl download-ready email format, with the target CDN still requiring explicit
operator allowlisting. These links can expire. No private sample URLs are stored
in this document, and no Hudl account integration or unattended login is implemented.

## Library and processing

The library supports title/opponent search, video-ready and in-progress/issue
filters, manual refresh, and automatic refresh while server-side work is active.
Importing, preparing, incomplete uploads, and failures have distinct labels.
Video readiness is not a certification of statistical accuracy.

Game cards retain access to playback/editing, available stats and plays, linked
shot breakdowns, and removal. Published clips remain in their own section.
Stat review and correction remain optional. Roster and individual-stat accuracy
are not implied by this workflow.

## Optional roster setup

Team Spaces now includes a team-scoped roster. Coaches and admins can add or
edit player names and jersey numbers; other members can view the roster. Names
and jerseys are trimmed, leading zeroes in jerseys are retained, and duplicate
jersey conflicts are reported without discarding the form. Failed saves keep
the entries for retry, and switching teams mounts an isolated roster view.
Edits retain the player ID and existing possession links; deletion is not offered.
Roster setup never blocks a film upload and does not establish video identity or
individual-stat accuracy. The backend contract is in `backend/docs/team-workspaces.md`.

## Dashboard design

The shared dashboard shell supplies a navy sidebar, restrained orange accents,
white cards, clear active navigation, keyboard focus styles, reduced-motion
support, and a mobile drawer with focus trapping and Escape dismissal. Workspace
styles are scoped; public landing and authentication styling is unchanged.
Film, review, season, and scouting pages receive focused hierarchy improvements;
the shared styling also applies to the other dashboard views.

## Validation

From `aim-app`:

```sh
npm run build
./node_modules/.bin/tsc --noEmit --incremental false
./node_modules/.bin/eslint app/dashboard/page.tsx components/FilmLibrary.tsx lib/teamApi.ts lib/filmIntake.ts
```

Additional in-memory assertions exercised link/file validation, rendered library
empty/ready/importing/error states, escaped film titles, and the import API's
authenticated request and validation-error handling. These are not live-provider,
browser interaction, or real large-file transfer tests. Browser visual QA and a
live authorized import remain release checks.
