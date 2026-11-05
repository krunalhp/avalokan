# Plan 07 — Add specialist activities only when evidence supports them

**Status:** Not started. **Depends on:** Plan 06. **Delivers:** independently gated candidate-detection packs, not one universal activity model.

Each subsection is a separate local checkpoint. A failed/data-blocked subsection stays experimental and disabled; continue to the next and report the unsupported capability. The core engine remains usable without any of these models.

## 07A — Falling and fighting

1. Define labeled temporal windows, minimum person pixel size, camera angle, occlusion and response-time requirements. Use authorized/non-graphic footage and staged controls; verify dataset/model permissions before downloading.
2. Fall baseline: lightweight licensed pose estimation on tracked crops plus a temporal classifier/state machine. Compare against sitting, bending, lying normally, camera tilt and temporary occlusion. A bounding-box aspect-ratio flip alone is insufficient.
3. Fight baseline: pair/group interaction crops with a compact temporal model or temporal-shift network. Skeleton-only and RGB methods are competing baselines; judge the total crop/pose/model cost. Do not assume a “fast motion” threshold distinguishes fighting from play.
4. Trigger candidates cheaply while retaining enough pre-roll samples for the temporal window. Account for the window's actual sampling requirement; a sparse object tracker cannot reconstruct missing motion after a trigger.

## 07B — Fire, smoke, PPE and unattended objects

1. Fire/smoke use a dedicated evaluated detector/classifier with temporal confirmation and idle-scene checks independent of person triggers. Include fog, dust, sunlight, headlights, screens and steam as hard negatives.
2. PPE/proximity use domain-specific class models and calibrated zones. Distinguish not visible from missing. Object/pixel distance is not physical distance without calibration.
3. Unattended-object candidates require persistent-object observations plus explicitly uncertain interaction history. Do not assert owner identity or abandonment merely from a bag class.

## 07C — Anomaly and traffic extensions

1. Per-camera scene-change/anomaly score is opt-in triage with a baseline/version and visible explanation. Camera drift/weather should generate health/baseline issues, not crime alerts.
2. Signal-violation candidates require synchronized authoritative signal input, stop-line calibration and uncertainty bounds. If unavailable, keep the capability unsupported; wrong-way/stopped events remain usable.

## Shared acceptance and evidence

- Each pack has an artifact/license/data card, timing contract, bounded crop queue, per-camera enablement, event schema and independent CPU budget.
- Compare against labeled positives **and** long negative exposure, report event-level precision/recall, false episodes/camera-hour, latency, unknown coverage and confidence intervals per condition.
- Reject/mark experimental any condition without enough examples. COCO object AP is not a fall/fight/fire score. A research-only dataset is not commercial training authorization.
- A pack fault or deadline miss does not starve core rules. Disabled packs consume no model inference. Every emitted event is a reviewed candidate, not an emergency action.

## Stop and handoff

`results/07.md` is a per-pack pass/experimental/blocked ledger with exact reasons, artifact versions and residual risks. Training a useful model may require more data than this stage currently has; do not fabricate working support. Plan 08 may proceed with the proven subset and explicit deferrals.
