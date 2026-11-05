# Plan 08 — Optimize measured cost and scale only the bottleneck

**Status:** Not started. **Depends on:** Plan 07's gate report, including explicit deferrals. **Delivers:** quality-qualified resource profiles, numeric TimeSeries adapter and recoverable multi-camera operation.

## Work units

1. Profile decode/resize/copies/inference/NMS/tracking/rules/store at 1/4/16 camera test points, stopping at saturation. Record hardware, actual input rates, thread pools, memory, CPU-seconds/video-hour, effective coverage, total latency and quality. No nested thread oversubscription.
2. Add adaptive motion/ROI sampling, periodic refresh and per-plugin rate admission. Test against full-rate selected-detector baseline; tune only on the calibration/tuning splits. Restore full observations when active hazards or uncertainty require them.
3. Compare one-thread economical vs multi-thread latency profiles, FP32/INT8/OpenVINO and optionally GPU/TensorRT. Batch across compatible inputs with bounded delay; compare GPU duty-cycle and cost only on available representative hardware.
4. Add memory pools/shared-memory frame handles only when copies are material. A Rust/PyO3 boundary is conditional on >20% measured Python-only CPU after simpler fixes; require equivalent event output and a net end-to-end benefit.
5. Implement camera/run ownership leases, monotonic fencing and resource admission across worker processes/hosts. Fault one worker, recover its checkpoint, and avoid double ownership. Keep video local/relay by media protocol; only compact observations/events cross coordination links.
6. Implement the optional **Redis 8 TimeSeries numeric projection** from the outbox: absolute time-bucket values, revision guards, bounded labels, retention and replay/rebuild. Pin a reviewed license/version. PostgreSQL remains event truth; Redis availability cannot gate inference or delete history.
7. Measure Postgres queue/rollup bottlenecks. Kafka is a decision gate: add only if sustained outbox lag/IO saturation or independent distributed replay/fan-out warrants it. If not, deliver the documented rejection rather than a broker. If yes, use camera/run partitioning, schema versions and consumer dedup; never frame payloads.
8. Add capacity cards and a 24-hour bounded-resource soak with database/network faults and mixed fast/slow plugins. Distinguish incomplete live coverage from complete but slow batch processing.

## Acceptance and evidence

- Meet the spec's absolute quality gates before claiming ≥3× efficiency improvement or economical-mode savings. Publish failed/non-dominating configurations too.
- Stationary dwell and fast crossing tests catch aggressive gating mistakes. More disabled activities must reduce unreachable model work, not merely suppress emitted labels.
- Redis duplicate/reordered updates and event retractions yield correct absolute aggregates; delete the disposable Redis instance and rebuild the same series from Postgres. Unknown periods remain unknown, not zeros.
- Kill an owner after lease expiry: its writes are fenced even if it resumes. Crash/replay does not double count crossings or numeric buckets.
- For any Kafka branch, test replay, broker unavailability, consumer duplication and event-schema upgrades; report operational cost against the no-broker baseline.

## Stop and handoff

`results/08.md` includes the Pareto chart, workload/capacity cards, supported profiles, Redis rebuild proof and Kafka/Rust decisions. Do not infer fleet capacity from the small single-scene probe. No production rollout yet.
