# Coach film workflow

## Adding a game

The Film + Clips workspace provides two intake methods with the same required
team and game title. Notes and jersey colors live under optional game details.
A box score is not required.

- **Import from a link:** submit an authorized HTTPS direct video download link.
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
Actual Hudl download-link compatibility still requires an authorized sample;
no Hudl account integration or unattended login is implemented.

## Library and processing

The library supports title/opponent search, video-ready and in-progress/issue
filters, manual refresh, and automatic refresh while server-side work is active.
Importing, preparing, incomplete uploads, and failures have distinct labels.
Video readiness is not a certification of statistical accuracy.

Game cards retain access to playback/editing, available stats and plays, linked
shot breakdowns, and removal. Published clips remain in their own section.
Stat review and correction remain optional. Roster and individual-stat accuracy
are not implied by this workflow.

## Design scope

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
