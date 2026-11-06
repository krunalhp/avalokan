---
name: debugging-footage-runs
description: "Monitors the Avalokan clip workbench, diagnoses failed footage ingests or analysis jobs from trace logs, fixes them, and records every change in MEMORY_LOG.md. Triggers on: footage failed, analysis broke, job failed, check the app logs, why did my video not analyze, monitor the workbench."
---

# Debugging Footage Runs

Debug cycle for the Avalokan clip workbench (FastAPI + worker + Postgres + web UI).
When the user reports a problem ("my video failed", "no events appeared"), run this
loop: observe → diagnose → fix → verify → record.

## 1. Check the service is alive

```bash
amp orb service status avalokan avalokan-db
curl -s http://127.0.0.1:8000/health
```

If the API is down, read startup errors: `amp orb service logs avalokan | tail -50`.
After code or dependency changes, `amp orb service restart avalokan`.

## 2. Trace the failing run

Every request, ingest, and job logs one JSON line per event with a `trace_id`
(`req_*` HTTP requests, `ing_*` URL ingests, the job UUID for analysis).

```bash
# Recent errors first
amp orb service logs avalokan | grep '"level": "error"' | tail -20
# Follow one run end to end (job id / trace id from the UI or DB)
amp orb service logs avalokan | grep '<TRACE-OR-JOB-ID>'
```

Job state and per-job stats also live in Postgres:

```bash
uv run --locked python -c "
import psycopg
from avalokan.settings import Settings
with psycopg.connect(Settings().dsn, row_factory=psycopg.rows.dict_row) as c:
    for r in c.execute('SELECT id,status,progress,error,stats FROM jobs ORDER BY created_at DESC LIMIT 5'):
        print(r)
"
```

## 3. Known failure modes

- **YouTube/figshare "Sign in to confirm you're not a bot"**: the host blocks
  datacenter IPs. Fix: export a Netscape `cookies.txt` from the user's browser and
  save it to `.data/secrets/youtube-cookies.txt` (or set `AVALOKAN_YTDLP_COOKIES`),
  then retry. Never commit the cookie file; it is under `.data/` (gitignored).
- **422 "Cannot read video"** on ingest: downloaded file failed ffprobe validation
  (codec, > 600 s duration, wrong dimensions). The trace line `ingest.failed`
  carries the real cause.
- **Job failed with "Analysis exceeded the 15-minute job limit"**: long clip at
  sample_fps 5 on CPU; suggest raising `confidence`/lowering `sample_fps` or
  trimming the clip.
- **Worker stopped** (`/health` returns 503): check `job.engine_failed` trace
  lines for the child's stderr tail, then restart the service.

## 4. Fix and verify

Reproduce against the running service (demo mode needs no auth):

```bash
curl -s -X POST http://127.0.0.1:8000/v1/media/url \
  -H "Content-Type: application/json" -H "Idempotency-Key: debug-$(date +%s)" \
  -d '{"url": "<the failing url>"}'
```

After any code change: `uv run --locked pytest tests/ -q` (two pre-existing
benchmark failures over network fixtures are known and unrelated), restart the
service, and rerun the failing scenario to green before claiming the fix.

## 5. Record it

Append one entry to `MEMORY_LOG.md` in the repo root: date, symptom, root cause,
fix, and verification result. Never delete earlier entries; the log is append-only
history for future sessions.
