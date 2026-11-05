# Avalokan handoff — 2026-10-15

## Resume here

The user asked to stop for the night and resume tomorrow. Do not continue
implementation, push, deploy, or schedule work until they return.

Repository: `krunalhp/avalokan`, checkout `/home/user/workspace/repo`, local branch
`main`. The experimental upload-to-events workbench is implemented and verified.
The four implementation/setup/specification commits are local only; the remote
has not received them. Push approval was requested but **not granted**. This
handoff is an additional local documentation commit. Do not discard local work
or replace this checkout with `origin/main`.

## Start the existing environment, not a fresh installation

```bash
git status --short
.agents/resume
amp orb services ensure
curl -fsS http://127.0.0.1:8000/health
```

Use the workbench portal printed by `ensure`, not the loopback URL. The declared
services are `avalokan-db` (PostgreSQL 15 on 55432) and `avalokan` (API, worker,
static UI on 8000). Shutdown order is app first, database second. The artifact
page server is optional; restart it with the creating-artifacts skill's
`scripts/share.mjs` when a human needs the handoff/research portal.

Dependencies, model, UI build, media and DB are already present. Run
`.agents/setup` only if missing or reconciling changed dependencies. Existing
data is under `.data/` and is not in Git; do not remove or reinitialize it.
Screenshots, recordings and the Noida sample are under `.amp/in/artifacts/`.
An orb pause preserves these; a new checkout does not include them.

The checked-in services enable **demo mode without application authentication**.
Portal viewers share clips/results. No sensitive footage. Token-mode API tests
pass, but this is not a multi-tenant production deployment.

## Read these before making changes

1. `specs/002-clip-workbench/spec.md`, `plan.md`, `tasks.md`: all 12 tasks complete
   for this narrow milestone, not for the parent roadmap.
2. `specs/002-clip-workbench/results.md`: measured checks and limitations.
3. `specs/002-clip-workbench/quickstart.md`, `contracts/api.md`, `extensions.md`:
   setup, API semantics and activity plugin contract.
4. `specs/001-cctv-event-engine/plan.md`: ten-stage roadmap. Recommended next
   development milestone is `plans/01-benchmark.md`, not speculative Rust/Kafka.
5. `.agents/skills/analyzing-cctv/SKILL.md`: loaded agent skill/client. Reload
   skills if this session has not discovered it.

Spec Kit uses Specify CLI 1.2.0 and `.agents/commands/`. Select explicitly with:

```bash
SPECIFY_FEATURE=002-clip-workbench .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

The constitution is an unratified template; there are no extension hooks.

## Implementation contracts

- Python/FastAPI/Pydantic; PyAV source presentation timestamps; checksum-pinned
  YOLOX Nano ONNX CPU; one inference thread; conservative consecutive-IoU tracking.
- Shared detections/tracks feed registry plugins `object.present`, `line.crossed`
  and `zone.dwell`. Explicit per-run allowlist, optional instance restriction.
- Fixed 1/2/5 fps sampling; missed detections/gaps break continuity. Tracks are
  not identities. Text is generated from typed facts, not free-form captioning.
- PostgreSQL owns durable jobs, immutable facts, occupancy time series and
  append-only reviews. Child attempts are fenced; results publish atomically.
  Restart retries the whole clip, at most three attempts; one worker per DB.
- Preact/native browser video. H.264 remux or bounded H.264 proxy for other
  supported codecs; original preserved. Upload, progress, seek/filter and review.
- API/client use clip-relative seconds, not capture UTC. Occupancy samples are
  gauges, not unique-person totals. Scores are not calibrated probabilities.

## Last verification

```bash
uv run --locked pytest -q
# 13 passed; one upstream Starlette/httpx deprecation warning
uv run --locked python -m unittest discover -s .agents/skills/analyzing-cctv/scripts
# 10 passed
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
npm --prefix web run build
# all passed
```

Real PostgreSQL tests isolate temporary schemas. Browser upload, playback,
seek to 2s, person filter, persisted review, error/running/empty/result states and
390px layout were exercised and inspected. An interrupted job completed on
attempt two without partial events. Warm setup: 3.19s and 3.16s; resume immediate.

Sample job `6a7ec09e-065f-42a1-a80f-ff3490613788`: 12 events, six occupancy samples,
0.460s analysis wall / 0.451s CPU, 0.600s child processing with cached playback.
Noida footage consists of 30 CC BY 4.0 frames assembled at synthetic 10 fps;
original timing is unknown. These are smoke measurements, **not accuracy or
capacity evidence**. Source attribution is in the parent research document.

Recovery/proxy job `0bd18079-c9c8-454e-8bef-8b8323efacb1`: synthetic repeated
60-second clip, attempt two completed. Browser review job
`f60fa390-11e6-43a0-a399-754a4e3a12aa`: nine presence events, including a persisted
test uncertain review. Leave these demo records available for inspection.

## Outstanding decisions and limits

- No push, PR, merge, deployment or secret changes authorized. Ask before remote
  delivery; future fresh orbs do not inherit setup until it reaches default branch.
- No labeled, scene-separated accuracy evaluation or sustained scalability test.
  All activities remain experimental. No safety/intent/crime claims.
- Live RTSP/HLS, specialist fall/fight/fire/PPE detection, adaptive sampling,
  Redis projection, distributed workers, training and production hardening are
  deferred. No deletion/retention API yet.
- Immediate orb pause is not exposed by the available tool/CLI. Application
  services are stopped for the handoff; Amp automatically pauses after both
  five minutes without agent work and twenty minutes without user/portal
  interaction. Do not archive the thread merely to force a pause without the
  user's explicit archive request.
