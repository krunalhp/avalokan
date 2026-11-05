# Avalokan: CCTV video to structured event timelines

**Status:** Draft for implementation in sequential stages; no production engine exists yet.

**Version:** 1.0 · 2026-10-15

**Scope:** Fixed CCTV cameras, recorded CCTV files, and India deployment conditions.

**Execution order:** [plan.md](plan.md). Technical decisions: [architecture.md](architecture.md). Evidence: [research.md](research.md). Storage contracts: [data-model.md](data-model.md).

## Goal and recommendation

Build a small framework that turns CCTV into searchable, timestamped facts and activity episodes, with text and playable evidence. Optimize useful events per CPU-second at an explicitly measured accuracy, not model FPS alone. Preserve the original video because storage is available; do not repeatedly analyze it for every feature.

Use a shared detector and timestamp-aware tracker for inexpensive geometry/time rules. Invoke specialized temporal models only for enabled activities and relevant regions. Generate text from typed event fields, not from a general video-language model on every frame. Run on a single CPU host first; make a GPU or additional workers an optional capacity improvement.

The core output is an **observation**, not a declaration of intent, identity, guilt, or certainty. “Person remained in gate zone for 62 observed seconds” is supportable. “A thief is planning a burglary” is not.

## Current repository and boundaries

`VideoAnalysis.ipynb` demonstrates HOG person detection and labels movement from raw pixel displacement. Its IDs are not stable track identities, its speed threshold depends on frame rate and perspective, and it has no event storage. `YOLO11_Tutorial.ipynb` is a tutorial, not a production pipeline. Neither is a baseline for claimed production accuracy. Keep these notebooks intact as references.

The installed notebook environment includes Ultralytics. That does not select its AGPL-licensed models for the production framework. The production runtime and training/export tools should have separate dependency groups when implemented. No trained model, end-to-end benchmark result, database deployment, or production UI is delivered by this specification.

## User scenarios and acceptance

### US1 — Analyze a recorded CCTV file (P1)

An operator supplies a file, camera calibration, and allowed activities. They receive structured events, human-readable summaries, and evidence time ranges without supplying a cloud AI account.

- Given the same asset, run ID, configuration, model artifact, and checkpoint, retrying interrupted processing does not duplicate committed events.
- Given a line crossing at a known source time, the event refers to that source position, not the wall time when the batch job ran.
- Given an uncalibrated/unknown capture date, relative playback timestamps remain valid and UTC is explicitly unknown.
- Given a missing model, unsupported codec, or incompatible activity, validation fails before a job silently skips the requested feature.

### US2 — Attach multiple activity pipelines to one camera (P1)

One camera runs intrusion and dwell rules while another runs vehicle counting. Adding a rule reuses compatible detector/tracker results; unrelated activities and models remain disabled.

- An empty allowlist enables no semantic activities. Unknown IDs are errors; a missing allowlist is an error, not “enable everything.”
- A plugin emitting an activity outside its declared capabilities or effective allowlist is rejected and produces a health/audit record.
- Enabling an incompatible temporal model either admits its additional resource budget or rejects the change with a reason.
- Each active event retains the rule/config version that created it; a configuration change cannot silently rewrite history.

### US3 — Run live within a resource budget (P1)

An operator selects low-latency or low-compute processing and sees coverage, lag, CPU usage, and gaps, not only alerts.

- A stalled live worker sheds stale analysis work within configured limits rather than accumulating an unbounded queue.
- A recorded batch job slows down or pauses instead of dropping observations required by its configured sampling policy.
- A camera disconnect creates a coverage gap; the system cannot report that nothing happened during that gap.
- A long stationary person remains eligible for dwell detection even when the background subtraction gate sees no motion.

### US4 — Find events and review the original video (P1)

Filter a camera timeline by time, activity, zone, processing version, and review status; select an event to play pre-roll and post-roll evidence.

- Distinguish provisional, ended, interrupted, retracted, and human-reviewed observations.
- Show expired evidence as expired; never point silently at a different recording after reconnect or filename reuse.
- Default display timezone is `Asia/Kolkata`; stored UTC values retain their original source and uncertainty. Relative-only recordings are not assigned a fabricated date.
- A user authorized for one site cannot query or play another site's material through a copied URL.

### US5 — Add a new detector without editing the engine (P2)

A developer declares a plugin's inputs, temporal requirements, emitted activities, event schema, resource limits, and artifact versions; implements the small plugin interface; and installs it through the registry.

- Contract tests run the plugin against deterministic input observations, gap/reset messages, and shutdown/config changes.
- A crash or timeout marks only the affected pipeline degraded; it cannot hold frame buffers forever or stall all cameras.
- Unsupported schemas and unsafe executable model formats are refused at admission. Plugins are trusted installed code, not arbitrary code uploaded by dashboard users.

### US6 — Improve accuracy with review, not silent self-training (P2)

Reviewers correct events and label missed examples. An offline training process uses authorized footage, tracks data/model lineage, and proposes a version for shadow evaluation.

- Predictions are not automatically treated as ground truth.
- A changed model does not replace the active model until held-out gates and an explicit promotion pass.
- Model rollback and historical reprocessing preserve the old events and identify which result set is authoritative.

## Activity catalog and capability gates

“Supported” means a named activity passed its camera/domain evaluation. A model accepting an image is insufficient. Every activity declares minimum visible object size, camera geometry, cadence, uncertainty behavior, label requirements, and supported conditions.

| Activity IDs | Method and observable meaning | Delivery stage and limits |
|---|---|---|
| `object.present`, `zone.entered`, `zone.exited`, `line.crossed` | Detection, track anchors, zone/line hysteresis | Core; human/vehicle classes supported by the selected model; no identity |
| `zone.dwell`, `zone.intrusion` | Sustained observed presence; intrusion means entry into an operator-defined restricted zone/time | Core rules; “loitering” is a configured dwell threshold, not intent |
| `vehicle.stopped`, `vehicle.wrong_way` | Persistent stationarity or motion against a configured direction | Traffic rules; calibration and minimum displacement; no legal conclusion |
| `queue.long`, `crowd.threshold` | Observed persons in a calibrated queue/area above a threshold | Rule pack; image-plane count is not calibrated people/m² or proof of queue membership |
| `object.unattended_candidate` | Persistent object with a separately evaluated interaction/ownership heuristic | Experimental later pack; cannot infer abandonment from detector class alone |
| `person.fall_candidate` | Pose/trajectory plus temporal posture change and persistence | Specialist pack; distinguish sitting, bending, occlusion, camera motion |
| `person.fight_candidate` | Temporal interaction model over person pairs/groups | Specialist pack; requires domain footage and human review; not boxing/dancing/rough play inference from one frame |
| `fire.candidate`, `smoke.candidate` | Dedicated trained visual model and temporal confirmation | Specialist pack; never a certified life-safety system or substitute for sensors |
| `ppe.missing_candidate`, `restricted_area.proximity` | Custom class models and calibrated worker/equipment zones | Industrial pack; deployment-specific training, visible equipment and PPE |
| `traffic.signal_violation_candidate` | Track crossing plus synchronized signal state and road calibration | Custom traffic extension; unavailable without signal data/calibration |
| `scene.change_candidate` | Per-camera baseline deviation, separately calibrated | Experimental anomaly triage, never generic “abnormality detection” guarantees |

Metrics such as occupancy, throughput, queue length, and dwell histograms are numeric observations/rollups, not an event emitted for each frame. Health events such as `source.offline` and `analysis.coverage_gap` are in a separate mandatory operational namespace, not bypasses for semantic allowlists.

### README use-case coverage

| README promise | Concrete delivery | Explicit boundary |
|---|---|---|
| Real-time detection | Shared object detection, bounded latency, declared capacity | No universal cameras-per-host claim |
| Activity recognition | Geometry rules first; temporal specialist packs later | Fighting/falling require different models from object detection |
| Anomaly detection | Named candidate events and optional per-scene change detector | No general interpretation of every unusual behavior |
| Automated and assisted learning | Automatic candidate mining, assisted labels, offline retraining, explicit promotion | No unattended production self-training |
| API integration | Versioned event/query/config endpoints and signed retried webhooks | No per-frame HTTP API in the hot path |
| Cloud/edge scalability | Single-node runtime, quotas, fenced worker ownership, optional durable event bus | No Kubernetes/Kafka prerequisite |
| Custom models | Versioned artifacts with license, input/output and evaluation manifests | Not arbitrary remote code execution |
| Retail | Dwell, occupancy, queue, restricted area, reviewed unattended-object candidates | No automatic theft accusation |
| Traffic | Flow/counts, stopped/wrong-way candidates, later signal integration | No vehicle identity/ANPR or enforceable speeding without separate scope |
| Public/industrial safety | Reviewed fall/fight/fire/PPE/proximity packs | No autonomous emergency dispatch or certified safety claim |
| Smart cities | Aggregation across explicitly authorized camera deployments | No cross-camera person re-identification or city-wide identity tracking |

## Functional requirements

- **FR-001 Ingest:** Accept RTSP and local H.264/H.265 files, preserving presentation timestamps and stream metadata. Catalog unsupported formats and codec faults explicitly.
- **FR-002 Shared work:** Within a camera worker, share a compatible decode/detect/track node among its subscribers; do not instantiate one detector per rule.
- **FR-003 Model contract:** Record model hash, preprocessing, class mapping, runtime/provider, precision, thresholds and tracker/rule versions for every processing run.
- **FR-004 Time:** Preserve source presentation time, stream epoch, optional capture UTC and uncertainty, receive time, and processing/commit time as distinct quantities.
- **FR-005 Scheduling:** Support declared cadence floors/ceilings, motion gating with periodic refresh, activity-specific deadlines, bounded queue sizes and per-camera fairness.
- **FR-006 Resource modes:** Support low-latency live, low-compute live, and complete recorded-batch modes. Report the tradeoff and effective sampling, including requested work not executed.
- **FR-007 Tracking:** Use real elapsed time; distinguish “observed with no detections,” “not sampled,” and “source unavailable.” Reinitialize on discontinuity.
- **FR-008 Activities:** Implement the activity catalog incrementally; never advertise a research-only/disabled plugin as supported.
- **FR-009 Lifecycle:** Stable event IDs, monotonic revisions, typed activity payloads, explicit closure reason, observed support and evidence references; deterministic text is derived from those fields.
- **FR-010 Allowlists:** Validate instance and pipeline allowlists, capabilities, dependencies and resource admission before activation; enforce again at persistence.
- **FR-011 Plugin isolation:** Timeouts, bounded memory, version compatibility, dependency reuse, state checkpoint/reset, and per-plugin error reporting.
- **FR-012 Durable writes:** Use idempotent writes, persistent replay identifiers and atomic event/revision/outbox/checkpoint transactions. Define the data-loss boundary under host loss.
- **FR-013 Evidence:** Retain compressed originals independently from analysis; immutable media identifiers, checksums, timestamp maps, policy-controlled deletion and evidence pinning.
- **FR-014 Query:** Time-overlap queries, keyset pagination, typed filters, run/model provenance, and separate canonical versus historical result sets.
- **FR-015 Metrics:** Store numeric observations and idempotent corrected aggregates separately from events. Unknown coverage is not zero occupancy.
- **FR-016 Browser:** Smooth browser-native live/replay video, accurate source-time seek mapping, timestamp-aligned overlays, expired/gap/unsupported states, keyboard controls.
- **FR-017 API:** Versioned contracts, authentication, site-scoped authorization, scoped media access, audit logs and bounded uploads/jobs.
- **FR-018 Delivery:** Durable webhook delivery with event/revision idempotency keys, bounded retries and a dead-letter state; optional stream adapters later.
- **FR-019 Operations:** Camera health, analyzed coverage, detector calls, CPU-seconds/video-hour, RSS, queue lag, per-stage p95 time, event false alarms and consumer lag.
- **FR-020 Review:** Corrections/retractions are append-only review records; preserve original model facts and reviewer rationale, without overwriting provenance.
- **FR-021 Learning:** Authorized data manifests, scene-disjoint evaluation, training isolation, shadow/canary rollout and rollback; no training in serving workers.
- **FR-022 Scale:** Explicit camera ownership, fenced leases, bounded spool/replay, graceful shutdown and resource-aware scheduling; no raw-video broker transport.
- **FR-023 Privacy:** Purpose-limited allowlists, least privilege, secrets outside configs/logs, retention/deletion workflows, export audit, and optional display masking.
- **FR-024 Offline operation:** Local event production and recording work without external AI or telemetry services. External integrations must be opt-in.

## Performance and accuracy acceptance

These are **proposed release gates**, not measurements or promises of current capability. Plan 01 freezes a hardware/camera workload card before testing. Report unsupported conditions rather than lowering accuracy silently.

| Criterion | Initial target and test |
|---|---|
| Semantic quality | For each released core activity: event precision ≥95%, recall ≥90%, with class-specific matching tolerance fixed before evaluation; report confidence intervals and raw counts |
| False alerts | ≤0.1 false alert episodes per evaluated camera-hour for alerting core rules; report separately per camera/day/night condition, not one pooled number |
| Exposure | Aim for ≥100 held-out camera-hours, ≥10 independent fixed cameras and ≥100 positive examples per released activity; insufficient coverage means “experimental,” not a passed release |
| Live timeliness | p95 processing lag ≤2 s for core geometric rules after the last required observation, at the **admitted** camera count; excludes configured dwell/confirmation interval, reported separately |
| Temporal correctness | No duration accumulated through declared unknown gaps; event boundary error separately reported against annotated source time |
| Efficiency | Target ≥3× lower CPU-seconds/video-hour than the same selected detector at source FPS, with ≤2 percentage-point recall degradation and absolute gates still passing; narrow claim to measured activity/scene strata |
| Low-compute mode | Seek ≥30% lower CPU-seconds/video-hour than the selected low-latency mode at equal quality, accepting higher declared delay; publish a non-winning result if no such profile exists |
| Shared rules | Adding a rule needing identical observations must not add detector invocations; measure rule overhead and allocations rather than demanding a fabricated zero-cost plugin |
| Resource control | No unbounded queue/spool; quotas enforced under camera bursts and DB outage; 24-hour soak shows bounded memory after warmup |
| Query/replay | Initial target: event-list API p95 <250 ms at 1M events on the declared test host; event video starts within 2 s on a controlled LAN/browser after access authorization |
| Recovery | Crash/retry produces one logical revision per persisted replay key; stale owners cannot write after a new fencing token is issued |

Compute limits, number of cameras, bitrates, minimum object size, event sensitivity, and retention are configurable site decisions. Initial benchmark profiles are 1/4/16 cameras and 1/2/4 worker threads on the available CPU, stopping at saturation. **Sixteen cameras is a test point, not a promised capacity.**

## Failure and edge cases to test

- Stationary people, leaves, rain, shadows, headlights, insects, camera shake, PTZ movement, blocked lens, darkness and monochrome IR.
- Small distant pedestrians, mixed two/three-wheelers, crowded overlap, vehicles outside expected lanes, no useful depth calibration.
- Boundary jitter, two crossings in opposite directions, U-turns, track merge/split, late confirmation, and long occlusion.
- Duplicate/backward/wrapped timestamps; B-frame reorder; variable FPS; source reconnect with repeated timestamps; unknown recording start time.
- Slow rule, incompatible models, shared-model subscribers with different cadence, removed allowlist entry while an event is open.
- Retried batch, model upgrade, DB unavailable, spool full, disk full, expired/pinned evidence, process crash between local append and database commit.
- Day-boundary/DST/timezone display, events spanning query windows, corrected event start time, concurrent reviewers, and revoked media authorization.

## Assumptions and decisions still requiring field data

1. Fixed elevated CCTV is the initial scene. PTZ movement pauses geometry rules until stabilization/recalibration; supporting moving cameras is a separate project.
2. CPU-first Linux x86-64, one site/host initially; dedicated production hardware is not yet specified. An Intel-specific accelerator cannot be assumed on every host.
3. Model choice remains provisional until Indian CCTV quality is measured. YOLOX Nano/Tiny are the first permissively licensed candidates; their small-object limitations may require a larger model or higher-resolution ROI.
4. Proposed retention defaults for a trial: recordings 7 days, events 90 days, diagnostic tracks 24 hours, review pins 30 days. These are configurable suggestions, not legal requirements or permission to retain real footage. Space availability does not remove privacy obligations.
5. Public India datasets support smoke tests and some detection evaluation; they do not establish long-duration event false-alarm rates. Authorized field recordings are a release dependency.
6. The project constitution remains an unratified Spec Kit template. The measurable gates here govern this design proposal; do not claim organizational ratification.

## Out of scope

Face recognition, identification by sensitive attributes, cross-camera person identity, license-plate recognition, audio surveillance, autonomous police/emergency action, arbitrary natural-language crime detection, and a full training/data-labeling platform. Video-language models may later explain already supported evidence for a reviewer, but must not define the durable event truth or run continuously by default.
