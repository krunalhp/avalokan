# Workbench verification — 2026-10-15

Scope: a working **experimental upload-to-events slice**, not completion of the
parent ten-stage production roadmap. Implementation and verification took place
in a Linux x86-64 Amp orb, Python 3.11.14, Node 26.10.0, PostgreSQL 15. Model
artifact SHA-256: `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`.

## Automated checks

- `uv run --locked pytest -q`: 13 passed. Real PostgreSQL disposable schemas;
  source PTS sampling, gaps, dwell boundaries, crossing jitter/directions,
  custom plugin registration, per-instance/run allowlists, malformed uploads,
  authentication/cookies/media access, size bounds, idempotency conflicts,
  recovery/stale-attempt rejection, half-open event overlap/cursors and reviews.
  One upstream Starlette/httpx deprecation warning remains.
- `uv run --locked python -m unittest discover -s .agents/skills/analyzing-cctv/scripts`:
  10 passed. Client authorization flags, errors/deadlines, pagination and safe
  request behavior. The bounded-pagination regression failed before fixing the
  cursor that skipped unreturned records, then passed after the fix.
- `uv run --locked ruff check src tests` and `ruff format --check src tests`: pass.
- `npm --prefix web run build`: TypeScript and Vite pass; 46.48 kB JS and 10.24 kB
  CSS before gzip. `bash -n .agents/setup .agents/resume`: pass.
- Spec Kit prerequisite check with `--require-tasks --include-tasks`: pass.
  No extension hooks configured; constitution remains unratified.

## Actual inference, API and restart

The downloaded TrafficCAM Noida frames are CC BY 4.0; source, attribution and
selection caveats are in [research](../001-cctv-event-engine/research.md).
Thirty frames were assembled at **synthetic 10 fps**, 1920×1080, into a 3-second
test video. Original frame timing is unknown. This verifies the software path,
not real-world dwell/crossing accuracy or representative capacity.

The skill client uploaded the sample, submitted an explicitly allowlisted job,
waited for completion, and fetched persisted events and occupancy. UI upload
created a separate presence-only run with nine events. A final all-activity run
`6a7ec09e-065f-42a1-a80f-ff3490613788` produced 12 events and six occupancy samples:

| Final sample run | Measurement |
|---|---:|
| Decoded / analyzed frames | 30 / 6 |
| Analysis wall / CPU seconds | 0.460 / 0.451 |
| Total processing inside child | 0.600 s |
| Playback preparation | already cached, effectively zero |
| Sampling / inference threads | 2 fps / 1 |

Total processing includes checksum, playback preparation, model initialization,
analysis and result inserts, but excludes queue wait, process startup and the
final transaction commit. Analysis CPU excludes model startup and FFmpeg's
subprocess cost. An earlier fresh H.264 remux took 0.106 seconds. These are smoke
measurements, not a claim of speedup over another system.

A separate disposable test repeated/downscaled the sample into a **synthetic
60-second, 640×360 MPEG-4** clip. Job
`0bd18079-c9c8-454e-8bef-8b8323efacb1` was interrupted while running by restarting
the API service. Before restart it had zero published events. It completed on
attempt two with 346 events, 600 decoded / 300 analyzed frames, 4.534 s analysis
wall time, 4.326 s analysis CPU, 1.027 s H.264 proxy preparation and 5.684 s total
processing. Progress was observed at 0%, 18%, 62% and completion. Repeated imagery
is not an accuracy or sustained-load corpus. Browser proxy metadata reported
duration 60 seconds and readyState 4.

## Browser checks

Real Chromium with a moving pointer, desktop 1440×1000 and narrow 390×844,
both DPR 2. These are browser viewports, not real mobile-device tests.

- Uploaded the actual Noida clip through the UI; job completed and results appeared.
- Native play advanced currentTime from zero to 0.404 s. Selecting a later event
  moved currentTime to 2 s; the sample duration is 3 s.
- Person filter returned two of nine events. The selected event exposed source
  bounds and provenance. A test `uncertain` verdict/note was appended and survived
  page reload and service restart (also confirmed through the API).
- Invalid MP4 upload displayed “Cannot read video; use a valid MP4, MOV or MKV
  clip” while preserving the previous playback/results.
- Running state disclosed atomic publication and playback preparation. Empty
  selection showed no fabricated events. Completed result/details and geometry
  controls rendered. Narrow overflow was found and fixed: document scrollWidth
  is now 390 for a 390px viewport; metadata stacks without clipping.
- Captures and the interaction recording/contact sheet were inspected. Review
  artifacts in this thread: `.amp/in/artifacts/workbench-{empty,running,results,error,narrow}.png`
  and `workbench-review.mp4` / `workbench-review.loop.webp`.

## Orb setup

Setup ran repeatedly; final timed runs were 3.19 s and 3.16 s on the prepared
filesystem. They reused Python packages/model and rebuilt the small UI. Resume
finished in 0.00 s at the timer's precision. A clean non-interactive login shell
resolved repository `.venv/bin/python` (3.11.14), Node and Specify. Both supervised
services respond after `amp orb services ensure`. This is an idempotence/warm
environment check, not a measured cold boot on another fresh orb.

## Remaining qualification and delivery

No labeled accuracy evaluation, 100-camera-hour corpus, sustained capacity test,
live stream ingestion, distributed concurrency, adaptive sampling, Redis
projection, specialist safety models, browser-engine matrix, multi-tenant auth
or production rollout was performed. Token mode has API tests; the browser
workflow used the explicitly disclosed demo mode. No sensitive footage was used.

The orb demo has no application authentication and shares data among portal
viewers. Code/setup must reach the default branch before future orbs inherit
them; local commits alone are not deployment or remote delivery. Do not mark the
parent roadmap's quality/performance/production gates complete from these results.
