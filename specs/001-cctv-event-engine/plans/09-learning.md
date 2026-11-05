# Plan 09 — Improve models through reviewed data and controlled promotion

**Status:** Not started. **Depends on:** Plan 08. **Delivers:** a narrow, auditable custom-model workflow rather than an autonomous training platform.

## Work units

1. Export authorized event clips and hard-negative/missed-event examples with source rights, purpose, retention, reviewer labels, label version and camera/scene/day split. Support an external open-source labeling tool through standard formats; do not build one from scratch.
2. Add automatic candidate mining for uncertainty, disagreements, drift and false alarms. This proposes work for reviewers; it cannot convert model predictions into truth or upload footage to an external provider by default.
3. Create an offline training/fine-tuning command with pinned data/model/code/config hashes, reproducible split, resource limits and metrics. Separate training dependencies/processes from live serving. Begin with a concrete failing class/domain found in earlier results.
4. Export signed/hashed supported model artifacts with complete input/output/preprocessing/class schemas; verify inference parity against the training model. Restrict unsafe deserialization and model URLs.
5. Run shadow inference on a bounded subset using existing frames where compatible; compare per-condition quality and CPU overhead without mixing shadow events into counts/alerts.
6. Require explicit promotion after quality/performance/license gates. Canary by camera subset, atomically switch config/model version, preserve old runs and allow rollback. Historical reprocessing produces a new result set with deliberate canonical selection.

## Acceptance and evidence

- Trace a reviewed false alert through a dataset revision, fine-tuned artifact, shadow comparison and a reversible promotion on disposable test data.
- Scene/test leakage checks fail on overlapping frames/camera sequences. Export lineage respects expired footage and revoked dataset permissions.
- A model with better average AP but worse rare-activity recall or night false alerts cannot pass the deployment-specific gate.
- Rollback restores the old processing version without deleting new history; aggregates do not double count both result sets.
- Drift alarms do not trigger automatic retraining or production model replacement. External labeling/training services require separate authorization.

## Stop and handoff

`results/09.md` includes one demonstrated improvement or an honest non-improvement, exact lineage, deployment limits and rollback proof. No automatic learning loop may become a silent production behavior.
