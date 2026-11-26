# Recoverable direct film upload

Device uploads use fixed-size 64-MiB parts, except the last part, and a maximum
5-GiB source. The server signs allowed part numbers, reads the actual R2 part
record and completes the object; it never accepts browser-supplied ETags.

`POST /teams/{team_id}/film/{upload_id}/upload/complete` is retryable after a lost
HTTP response. Already-completed uploads return their current processing, ready
or error state without completing storage or starting another processing job.
The response does not claim processing succeeded when the state is `error`.

Completion serializes on the upload row with a PostgreSQL row lock and refreshes
previously loaded ORM state. Parts must have exactly the expected consecutive
numbers and individual byte sizes, not just the expected combined length.
SQLite unit tests exercise the sequential contract, not PostgreSQL concurrency.

If R2 reports `NoSuchUpload`, the server checks the unique destination object.
Only an object whose byte length exactly matches this upload can recover the
transition to processing. This handles completion succeeding in R2 before a
database commit or response was lost. Missing, inaccessible or size-mismatched
objects never count as success, and unrelated provider failures are not treated
as completed uploads. Byte-length verification is recovery evidence, not a
content hash, container check or film-quality guarantee.

The existing background task starts processing after the database commit. A
process crash before that task starts is a separate dispatch-recovery concern;
this contract does not claim exactly-once worker dispatch across external calls
and database commits. Incomplete multipart lifecycle cleanup remains required.

Offline regressions:

```sh
cd backend
.venv/bin/python -m unittest tests.test_film_upload -v
```
