# Plan 06 — Review event timelines with smooth browser video

**Status:** Not started. **Depends on:** Plan 05. **Delivers:** a usable authenticated single-site application and integration API.

## Work units

1. Implement the scoped FastAPI surface in [data-model.md](../data-model.md), with JSON Schema/OpenAPI, resource limits, server-side tenant authorization and scoped media capabilities. Establish operator/reviewer/admin roles; keep provisioning secrets private.
2. Build a small Vite/Preact interface: camera list/health, time/activity/zone filters, paginated event timeline, selected-event detail, evidence player and review action. No large admin dashboard or visual pipeline builder.
3. Use native `<video>` for recorded MP4/native HLS and lazy hls.js otherwise. MediaMTX serves video separately. Default to HLS live view; add WebRTC only when latency needs justify it and its connectivity/codec behavior is tested.
4. Implement source-PTS-to-player mapping, pre/post-roll and overlays tied to the presented frame. Show missing/expired evidence, unsupported codecs, UTC uncertainty, source gaps and stale predictions explicitly. Persist only stable media identifiers.
5. Add SSE updates with cursor recovery/polling fallback, keyboard-accessible review, local timezone display and API-backed immutable feedback. Pause offscreen video and cap concurrent decoder tiles.
6. Add signed retried webhooks and delivery status using the outbox. Validate destinations against SSRF/network policy; bounded retries/dead-letter handling, not blocking inference on a third-party HTTP call.

## Acceptance and evidence

- Real browser end-to-end: filter events, select one, play pre-roll, seek to evidence, pause/resume, review/correct, reconnect updates. Verify request authorization and DB state as well as screenshots.
- Record and inspect the full pointer/keyboard interaction; inspect desktop/narrow states and loading/empty/error/expired/gap states. Test actual HLS segments and video playhead progress, not just a `<video>` element existing.
- Attempt cross-tenant event/media access, expired capabilities, traversal, invalid webhooks and untrusted upload URLs. Confirm failures are server-side.
- Measure query latency and playback startup on declared fixtures. Test timeline alignment across segment boundaries and camera-clock discontinuity.
- Chromium/Firefox can be checked in an available browser runner; Safari/iOS require compatible real runners/devices. Record untested targets rather than claiming universal codec support.

## Stop and handoff

`results/06.md` contains screenshots/recording, executed browser/API checks and codec/device matrix. This is the single-site product checkpoint. No public deployment or live external webhook submission without authorization.
