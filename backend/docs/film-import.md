# Authorized direct-download film import

## API contract

`POST /api/v1/teams/{team_id}/film/import` requires the existing bearer authentication
and membership of that team. Request:

```json
{
  "title": "Valley game",
  "source_url": "https://enabled-download-provider.example/game.mp4?authorized-signature=...",
  "notes": "Optional coach notes",
  "valley_jersey": "white",
  "opponent_jersey": "blue"
}
```

Only `title` and `source_url` are required. No game/box score is required or
created. Success is **202** with the existing `GameUploadRead` object, initially
`status: "importing"` and `processing_error: null`. Poll the existing GET film
list or GET film/{id}; statuses advance through `importing` → `processing` →
`ready`, or `error` with a safe `processing_error`. There is no byte-level import
progress API. `size_bytes` is populated when import completes. The original
multipart browser upload endpoints remain unchanged.

Disabled/unconfigured import or unavailable worker returns **503**; forbidden
providers/URL syntax return **400**; malformed requests return a generic **422**
without echoing the signed URL. Nonmembers receive **403**, unauthenticated
requests **401**. Failed dispatch leaves a visible error row. Source-link
failures after dispatch become asynchronous error rows, not HTTP errors.

## Operator setup (not performed by this change)

1. Apply migration `0016` through the normal release procedure, before enabling
   the feature. No migration has been applied by this implementation.
2. Deploy the updated `worker/film_worker.py` to the configured `MODAL_FILM_APP`.
   Its separate `import_film` CPU function uses the existing `aim-r2` secret
   (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`).
3. Configure an R2 lifecycle rule to abort incomplete multipart uploads. This is
   required operational cleanup for forcibly killed/timed-out workers; Python
   `finally` cannot run when a container is terminated.
4. Set `FILM_IMPORT_ALLOWED_HOSTS` to a comma-separated list of **exact** trusted
   direct-download CDN hostnames, including every permitted redirect hostname.
   No wildcard or suffix matching. Keep this as narrow as possible. Set
   `FILM_IMPORT_ENABLED=true` only after the worker and cleanup rule are ready.

Both settings default to disabled/empty. Existing direct uploads still work.
The worker never receives database credentials and never writes database rows.
Modal invocation is spawned during the POST, rather than in a browser callback
or FastAPI background task. Its job ID and start time are persisted. The existing
20-second server poller collects results and starts the usual proxy/detection/
event pipeline without a browser. If the API restarts, the Modal import continues;
result collection resumes after restart. A crash between creating the row and
saving its job ID is detected after 2h15m and produces an error; there is no
automatic source replay or exactly-once dispatch guarantee. Row locking protects
result collection on PostgreSQL; SQLite is for offline tests only.

## Security and capability limits

- Supply a download you are authorized to use. Ordinary Hudl watch/share pages,
  login pages, HLS/DASH playlists, cookies, interactive sign-in, and DRM are not
  supported. This is not a Hudl integration or authorization bypass. Ask the
  provider for an authorized direct MP4/MOV download or upload the file instead.
- HTTPS only, port 443 only; no embedded credentials, URL fragments, IP literals,
  backslashes, raw whitespace/control characters, or unconfigured hosts.
  Each redirect is revalidated (at most five redirect hops). All DNS answers must
  be public unicast addresses; private, reserved, loopback, link-local, multicast,
  IPv4-mapped and IPv6 transition addresses are rejected. The socket connects to
  the validated numeric address, while TLS verifies the original hostname and
  supplies its SNI. No second DNS resolution or environment proxy is used, so a
  DNS change cannot redirect the connection to an internal address. Failure of
  the selected address fails the import rather than trying uncontrolled fallbacks.
- Maximum size is **5 GiB** (the existing upload limit), enforced on declared
  length and actual streamed bytes, including when length is missing. Downloads
  must return HTTP 200, `video/mp4` or `video/quicktime`, identity encoding, and a
  supported `ftyp` ISO-BMFF/QuickTime brand. Older MOV files without `ftyp` or
  servers returning generic `application/octet-stream` are not supported by link
  import; use direct upload instead. A restricted local ffprobe validates a real
  video stream and positive duration before publishing the R2 object.
- Data streams to R2 in 64 MiB multipart parts (bounded buffer), with a temporary
  local copy of at most 5 GiB for validation. Budget that much ephemeral worker
  disk. Completed objects feed the existing processing pipeline. On normal
  failures the connection closes, incomplete multipart upload is aborted, and
  the temporary file is removed. Abort itself is best-effort if R2 is unavailable;
  the lifecycle rule is the final safety net. Hard kills and the narrow dispatch
  crash window can leave unreferenced completed objects; reconcile orphaned
  objects operationally. Deleting an import cancels its Modal job best-effort and
  deletes its known object; incomplete parts still rely on lifecycle cleanup.
- Socket inactivity is limited to 30 seconds, download time to two hours, and
  worker time to 2h5m; imports still pending at 2h15m become errors. A failed or
  expired source needs a new POST/new authorized link; no automatic retries.
- **No source URL/token is stored in the database or returned by read APIs.**
  Only an R2 key, job ID and timestamps are persisted there. The source URL is
  supplied through a per-invocation private Modal Secret, not normal function
  arguments or environment metadata. Modal holds that secret as required for
  invocation; authorized Modal administrators remain inside the trust boundary.
  It is not an encrypted archival source/retry mechanism. Do not put tokens in
  user-visible title/notes fields. Import worker exceptions return only static
  errors, never remote bodies, redirect locations or raw transport exceptions.
  Sentry events for the POST import request are suppressed to avoid request-body
  or stack-local capture. Access logs should record paths/statuses only; do not
  configure upstream infrastructure to log request bodies.

## Offline validation

```bash
cd backend
.venv/bin/python -m unittest tests.test_film_import tests.test_film_delete tests.test_film_processing -v
```

Tests mock Modal, R2, sockets and probing: no downloads, installs, paid calls,
live migrations or deployments are necessary. They cover access control,
disabled configuration, response secrecy, URL/DNS/redirect policy, numeric-IP
TLS pinning, bounded multipart streaming, size/container/probe failures, abort
cleanup, restart polling and processing handoff.
