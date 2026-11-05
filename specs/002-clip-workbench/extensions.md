# Add or change an activity

Activity rules consume shared timestamped tracks; they do not decode videos,
create model sessions, call the API or write to the database. This keeps the
cost of several rules close to the cost of one inference pass per sampled frame.

## Ownership

- `contracts.py`: validated run settings and event candidates.
- `detector.py`: pinned model, preprocessing and class-aware suppression.
- `activities.py`: track association, rule state and `REGISTRY`.
- `engine.py`: original presentation timestamps, sampling, metrics, provenance,
  deterministic run-scoped IDs and atomic publication.
- `api.py`/`worker.py`: transport, authorization, queue admission and execution.
- `web/`: UI; no inference or rule decisions.

## Plugin contract

Add a trusted Python class in `activities.py` (or a focused module when it grows):

```python
class MyActivity:
    id = "my.activity"
    name = "My activity"
    description = "Describe only the evidence the rule establishes."

    def __init__(self, config):
        self.config = config

    def observe(self, time, tracks):
        # time: clip-relative PTS seconds; tracks: current sampled observations.
        # Return list[EventCandidate]. Keep per-track state only when needed.
        return []

    def close(self):
        # Flush supported intervals at end-of-file; never invent future time.
        return []
```

Register it with `REGISTRY[MyActivity.id] = MyActivity`. The API capabilities and
UI activity picker discover registered, instance-allowed IDs automatically.
The host constructs only the requested activities and rejects candidates with
an ID different from the plugin's. No API route, worker, or SQL migration is
needed for a rule using current settings/observations. Plugins are trusted
repository code, not uploaded scripts or a security sandbox.

For a new setting, add a constrained field to `AnalysisConfig` and a UI control
if humans need to edit it; update the TypeScript config and API contract. Do not
accept an unvalidated options bag. For model-specific observations, extend the
shared observation contract deliberately rather than opening another inference
session inside every rule. This initial slice has one detector family, not a
general inference DAG.

## Temporal semantics to preserve

- A track contains a run-local integer ID, class, uncalibrated support score,
  normalized bounding box and source time. Bottom-center is the geometric anchor.
- The baseline matches consecutive detections by IoU. Missing observations or
  a gap longer than 1.5 sampling periods reset continuity; no identity is promised
  through occlusion. A rule must not accumulate dwell across unknown spans.
- Presence/dwell need at least two supported observations. Interval bounds are
  observed endpoints, not extrapolated entry/exit times. Crossings are point
  events with boundary uncertainty in attributes.
- `summary` is deterministic text from typed facts, not a model-generated story.
  Never infer intent, identity, crime or demographic attributes.
- Use `EventCandidate`, retain `activity`, `object_class`, `track_id`, source
  bounds and score. Put rule-specific evidence in `attributes`. On semantic
  changes, bump the engine's plugin version (currently one shared version) and
  tracker version when relevant; old jobs must remain interpretable.

## Verification and qualification

Extend `tests/test_activities.py` using asymmetric observations that distinguish
the intended behavior from likely mistakes: both directions across a line,
inside/outside a zone, just below/at the duration threshold, jitter and missing
observations. Test returned events, not private state or call order. Validate
allowlist enforcement and an empty allowlist. Run the complete suite.

Then compare on scene-separated labeled footage: precision/recall by activity,
false positives/hour, boundary error, CPU seconds/video hour, wall time and peak
memory. Record sampling/model/config versions and decode/proxy costs separately.
Do not promote a plugin from experimental based on synthetic observations or a
short demo. Start with the parent roadmap's benchmark/data stage; only replace
the tracker, add gating, Rust, Redis or Kafka when measurements justify them.
