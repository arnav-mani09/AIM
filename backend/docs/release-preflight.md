# Offline film release preflight

This is a prerequisite checker, **not a deployment or release certification**.
It supports both enabled authorized direct-download imports and the existing
direct-upload-only rollout. It changes no application configuration, database
schema, deployment, bucket, or worker. Run it against a checkout containing the
backend and worker sources.

## Run

From the repository root:

```bash
backend/.venv/bin/python backend/tools/film_import_preflight.py
backend/.venv/bin/python backend/tools/film_import_preflight.py --json
```

The script is also executable and works from any working directory. Offline
checks use only the Python standard library. No dependency installation is
needed. It reads **only the process environment**, local Python source, and
migration files. It never loads `.env`, `.env.local`, Modal profiles, application
settings, database models, or migration execution code. Supply the target
backend environment through your existing secure environment mechanism, not
command-line secret values. Do not assume your current shell matches production.

Local Settings defaults are extracted without executing application code:
`FILM_IMPORT_ENABLED=false`, empty allowlist, `MODAL_FILM_APP=aim-film`,
`R2_BUCKET=aim-film`, and `DETECTION_ENABLED=false` in the current checkout.
Explicit environment values override these defaults. Presence is required for
`DATABASE_URL`, `SECRET_KEY`, R2 account/access/secret keys, bucket and Modal app.
Presence does not validate secret strength, credentials, placeholder values,
database URL syntax, or remote resources.

The allowlist accepts comma-separated exact ASCII fully-qualified DNS hostnames
(case-insensitive, whitespace around entries allowed). URLs, IP literals, ports,
wildcards, trailing dots and empty entries are rejected. This is deliberately
stricter than the runtime's string splitting. No DNS lookup occurs; valid syntax
does **not** establish public addresses, ownership, authorized downloads, or
safe redirect chains. Include all authorized redirect hosts and keep it narrow.

Both Modal environment tokens must be supplied together. On Render they are
required by this check. Elsewhere, an absent pair is `not_checked`: an existing
local Modal profile might work, but the tool never reads it. A token pair is only
`configured`, never proof of deployed worker access.

## What results mean

- `configured`: a process environment/default prerequisite is present or has
  valid syntax; no remote verification or secret-value validation occurred.
- `verified`: a specifically named local structural check passed, or the
  explicitly requested database revision query matched. Not a wider guarantee.
- `not_checked`: no evidence was obtained. Follow the check's actionable message.
- `invalid`: a missing or malformed prerequisite, broken local contract, or
  mismatched database revision blocks the selected scope.

Local checks inspect the Settings declaration, migration graph (one complete
head, including revision `0016` and its import columns), decorated worker
entrypoints, worker app/config alignment, import environment contract and local
downloader availability. Detection requires `detect_players` and `make_events`
in addition to `make_proxy`. Enabled imports also require `import_film`.
These checks do not execute or comprehensively validate worker behavior.

JSON includes `scope`, `local_prerequisites_passed`, `import_enabled`,
`database_check_requested`, `checks`, and `exit_code`. `release_ready` is always
`false`. Disabled imports select `scope: direct_upload_only`; passing local
checks does not claim import readiness or an all-feature release pass. An empty
allowlist is permitted in this scope, but a supplied malformed list is flagged.
Database/import migration availability is checked even with imports disabled:
the shared upload model may still depend on those columns.

Exit codes are deterministic:

| Code | Meaning |
| --- | --- |
| 0 | Selected-scope **local prerequisites only** passed; remote unchecked items remain. If requested, the database head also matched. |
| 1 | At least one blocking prerequisite or revision mismatch. Takes priority over code 3. |
| 2 | Invalid CLI invocation. Arguments are not echoed, including unknown arguments. |
| 3 | Local checks passed, but an explicitly requested database check could not be verified. |

Neither output format prints configuration values, allowlist contents, source
URLs, database endpoints, exception details, or credentials. The tool accepts no
source URL argument and performs no film downloads, paid calls, Modal/R2 API
calls, migration application, or deployment.

## Optional configured-database revision check

**This flag allows a network connection. Do not use it for offline validation.**

```bash
backend/.venv/bin/python backend/tools/film_import_preflight.py --check-database --json
```

Only with this explicit flag does the tool import the already-installed
`psycopg` driver and connect to the process `DATABASE_URL`. Supported schemes are
`postgresql`, `postgres`, and `postgresql+psycopg`, with an explicit hostname and
database. URL query options and fragments are deliberately unsupported so they
cannot override connection safety options; such configurations are reported
`not_checked`, without connecting. Do not strip required TLS options just to
make this check pass; use an independently reviewed read-only release check if
your connection policy requires unsupported URL options.

Connection timeout is five seconds. PostgreSQL enforces read-only transactions
from connection startup, a five-second statement timeout, and a two-second lock
timeout. The tool confirms transaction read-only status, then issues only
`SELECT version_num FROM alembic_version`. It rolls back and closes, never
commits. Missing driver, unsupported URL, denied SELECT, missing version table,
or connection/query failure remains `not_checked`; errors are value-free.
An empty, behind, unknown or multiple revision set is a blocking mismatch.
No Alembic environment or migration function is executed.

This verifies only the configured database's revision marker against local
source. It does **not** identify the database as production, inspect physical
columns/schema drift, or prove application permissions/search-path correctness.
Use least-privilege credentials and your normal release procedure independently.

## Still required outside this tool

Follow [film-import.md](film-import.md) for operator setup and security limits.
Independently verify the deployed Modal app, required CPU/GPU functions, runtime
credentials and `aim-r2` secret (including `R2_BUCKET`), ffmpeg/ffprobe packaging,
temporary disk capacity, worker timeouts and no-retry import behavior. Backend
R2 values do not prove the separate Modal secret is provisioned. Verify R2
playback/CORS and lifecycle abortion of incomplete multipart uploads; reconcile
orphaned completed objects. Apply schema updates through the normal reviewed
release process, never this tool.

No result certifies live Hudl compatibility. Ordinary Hudl watch/share/login
pages, HLS/DASH, interactive authentication, cookies and DRM are unsupported.
Only authorized direct MP4/MOV downloads meeting the import contract qualify;
direct upload remains the fallback. Any live compatibility validation must be
separately authorized and avoid leaking signed source URLs.

## Focused offline tests

```bash
cd backend
.venv/bin/python -m unittest tests.test_film_import_preflight -v
```

Tests use explicit synthetic environments, block sockets/DNS and private config
reads, and mock the optional database driver. They do not read real `.env`
files, contact a live database, install dependencies, deploy, or download media.
