# Bounded film deletion cleanup

## Route and failure contract

- `DELETE /api/v1/teams/{team_id}/film/{upload_id}` requires team membership and
  looks up the upload within that team (404 if missing). A successful deletion
  returns 204 with no response body.
- Before storage deletion, attempt each nonempty persisted `processing_job_id`,
  `detection_job_id`, and `events_job_id` once, deduplicated in that order. Do not
  gate cancellation on status: stale IDs can still identify active work.
- Cancellation is best effort, matching `FilmProcessingService.cancel_job`:
  exceptions are captured in Sentry, other IDs are still attempted, and deletion
  continues. This is not confirmation that remote work has stopped. The route
  also catches unexpected cancellation exceptions rather than skipping later IDs.
- Existing original/proxy/thumbnail deletion remains. Multipart uploads are
  aborted instead of deleting any objects. S3 client/core errors produce 502 and
  leave database deletion uncommitted; earlier external effects cannot roll back.
- Published clips linked through `source_upload_id` are deleted. Existing ORM
  cascades delete film segments and all persisted shot/play events, including
  hidden events; unrelated clips and uploads remain.
- The separate `DELETE .../{upload_id}/upload` is unchanged: it only accepts an
  in-progress multipart upload (409 otherwise), aborts it, and deletes its row.
  It does not cancel film-processing jobs.

## Conservative analysis-object cleanup

Only persisted tracks/events URLs are considered; there is no bucket listing,
prefix deletion, worker invocation, or guessing of unrecorded output keys.

The upload source must be a canonical URL in the configured bucket, with the
current uploader's `teams/{team_id}/film/{32 lowercase hex digits}.mp4|mov` key.
Analysis URLs must also reference that exact configured bucket and match the
worker's source-derived naming: `<source-stem>.tracks-<version>.json.gz` or
`<source-stem>.tracks-<version>.events.json`. Versions cannot contain `/`.
The storage parser alone is insufficient: it discards the URL bucket while
`delete_object` always targets the configured bucket.

Skip an analysis object if another upload references it as original, proxy,
thumbnail, tracks, or events, or another upload uses the same original source.
Also skip it when a surviving clip references it. Clips linked to the deleted
upload do not prevent cleanup because they are deleted in the same operation.
At most two additional object keys are considered; all deletion keys are
deduplicated. Unknown, external, legacy, foreign-bucket, or nonmatching analysis
URLs are deliberately retained.

## Limits

- No changes to worker code, processing retries, polling, or job submission.
- A failed/asynchronous cancellation or concurrent worker/request can still
  produce an orphan after cleanup. There is no durable tombstone, cross-service
  transaction, or race-free reference lock in this bounded route fix.
- Old model outputs, unrecorded outputs, and other historical artifacts are not
  discovered or deleted. No general garbage collector is introduced.
- The ownership checks apply to newly added tracks/events cleanup. Historical
  original/proxy/thumbnail deletion behavior is not expanded or hardened here;
  shared or foreign-bucket legacy media references remain an existing limitation.
- Reference checks cover the storage-bearing upload and clip models, not arbitrary
  JSON, external consumers, or future models.

## Offline regression command

```sh
cd backend
.venv/bin/python -m unittest tests.test_film_delete -v
```

The API tests mount only the film router on a local FastAPI app, use in-memory
SQLite, override membership/database dependencies, and mock storage operations
and Modal cancellation. The real cancellation wrapper is separately exercised
against a mocked Modal failure. Socket connections and storage-client creation
are blocked; no live database, bucket, worker, or background poller is used.
