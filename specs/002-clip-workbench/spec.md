# Feature: CCTV clip workbench

Created 2026-10-15. Status: locally implemented and verified; see [results](results.md).

This milestone implements the user's upload → analyze → query workflow from
the broader [engine design](../001-cctv-event-engine/spec.md). It does not claim
completion of all ten research/production plans. All detectors/rules remain
experimental until labeled, scene-separated evaluation passes.

## User stories

### US1 — Upload and analyze (P1)

Upload a local MP4/MOV/MKV CCTV clip, explicitly select allowed activities,
start a durable background job, and see progress or a useful failure. Use source
presentation times, not frame number/FPS or fabricated capture UTC. Limits:
250 MiB, ten minutes, 4K, eight pending jobs. Never fetch arbitrary media URLs.

Acceptance: a real Indian CCTV clip produces persisted object-presence events;
an empty allowlist emits no semantic events; invalid files/configurations fail;
repeating an idempotency key returns the same job or conflicts on changed input.

### US2 — Review facts alongside video (P1)

Play a browser-compatible recording, select an event to seek, filter by activity
or class, inspect provenance, and append a human verdict. Provide loading,
queued/running/failed, empty, and completed states at desktop and narrow widths.
Do not equate a model score with calibrated confidence or identity.

Acceptance: real playback advances and seeking follows the event source offset;
filters change returned events; review survives reload; HTML in filenames/text
is escaped. An unsupported source codec gets a bounded review proxy, preserving
the original. Transcoding is not counted as free analysis.

### US3 — Agent API and skill (P1)

Provide versioned OpenAPI endpoints for media, jobs, event overlap queries,
event details/reviews and sampled occupancy. A repository skill supplies a small
CLI client, safe credential handling, polling deadlines, pagination and factual
reporting with evidence references.

Acceptance: the skill client uploads a file, starts/waits for a job, queries
events and occupancy. Unauthorized requests fail outside explicit local demo
mode. Missing allowlists and unknown capabilities are rejected.

### US4 — Change activities without changing transport/storage (P1)

Small Python activity classes consume shared timestamped tracks and emit typed
candidates. The registry supplies capability metadata; the host validates and
enforces the allowlist. Presence, vertical-line crossing and rectangular-zone
dwell are initial experimental plugins. Geometry is normalized and configurable.

Acceptance: adding a test plugin needs no API/worker rewrite; one detector call
feeds all enabled activities. Gap/empty detections cannot accumulate dwell or
invent crossings. One process and one native inference thread bound compute.

## Engineering boundaries

PostgreSQL is authoritative. Media stays on local disk. Batch results publish
atomically at completion, with deterministic run-scoped event IDs; a crashed
worker retries the whole clip, not a partial tracker checkpoint. Failed runs
publish no partial success. Original files, config, model hash and source-time
basis are retained. Single-site, trusted operators; API token or explicit demo
mode, not a multi-tenant production identity system.

Deferred: live RTSP/MediaMTX/HLS, adaptive sampling, ByteTrack, safety specialists,
Redis projections, webhooks, distributed leases, retention automation, training
and production accuracy/capacity qualification. The simple timestamp-aware IoU
tracker is a replaceable baseline, not a claim that crowded-scene tracking is
solved. Fixed 1/2/5 fps sampling can miss short events; skipped frames still cost
decode. No motion gate is enabled without quality evidence.

## Verification gates

Run real PostgreSQL API integration tests, source-time/plugin boundary tests,
actual ONNX inference on the downloaded sample, the skill client against the
running stack, and browser upload/play/seek/filter/review checks. Record wall and
CPU cost without claiming accuracy or all ten roadmap stages complete.
