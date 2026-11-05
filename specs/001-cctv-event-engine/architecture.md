# Architecture: spend computation on observations, share the results

**Status:** Proposed design, not implemented. Read [spec.md](spec.md) for acceptance gates and [research.md](research.md) for evidence and limitations.

## A1 — The runtime is Python around native libraries

Use Python 3.11 initially for orchestration, state machines, plugins and API. FFmpeg/PyAV decode, OpenCV image operations and ONNX Runtime inference execute native code. Use explicit process/thread limits; the GIL is not a reason to rewrite tensor inference in Rust. Separate serving dependencies from PyTorch/export/training dependencies.

Proposed stack:

| Responsibility | Default | Escalation condition |
|---|---|---|
| Recorded decoding | PyAV over FFmpeg, preserving PTS/timebase | Hardware decoder only after profiling end-to-end copy costs |
| Live transport/record/playback | MediaMTX, compressed stream passthrough | More media nodes when tested bandwidth/IO/viewer capacity is reached |
| Object detector | YOLOX Nano then Tiny candidate, fixed ONNX graph | Larger model/higher-resolution ROIs if event recall fails; no speed-only selection |
| Inference | ONNX Runtime CPU, bounded threads, no idle spin by default | Native OpenVINO on measured compatible Intel hosts; TensorRT on measured NVIDIA GPU hosts |
| Tracking | Minimal timestamp-aware ByteTrack-derived association, MIT notices retained | Re-ID only when ID-switch errors justify its extra inference; no cross-camera identity |
| Activity logic | Small stateful plugins over shared observations | Separate process for expensive temporal models or fault isolation |
| Event store | PostgreSQL, native partitioned append-only facts/metrics | Optional TimescaleDB Apache edition, Redis numeric projection, ClickHouse analytics replica |
| Coordination | Local bounded queues; PostgreSQL transactions/outbox; local SQLite WAL spool when live | Kafka only for measured multi-consumer/replay/transport need |
| API | FastAPI, Pydantic, psycopg, explicit SQL migrations | No ORM/framework layer unless it reduces actual maintenance |
| UI | TypeScript + Vite + Preact, native video + hls.js | WebRTC for low-delay operator view if HLS delay is unacceptable |
| Monitoring | Prometheus-compatible endpoint, structured logs, benchmark JSON | Central collection when there are multiple nodes |

Do not preinstall all future services or heavy model families just to make this proposal executable. Each plan adds only its dependencies and extends `.agents/setup`/service declarations then.

## A2 — Separate media transport from semantic analysis

One ingest session may relay/record compressed main-stream packets and feed one analysis decoder for a selected substream. “Decode once” means once per compatible stream/profile, **not** that H.265 main-stream archiving needs pixel decoding. A separate main-stream ROI decode or specialist input counts as another measured cost.

Processing order:

1. MediaMTX relays/records RTSP packets. A file reader supplies equivalent timestamped input for batch.
2. Camera worker owns timestamp normalization, stream epoch and bounded decoded frame buffers.
3. Scheduler chooses detector observations from declared plugin requirements and measured resource budget.
4. Shared native inference session produces detections, then a timestamp-aware tracker produces trajectories.
5. Cheap rule plugins consume trajectories; expensive plugins request bounded crops/temporal clips only when enabled.
6. Event reducer assigns persistent IDs/revisions, enforces allowlists, formats text, and durably appends to spool/store.
7. Store transaction updates current events, history, outbox and committed checkpoint; UI reads events and independently plays compressed video.

Never send full decoded frames through REST, Redis or Kafka. A 1920×1080 RGB frame is about 6.22 MB; 25 fps is about 155.5 MB/s per camera before copies. A reference to a shared-memory slot is cheap, but has ownership and expiry rules. Start with camera-local buffers; add cross-process shared memory only when measured copying warrants it.

## A3 — Scheduling is an accuracy contract

Each plugin declares:

- Input types, object classes, required region/resolution and compatible model/tracker profile.
- Minimum/maximum observation cadence, maximum gap, temporal window and acceptable deadline.
- Whether motion gating is safe, whether it needs idle-scene polling, and whether image-space or world-space geometry is required.
- CPU/memory budgets and optional GPU class; startup fails if the scheduler cannot meet a mandatory capability.

For shared nodes, use the **union of requirements**: maximum necessary rate/resolution, not the most economical subscriber's rate. Share only when graph/model/preprocessing/class mapping/stream epoch are compatible. Selecting fewer class labels after inference usually does not make an unchanged neural network materially cheaper; pruning/training a smaller head is a later measured optimization.

Illustrative starting presets, to tune in Plan 01:

| Profile | Detector sampling | Tradeoff and guard |
|---|---|---|
| Low-latency core | 5 fps active, 1 fps idle refresh | Good starting point for geometric rules; still can miss brief events |
| Low-compute core | 2 fps active, 0.5 fps idle refresh | Lower CPU use; only activities validated at this cadence remain allowed |
| Temporal safety | Plugin-declared, e.g. a contiguous 8–16 fps crop window | Not automatically satisfied by 0.5–2 fps object observations |
| Recorded complete | Evaluate the declared sample schedule in source-time order | No overload dropping; can run slower than real time at bounded CPU |

These rates are hypotheses, not validated defaults. A one-second activity between two two-second polls is invisible. More waiting is not automatically less computation: sleeping changes utilization but not total CPU-seconds. Compute savings require doing less work, a more efficient kernel, reuse, or a lower-cost model at acceptable quality.

Motion gate: low-resolution luma difference/background model, ROI masks, exposure/shake rejection, and forced periodic refresh. Do not let background adaptation erase stationary persons. Existing tracks with pending dwell timers continue receiving confirmations. A fire/smoke pipeline cannot depend solely on a person detector trigger. Keep candidate negative/skip decisions measurable; sample skipped windows for audit only in explicitly authorized evaluation modes.

H.264/H.265 reference chains still need decoding even when downstream frames are dropped. `fps` filtering after decode saves inference, not necessarily decode. Camera substreams, camera-side FPS, hardware decode and longer offline batches address different costs. Keyframe-only scanning is optional coarse indexing and unsuitable for brief-event guarantees.

## A4 — Track in source time, not in function-call counts

Stock ByteTrack hard-codes a unit Kalman step and counts update calls for lifetime. Adaptive sampling must change transition/process-noise handling for elapsed time, use second-based expiration and expose three separate observations:

1. `observed(detections=[])`: the detector ran and found nothing.
2. `not_observed`: the scheduler skipped a frame; no negative evidence exists.
3. `gap`: usable source time is absent or uncertain; trajectories and activity continuity are interrupted according to policy.

Track keys are scoped to camera + stream epoch + processing run. A tracker ID is not a person's identity. Anchor footpoints for people and configured ground-contact points for vehicles; normalize geometry and store calibration version. Do not label running/speed from pixels-per-frame. World speed needs scene calibration; without it emit relative-motion candidates or disable the feature.

Dwell state accumulates only supported intervals between confirmations within the configured maximum gap. Store wall-span and observed duration separately. Crossing rules need direction, hysteresis, minimum movement and confidence before counting; no inferred crossing across a long unobserved jump. At a source/config reset close active episodes as interrupted, not normal exits.

## A5 — A small plugin interface, not a general DAG platform

Proposed Python-level contract (names are design, not existing code):

```python
class ActivityPlugin:
    manifest: PluginManifest
    def on_observation(self, observation, context): ...  # candidates, not DB writes
    def on_gap(self, gap, context): ...
    def snapshot(self): ...                             # versioned, bounded bytes
    def restore(self, snapshot): ...
    def close(self, reason, context): ...
```

Manifest: `plugin_id`, semantic version, input/output schema versions, capabilities/activity IDs, dependency profiles, timing/window requirements, budget and model artifact hashes. Initially use an explicit Python entry-point registry and simple dependency resolution; no visual DAG builder, distributed graph compiler, or universal plugin SDK.

The host owns timestamps, frames, model sessions, track lineage, persistence, evidence, allowlists and scheduling. Plugins own their activity state and typed payload. Plugins cannot open camera connections, instantiate hidden duplicate detectors, write directly to event tables, change the canonical clock, or retain unbounded frames. A reference-counted/frame-lease API has deadlines and releases buffers on plugin crash.

Effective semantic activities = instance allowlist ∩ pipeline allowlist ∩ plugin capabilities. Configuration fails if a requested entry is unsupported; do not quietly take an intersection that hides a typo. Defaults are deny-all. The dependency graph includes only reachable enabled work. Operational health output is mandatory and separate.

Hot configuration: validate, compile dependency requirements, admit resources, create immutable version, then switch at a source timestamp boundary. Removed activities' open events receive an administrative `ended/interrupted: configuration_changed` revision under their **old** config authority; no new episode may open afterward. Reused detector nodes stay alive while any subscriber needs them.

## A6 — Bounded backpressure and recovery

- Live decoder queue: bounded by bytes and source age. Prefer latest useful observation for low-latency work, but emit analyzed-coverage gaps when required cadence is missed. Never call the result “fully analyzed.”
- Batch queue: block/retry and preserve the requested schedule. Split only at safe boundaries with overlap and restored state; do not double count segment overlaps.
- Expensive plugins: separate deadline/budget so they cannot starve cheap essential rules. Admission rejects combinations that cannot meet their contracts.
- Live event spool: SQLite WAL with fsynced append and stable record keys before acknowledgement. Disk quota is required despite abundant storage. On full spool stop accepting durable-event claims, preserve recordings where possible, and surface degraded coverage.
- PostgreSQL drain: idempotent transaction writes event/revision/outbox/checkpoint. Crash after commit but before spool acknowledgement replays the same key.
- Host loss: local spool and unreplicated recordings may be lost. No zero-RPO claim until durable replication is deliberately configured. Record the exact RPO/RTO in deployment profiles.
- Multi-node ownership: a DB lease with monotonic fencing token per camera/processing partition. Store rejects stale-token writes. Lease loss interrupts the old worker and starts a new epoch/checkpoint policy.
- Webhooks: at-least-once delivery. Consumer dedup key is `(event_id, revision)`. Kafka's exactly-once processing does not automatically include PostgreSQL or HTTP receivers.

## A7 — Text is a rendering of versioned facts

Example only: “Camera gate-01: a person remained in loading-zone for 62 observed seconds; evidence is incomplete for 4 seconds.” The source payload stores activity, zone, track, timing, evidence support, confidence semantics and coverage. Store `summary_template_version` and language so summaries can be reproduced. Escape user-defined camera/zone names in UI; never treat text as executable markup.

Optional later video-language explanations run over shortlisted evidence, are labeled generated commentary, and cannot change the canonical activity or trigger enforcement. A cheaper model that cannot support the event is not repaired by a fluent description.

## A8 — Browser video does not go through the inference process

Use Preact for the event timeline/filter/review interface. Load hls.js lazily for HLS where native support is absent; `<video>` handles recorded MP4 and supported native HLS. MediaMTX handles media protocols, not the application worker.

Default live view: HLS for simple network traversal and smooth buffering; opt-in WebRTC for sub-second operator use, accepting signaling/ICE/TURN complexity and codec constraints. MediaMTX does not transcode codecs. Prefer a browser-compatible H.264 camera substream; H.265 recordings may require an on-demand H.264 review proxy. H.264 B-frames complicate WebRTC. A container being fMP4 does not guarantee the contained codec plays everywhere.

Record main stream without re-encoding. Keep timestamp/segment maps and independently record substream alignment uncertainty. For an event, request the covered recording interval with pre/post-roll, seek from the preceding keyframe, then move playback to the desired presentation time. Show actual seek error and gaps; do not subtract arbitrary video start times from UTC. Do not persist signed playback URLs; mint them from stable media IDs after authorization.

Video stays browser-decoded, not a canvas JPEG loop. Draw optional boxes in a lightweight overlay synchronized via `requestVideoFrameCallback` where available. Hide stale boxes when no observation supports the current frame. Pause invisible tiles and cap concurrent live decoders; a 100-camera grid should use thumbnails and selected live tiles, not 100 active streams.

## A9 — Why not Kafka, Rust or a VLM first?

**Kafka:** helpful for independent durable consumer groups and long replay windows; it cannot reduce detector FLOPs. Start with the transactional outbox. Add Kafka when measured sustained outbox lag/IO limits or cross-node replay/fan-out requirements justify operating brokers. Publish small event/track summaries and recording references, not frame tensors. Partition ordering is camera/run-scoped; no global ordering promise. Existing sample model inference measured milliseconds; a broker is not a remedy for that work.

**Rust:** first profile decode, inference, copies, Python rule CPU, allocator pressure and queue latency. Rewrite a narrow stable boundary only if Python-only work remains a material bottleneck (proposed trigger: >20% of total CPU after batching/vectorization). Benchmark the replacement against a frozen contract and event output set. Rewriting native ONNX inference orchestration alone does not make its kernels faster.

**VLM per frame/clip:** expensive, slow to inspect exhaustively, prone to unsupported semantic claims, difficult to calibrate false alarms. The narrow activity catalog gives a testable contract and cheaper deterministic text.

**Training a detector from scratch:** unnecessary until baselines fail a known domain requirement. Start with a licensed pretrained detector; first improve scene calibration, class mapping, observation quality and scheduling, then fine-tune on authorized examples.

**Custom everything:** write the application semantics, not another codec, tensor runtime, database, transport server or browser decoder. Reusing native building blocks is consistent with a small custom framework.
