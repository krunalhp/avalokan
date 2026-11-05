# Plan 05 — Make activities pluggable and share expensive observations

**Status:** Not started. **Depends on:** Plan 04. **Delivers:** capability registry, configuration admission and practical retail/traffic rule packs.

## Work units

1. Stabilize the small plugin contract with versioned inputs, activity declarations, cadence/window requirements, budgets, snapshot/reset and gap callbacks. Keep a trusted explicit registry; no arbitrary uploaded executable code.
2. Resolve compatible dependencies and reference counts: two rules using the same stream/model/preprocessing/tracker share them. Different spatial/cadence requirements are combined honestly or admitted as a separate measured graph.
3. Implement instance/pipeline allowlist enforcement at startup, host emission and persistence. Empty = none, unknown = error, no wildcard. Ensure a disabled specialist cannot load its model or collect hidden crops.
4. Add zone enter/exit/intrusion, stopped vehicle, wrong-way candidate, occupancy threshold and queue-length rules one at a time. Each has calibrated geometry, hysteresis, timing and uncertainty semantics. Queue region occupancy is not automatically proof of queue membership.
5. Add hot config activation at source-time boundaries, administrative closure of removed activities and immutable version history. New rules reuse live dependencies when compatible without restarting the camera.
6. Isolate slow/failed plugins with bounded frame leases, cancellation and resource budgets. Build a second independently installed example rule to validate that extending the engine does not require changing its core.

## Acceptance and evidence

- Two identical observation subscribers show one detector call per chosen observation, not two. Removing one leaves the other alive; removing the last unloads the expensive dependency.
- A 10 fps subscriber cannot silently run at the 1 fps subscriber's cadence. Resource admission either meets the union or returns an explicit rejection.
- Disallowed activity injection fails even if a plugin returns it. Operational health remains visible without permitting semantic bypass.
- Negative rule tests include stationary pedestrians, parked vehicles, queue dispersal, shadow motion, boundary jitter, direction ambiguity and invalid calibration.
- Change an allowlist while dwell is active: one administrative close under the old config, no new disallowed event, other rules uninterrupted.
- Demonstrate a new rule plugin using documented contracts alone; reject incompatible schema versions and release all retained frame buffers on fault.

## Stop and handoff

Write `results/05.md` with capability matrix, per-rule quality/CPU results, dependency reuse evidence and extension guide. Learned fall/fight/fire models and generic anomaly inference remain out of this stage.
