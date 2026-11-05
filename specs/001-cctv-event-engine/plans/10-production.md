# Plan 10 — Qualify operation, privacy and recovery before deployment

**Status:** Not started. **Depends on:** Plan 09. **Delivers:** a tested release candidate and operator runbook. Deployment remains a separate authorized action.

## Work units

1. Audit authentication, site/tenant isolation, media capabilities, role permissions, webhook/upload/RTSP SSRF controls, secret redaction, dependency/model licenses and offline behavior.
2. Implement/configure recording/event/track/metric retention, evidence pins, user export/deletion and audit workflows. Review lawful purpose and applicable India privacy obligations with the deployment owner; do not infer legal compliance from technical controls alone.
3. Test backup/restore of PostgreSQL plus media/catalog consistency, optional off-host recording/spool replication and clock synchronization. Set measured RPO/RTO and documented limits per deployment profile.
4. Run multi-camera soaks under worker crash, DB/broker/network outage, time drift, disk pressure, codec change, slow viewers and hostile oversized input. Test long-open events and retention partitions with protected evidence.
5. Produce release capability cards by activity/camera condition, unsupported cases, hardware/camera capacity, expected lag and coverage. Include deployment-specific false-alert exposure and human escalation workflow.
6. Package a minimal CPU single-node deployment and optional measured accelerated/distributed profiles. Update orb setup/resume/service files and verify fresh/warm startup; no mandatory Kafka/Redis if unused.
7. Document upgrades, schema compatibility, rollback, adding a camera/plugin/model, diagnosing lost coverage, rebuilding numeric projections and safely rotating credentials. Keep training infrastructure separate.

## Acceptance and evidence

- Restore from backup onto disposable infrastructure and open the correct event evidence; a database-only restore that points to missing recordings is not a pass.
- Unauthorized users cannot reach cross-site records or replay video, including through raw media paths and stale signed capabilities.
- Retention never silently destroys pinned material; missing/corrupt assets are surfaced. Replays outside the dedup retention horizon are rejected or explicitly reprocessed.
- A 24-hour representative soak meets admitted-camera latency and bounded-resource gates; failures reduce the advertised capacity rather than hiding errors.
- Operator runbook includes hardware/software hashes, all executed checks and remaining gaps. Safety candidates retain their non-certified/human-review warnings.

## Stop and release boundary

Write `results/10.md` with pass/fail matrix and the exact proposed rollout/rollback. Ask for authorization before deploying, changing real cameras, enabling external alert destinations or applying shared database migrations. “Release candidate verified” is not “deployed.”
