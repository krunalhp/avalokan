# Sequential implementation roadmap

**Status:** No full-stage acceptance gate has passed. At the user's request, an
experimental upload-to-events slice spanning parts of 02/03/05/06 is now locally
implemented in [002 — Clip workbench](../002-clip-workbench/spec.md), with
[verification evidence](../002-clip-workbench/results.md). The research probe is
not Plan 01 completion; start there for the next quality/performance milestone.
**Specification:** [spec.md](spec.md) · [architecture](architecture.md) · [data model](data-model.md) · [research](research.md)

## How to execute

Run one numbered plan at a time. Each plan produces a useful checkpoint, tests, measured evidence, and a handoff to the next. Do not begin later plans merely because their files exist. Example instruction: **“Implement Plan 01 from specs/001-cctv-event-engine/plans/01-benchmark.md; stop at its acceptance gate.”**

At the start of each stage, read the spec, that stage, and the preceding result; inspect the actual repository because module paths below are proposed ownership boundaries, not existing code. At completion, record commands/results/limitations in a small `results/NN.md`, update the plan's status, and commit a coherent local checkpoint. Do not push/deploy or operate real camera infrastructure without the corresponding authorization. Failed model quality or unavailable datasets must be recorded, not hidden by moving ahead with a “supported” capability.

The two existing local setup/Spec Kit commits remain unpushed. This specification does not grant permission to push them or itself.

## Stages and dependencies

| Stage | Outcome | Depends on | Approximate scope, not a time estimate |
|---|---|---|---|
| [01 — Benchmark and data](plans/01-benchmark.md) | Reproducible India CCTV corpus, model/runtime/cadence Pareto comparison | Existing orb setup | Medium; data access is the largest uncertainty |
| [02 — Contracts and durable storage](plans/02-contracts-storage.md) | Versioned event/config/time schemas, PostgreSQL store and replay tests | 01 | Medium |
| [03 — Offline event engine](plans/03-offline-engine.md) | One file → detection/tracks → core events/text → DB | 02 | Large; timestamp/track semantics matter |
| [04 — Live feed and evidence](plans/04-live-media.md) | RTSP, compressed recording, continuity gaps, replayable evidence | 03 | Medium |
| [05 — Plugins and rule packs](plans/05-plugin-rule-packs.md) | Shared observations, allowlists, retail/traffic geometry rules | 04 | Large; add one rule at a time |
| [06 — API and lightweight UI](plans/06-api-ui.md) | Authenticated timeline, smooth live/replay, review and webhooks | 05 | Large |
| [07 — Specialized activities](plans/07-specialist-activities.md) | Individually evaluated fall/fight/fire/PPE/anomaly candidate packs | 06 | Research-heavy; unsupported packs remain disabled |
| [08 — Performance and scaling](plans/08-performance-scale.md) | Quality-gated economical profiles, Redis TimeSeries projection, bounded scale-out | 07 gate report, including explicit deferrals | Large; Kafka/Rust only on measured need |
| [09 — Custom models and learning](plans/09-learning.md) | Review datasets, offline retraining, versioned shadow/promotion/rollback | 08 | Large; no automatic self-training |
| [10 — Production hardening](plans/10-production.md) | Soak/recovery/privacy/security/capacity qualification and operating guide | 09 | Medium/large; depends on field evidence |

The smallest useful checkpoint is **after Plan 03**: an offline CLI with real persisted events. **After Plan 06**: a single-site live/replay application. Plans 07–10 extend it; they should not postpone the basic useful product. Plan 07 can finish with documented unsupported/blocked capabilities and no release claim, allowing the proven core to proceed to scaling.

## Technical context and complexity budget

- Python 3.11, native decode/image/inference libraries; PostgreSQL, local media, optional Redis series.
- Linux CPU-first; model/runtime versions pinned after benchmark. No cameras-per-host promise before target measurements.
- Pytest for contract/integration behavior; real disposable DB/media stack; browser verification for playback/seek/access states. Model correctness evaluated on labeled data, not mock outputs alone.
- One package/CLI, one API service, one lightweight frontend, and existing media/database services. Camera processes are workers, not microservices for every activity.
- Proposed layout, introduced only as each responsibility becomes necessary:

```text
src/avalokan/
  contracts/        # typed observations, events, plugin/config/time schemas
  media/            # source clocks, files, live sessions, evidence maps
  inference/        # artifact/preprocess/runtime adapters
  tracking/         # time-aware association
  pipeline/         # scheduler, shared dependencies, frame ownership
  activities/       # small rule/specialist plugins
  storage/          # migrations, event transactions, metrics, outbox
  api/              # authenticated control/query/review endpoints
  cli.py
web/                # Preact + native video/hls.js
benchmarks/         # maintained harness and dataset manifests, not video blobs
tests/              # contract/integration/E2E fixtures
```

Keep infrastructure choices reversible through concrete data contracts, not a universal abstraction for every possible database/runtime. Preserve notebook references. No Spec Kit constitution has been ratified; do not claim a constitution gate passed. These plans supply explicit engineering/verification gates instead.

## Requirement traceability

| Requirements | Primary plan(s) |
|---|---|
| FR-001/004 ingest and time | 01, 03, 04 |
| FR-002/003/005/006/007 shared inference, models, timing, scheduling | 01, 03, 05, 08 |
| FR-008/010/011 activity capabilities and extensibility | 02, 05, 07 |
| FR-009/012/014/015 events, durability, queries, metrics | 02, 03, 08 |
| FR-013/016 evidence and playback | 04, 06 |
| FR-017/018 API and delivery | 02, 06, 10 |
| FR-019/022 observability and scale | 01, 04, 08, 10 |
| FR-020/021 review and learning | 06, 09 |
| FR-023/024 privacy and offline use | Every stage; final qualification 10 |

Every algorithm change must say which failure mode it addresses, how much CPU/latency it costs, what quality it loses or gains, and how to revert it. If no measured improvement survives the quality gate, keep the simpler previous version.
