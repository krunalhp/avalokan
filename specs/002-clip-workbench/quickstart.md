# Run the clip workbench

## Orb

Run from the repository root:

```bash
.agents/setup
amp orb services ensure
```

Use the printed workbench portal, not its loopback address. `.amp/services.yaml`
supervises PostgreSQL on port 55432 and the API/worker/UI on port 8000. Setup
initializes the database but does not leave a daemon running. Resume does not
reinstall dependencies. Services and app data live in this orb; neither the
database nor uploaded media is committed. Back them up separately before losing
the orb if you need them.

The demo service deliberately sets `AVALOKAN_DEMO=1`. All viewers share the same
library. Do not upload sensitive footage. Upload a local clip, choose activities
and click **Upload & analyze**. Select an event to seek, filter the list, and
append a verdict. A verdict never changes the model's original observation.

## Configuration and non-demo use

| Setting | Meaning |
|---|---|
| `AVALOKAN_DATA` | Data root; defaults to repository `.data` |
| `AVALOKAN_DATABASE_URL` | psycopg DSN; defaults to `.data/socket`, port 55432, database postgres |
| `AVALOKAN_DEMO=1` | Explicit authentication bypass; otherwise a token is required |
| `AVALOKAN_API_TOKEN` | Shared operator token, at least 24 characters; use a secret manager |
| `AVALOKAN_WORKER=1` | Start the supervised worker under the API process |
| `AVALOKAN_ALLOWED_ACTIVITIES` | Comma-separated instance allowlist; unset = registry, empty = deny all |
| `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` | Keep native CPU thread usage bounded |

To enable token mode, remove `AVALOKAN_DEMO` from service configuration, configure
`AVALOKAN_API_TOKEN` through Amp project secrets, refresh the orb environment,
and restart the service. Never commit the token. The UI exchanges it for a
one-hour HttpOnly, SameSite=Strict cookie. Other clients use a bearer header.
Use HTTPS for remote access. Token mode is one trusted operator group, **not**
multi-tenant identity, audit attribution, rate limiting or production security.
Do not expose the private PostgreSQL socket/database as a portal.

Outside Amp, install Python 3.11, uv, Node compatible with Vite 7, FFmpeg and
PostgreSQL 15. Run `uv sync --locked`, `npm --prefix web ci`,
`npm --prefix web run build`, and
`PYTHONPATH=src uv run --locked python -m avalokan.install_model`.
Supply a private database DSN, token and data directory, then launch:

```bash
PYTHONPATH=src AVALOKAN_WORKER=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --locked uvicorn avalokan.api:app --app-dir src --host 127.0.0.1 --port 8000
```

API startup applies the initial schema. Use a disposable/new database; review
migrations before pointing this development application at any shared database.
For UI development, `npm --prefix web run dev` proxies `/v1` to the API; rebuild
`web/dist` and restart the API to inspect the served production build.

## Agent workflow

The repository skill is `.agents/skills/analyzing-cctv/SKILL.md`. It uses this
client and the same API as the UI. For a local demo:

```bash
export AVALOKAN_URL=http://127.0.0.1:8000
C='.venv/bin/python .agents/skills/analyzing-cctv/scripts/client.py'
$C capabilities
$C upload /path/to/approved-clip.mp4 --authorized
$C submit MEDIA_ID --idempotency-key unique-analysis-key \
  --activity object.present --activity zone.dwell \
  --config '{"classes":["person"],"sample_fps":2,"dwell_seconds":10}'
$C wait JOB_ID --timeout 900
$C events JOB_ID --from-s 0 --to-s 60 --all
$C metrics JOB_ID --all
```

Replace IDs with returned values. In token mode, provision the token in
`AVALOKAN_API_TOKEN`, never in command arguments. Upload requires authorization
to send that particular footage to that server. Job submission is safely
repeatable with the same idempotency key and payload. Uploads/reviews are not
automatically retried after uncertain network outcomes.

Open `/docs` on the workbench origin for OpenAPI, or read
[the API contract](contracts/api.md). Event queries use half-open time overlap.
Numeric samples are occupancy gauges, not unique-object totals or values that
can be summed over time. No wall-clock time is inferred from video overlays.

## Storage and resource bounds

`media` stores original metadata/hash and local source/proxy paths. `jobs`
stores configuration, admission key, status, attempts and statistics. `events`
stores run-scoped facts and provenance. `metric_samples` stores clip-relative
time series; `reviews` stores append-only verdicts. PostgreSQL indexes support
job/cursor/activity/time queries. Redis is unnecessary for this batch slice.

One worker owns a database advisory lock. Each clip runs in a fresh child with
one ONNX inference thread, a 15-minute deadline and a 3-minute playback-preparation
deadline. At most eight jobs may be queued/running. Interrupted jobs retry the
whole clip, at most three attempts. Attempt fencing and one completion transaction
prevent stale workers or incomplete runs publishing events. This is not a
distributed worker pool or checkpoint-based resume.

Limits also include 250 MiB, 600 seconds, 4K, 90,000 decoded frames, and bounded
event output. Decode still visits skipped frames; lower sample rates save
inference, not all decode cost. No retention/deletion API exists yet. Do not
remove DB rows/media directories manually unless the data is disposable.

## Verify and change

```bash
uv run --locked pytest -q
uv run --locked python -m unittest discover -s .agents/skills/analyzing-cctv/scripts
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
npm --prefix web run build
```

Tests require PostgreSQL and create/drop only their own temporary schemas.
Model accuracy requires a separate labeled corpus; passing these tests does not
qualify detections. See [results](results.md) and [extensions](extensions.md).
