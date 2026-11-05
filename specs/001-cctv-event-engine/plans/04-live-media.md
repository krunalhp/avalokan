# Plan 04 — Add live CCTV and durable evidence without re-encoding everything

**Status:** Not started. **Depends on:** Plan 03. **Delivers:** RTSP analysis, original compressed recordings, explicit gaps and evidence playback contracts.

## Work units

1. Add a pinned MediaMTX service and local RTSP fixture publisher through supervised orb services. Production camera connections remain explicit operator configuration; no camera discovery/scanning.
2. Record main-stream packets, analyze a configured compatible substream, and catalog immutable segments with hashes, codec/GOP metadata and source-time maps. Prefer passthrough; measure rather than assume no transcoding is needed.
3. Normalize presentation time with stream epochs and optional UTC anchors. Track main/substream alignment and uncertainty. Camera overlays are display text, not authoritative timestamps.
4. Implement bounded latest-useful-frame scheduling for live input, reconnect/backoff, camera health and coverage gaps. Add SQLite WAL event spool, bounded disk policy and transactionally idempotent draining.
5. Resolve event evidence across segment boundaries, include pre/post-roll, and support pinned immutable clips plus expiration states. Protect recording files from independent cleanup while a pin is being created.
6. Add graceful shutdown: finalize durable state, interrupt unconfirmed episodes, release buffers and avoid resetting other cameras. Document local-host-loss RPO explicitly.

## Acceptance and evidence

- Loop a timestamp-known licensed file as RTSP; compare offline/live event boundaries, accounting for real ingest delay without changing occurrence timestamps.
- Drop/reconnect the stream with repeated PTS, introduce delay/out-of-order packets, and change resolution/codec. No cross-epoch track or wrong-evidence linkage survives.
- Disconnect PostgreSQL and restore it; after spool drain, each logical revision appears once. Fill the test spool quota and verify visible degradation rather than false durability.
- Review an event spanning two recording segments and one gap; measure seek offset. Expire an unpinned asset, preserve a pinned one, and verify catalog states.
- Slow one plugin and prove recording/live analysis queues stay bounded. Main/substream skew is visible, not silently aligned by arrival time.

## Stop and handoff

Record media service versions, readiness checks, codec compatibility and recovery results in `results/04.md`. Media endpoints remain protected/internal; user-facing playback is Plan 06. No remote deployment or real-camera reconfiguration is implied.
