# Plan 03 — Deliver a file-to-event CLI

**Status:** Not started. **Depends on:** Plan 02. **Delivers:** the first useful vertical slice: recorded CCTV → persisted core events and text.

## Work units

1. Implement file ingest with PyAV/FFmpeg PTS/timebase, asset hashes, dimensions and relative time. Handle variable frame rate, decode errors and unknown UTC; no `frame_number / assumed_fps` clock.
2. Implement the chosen ONNX detector adapter with verified preprocessing/shape/class mapping and native postprocessing. Load one session per compatible worker profile. Baseline scheduling is fixed and deterministic before adding adaptive gates.
3. Implement timestamp-aware tracking using audited MIT ByteTrack association ideas. Change motion/process covariance and lifetimes for elapsed time; distinguish observed-empty, unobserved and gap. Add a baseline constant-cadence comparison to detect regressions introduced by the adaptation.
4. Implement `object.present`, directed `line.crossed`, and `zone.dwell` as separate small plugins sharing observations. Use hysteresis, persistence and one stable episode ID, not one event per frame. Gate outputs by the validated allowlist from day one.
5. Persist reducer state/checkpoint and events through Plan 02's transaction; write deterministic template summaries with evidence offsets. Resume a job with its original run ID; explicit reprocessing gets a new run ID.
6. Add CLI commands for analyze/status/export-events. Configuration and model validation occurs before decoding. Use batch backpressure, bounded buffers and limited diagnostic track retention.

## Acceptance and evidence

- Analyze a licensed CCTV file and inspect event time ranges against the footage. Save a JSONL/DB query sample with provenance and a review video; do not claim a positive event on an unlabeled smoke sample proves recall.
- Timestamp fixtures: irregular intervals, empty detections, long skipped interval, backward PTS, reconnect/epoch reset and two nearby objects. Wrong unit-time tracking must fail the irregular-interval test.
- Dwell fixture: 59 seconds must not pass a 60-second threshold; >60 observed seconds must; a 20-second gap cannot supply missing dwell duration. Use asymmetric motion and perspective examples.
- Crossing fixture: jitter around the line, reverse crossing, U-turn and a jump across the line during a gap. Expected counts are independently labeled.
- Kill/restart around commit boundaries and show no duplicate logical event or skipped committed range. Reprocess under a new model and show histories remain separate.
- Benchmark complete file processing versus the same detector at source FPS; record CPU cost, throughput and output-quality differences rather than model FPS alone.

## Stop and handoff

`results/03.md` includes exact CLI commands, database evidence, core capability/quality status and measured resource use. This is an offline MVP. No live camera, web UI, model training or advanced activity claim yet.
