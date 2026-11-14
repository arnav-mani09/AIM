# Event launch reliability

## Scope

The optional event-rerun endpoint checked `events_status` before calling
`FilmProcessingService.start_events`, but that read did not serialize callers.
Two requests could both see a completed job, spawn separate workers, and replace
the single stored job ID. The same service also has callers outside that route.

`start_events` now claims the upload with a conditional database update before
spawning. The update and recording the returned job ID share one transaction.
An overlapping start must wait for the first transaction, then cannot claim a
row whose event status is already running. No process-local lock is required.
The subsequent upload read refreshes any existing ORM identity-map entry.

Completed, failed, and never-started uploads can still start. Existing event
results and team-orientation metadata are retained while the replacement runs.
Missing uploads and missing/invalid track references do not launch workers.
A worker-launch exception records the existing error state and permits retry.

This adds no coach confirmation or review requirement. It changes job
reliability, not points, rebound, or assist detection accuracy.

## Offline validation

```sh
cd backend
.venv/bin/python -m unittest tests.test_film_processing -v
.venv/bin/python -m unittest tests.test_film_processing tests.test_shot_events tests.test_insights tests.test_season tests.test_chat -q
```

The eight focused tests use a temporary SQLite database and mocked Modal calls.
They cover repeated launches, retained results, retry, invalid input, a stale ORM
session, and two overlapping transactions on separate connections. The
concurrency test holds the first mocked spawn until the second connection
attempts its conditional update; exactly one worker is spawned.

This is not a live PostgreSQL or Modal integration test. The database transaction
is held during the remote spawn call. A process crash or database commit failure
after a remote worker accepts the request can still orphan a job: the database
and remote queue do not share a distributed transaction. Durable queue idempotency
would be separate work. A running row without a job ID is not silently restarted.
Proxy and detector launch semantics are unchanged.
