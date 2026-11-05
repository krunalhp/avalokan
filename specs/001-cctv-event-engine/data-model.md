# Data model and API contracts

**Status:** Design contract; not a deployed schema. Plan 02 implements migrations and executable validators. All IDs below are opaque identifiers, scoped by `tenant_id` even for the initial single-tenant installation.

## D1 — Events, measurements and recordings are different data

An event is an interval or point with identity, changing state, provenance and evidence. A metric is a timestamped numeric value. A recording is immutable compressed media with a time map. Do not force all three into a Redis numeric sample or a single untyped JSON table.

**Default:** PostgreSQL for authoritative event state/history, numeric time partitions, metadata and outbox; filesystem recordings addressed by stable IDs and checksums. PostgreSQL is not a specialized time-series product, but its open-source native partitioning, transactions, JSONB and indexes suit these mixed records. This intentionally favors correct event semantics over selecting a database solely because its name contains “time series.”

**Redis TimeSeries adapter:** publish numeric projections such as occupancy, observed flow and alert counts. Do not store event text as a double, key per frame, or giant string inside series labels. Redis is a rebuildable projection, not the only copy of incident history. A future TimescaleDB backend can use Apache-licensed features; TSL-only compression/continuous aggregates require a separate license decision. See [research.md](research.md).

## D2 — Entity inventory

| Entity | Identity and essential fields | Retention/ownership |
|---|---|---|
| `site`, `camera` | tenant/site/camera ID, display timezone, secret reference, camera purpose, stream capabilities | Metadata; credentials never stored in event JSON |
| `camera_calibration` | camera + version; normalized zones/lines, masks, anchor definitions, homography/units if available, valid interval | Immutable version; camera pose changes invalidate it |
| `stream_epoch` | unique ID, camera, source URI reference, timebase numerator/denominator, first PTS, UTC anchor source and error bound | New epoch on reconnect/discontinuity; raw PTS never assumed globally unique |
| `media_asset` / `media_segment` | content/segment ID, camera/epoch, path or object key, hash, codec, dimensions, first/last PTS, byte length, optional UTC bounds | Immutable content; `available`, `pinned`, `expired`, `missing`, `corrupt` state |
| `pipeline_version` | immutable config ID/hash, plugin version, activity allowlist, parameters, timing and budget, calibration version | Changes create new row |
| `model_artifact` | SHA-256, origin/license, runtime/precision, input/preprocessing/output/class contracts, evaluation card | Never trust a mutable filename such as `latest.onnx` |
| `processing_run` | run ID, asset/live camera, config/model set, baseline/shadow/reprocess purpose, source range, parent run, status | Retry resumes the run; deliberate re-analysis creates a new run |
| `analysis_coverage` | run + epoch + source interval; observed/skipped/unavailable/degraded reason and effective cadence | Distinguishes no events from no usable analysis |
| `track_sample` | run + epoch + tracker ID + PTS; bbox/anchor/class, score, observed/predicted flag | Short-lived diagnostics, downsampled/columnar export; not a permanent person record |
| `event_identity` | tenant + globally unique event ID; immutable creation bucket; stable producer key and run/pipeline/epoch authority | Dedup and retention anchor; independent of mutable event start |
| `event_current` | tenant + event ID; current revision, activity, point/interval, state, source/UTC bounds, support, summary and typed attributes | Unpartitioned initial current-state table; normal indexes and stable foreign keys |
| `event_revision` | tenant + creation bucket + event ID + revision; append-only full snapshot, reason, author, commit time, payload hash | Partitioned by immutable event creation bucket, not corrected occurrence time |
| `event_evidence` | event + revision + media ID + PTS range, ROI, evidence kind, time-map error, expiration/pin | No signed URLs persisted |
| `event_review` | review ID, event/revision, reviewer, verdict, correction/reason, created time | Append-only; review disagreement remains visible |
| `metric_sample` | tenant + series ID + sample time + analysis run; value/unit, quality, covered duration and source revision | Time partitioned; unique series labels never include track/event IDs |
| `outbox` / `delivery` | durable message ID, event/revision or metric revision, payload, destination, attempts, lease, retry time | Written with event transaction; independent downstream delivery status |
| `worker_lease`, `checkpoint` | camera/partition + monotonically increasing fence; run + source offset + plugin/tracker state version | Fenced ownership and resumability |

## D3 — Concrete event envelope

The following is an **illustrative record, not a detection from the downloaded Noida sequence**. The source PTS uses a 1/90000 second timebase; 5,580,000 ticks represent 62 seconds.

```json
{
  "schema_version": 1,
  "tenant_id": "demo-site",
  "event_id": "evt-example-001",
  "revision": 2,
  "camera_id": "gate-01",
  "stream_epoch_id": "epoch-example-01",
  "run_id": "run-example-01",
  "pipeline_id": "gate-dwell",
  "pipeline_version": "config-example-01",
  "activity": "zone.dwell",
  "kind": "interval",
  "state": "ended",
  "closure_reason": "observed_exit",
  "source_time": {
    "start_pts": 900000,
    "end_pts": 6480000,
    "time_base_num": 1,
    "time_base_den": 90000
  },
  "start_at": "2026-10-15T06:30:10Z",
  "end_at": "2026-10-15T06:31:12Z",
  "time_quality": {"basis": "camera_ntp", "uncertainty_ms": 100},
  "last_observed_at": "2026-10-15T06:31:12Z",
  "recorded_at": "2026-10-15T06:31:12.400Z",
  "subject_refs": ["run-example-01/epoch-example-01/track-17"],
  "zone_id": "loading-zone",
  "confidence": {"score": 0.88, "meaning": "rule_support_score", "calibrated_probability": false},
  "support": {"observed_duration_ms": 62000, "unknown_duration_ms": 0, "confirmation_count": 125},
  "attributes": {"object_class": "person", "threshold_ms": 60000, "calibration_version": "calibration-1"},
  "provenance": {"model_artifact_id": "model-example-01", "tracker_version": "time-aware-1", "plugin_version": "dwell-1"},
  "evidence": [{"media_id": "recording-example-01", "start_pts": 450000, "end_pts": 6930000}],
  "summary": "Person remained in loading-zone for 62 observed seconds.",
  "summary_template_version": "zone-dwell.en.v1",
  "review_status": "unreviewed"
}
```

Validators require ordered PTS within one epoch; positive rational timebase; nonnegative durations; confidence score domain plus semantics; valid activity-specific attributes; subject references in the right run; and evidence covering the claimed source interval or an explicit gap. UTC fields may be null when unknown; timestamps may not be synthesized from processing time. Integer PTS values are transported as decimal strings if they would exceed JavaScript's safe integer range.

`start_at/end_at` are occurrence times; `recorded_at` is commit/knowledge time. They answer different queries. Confirmation can arrive long after start. An event's semantic start can be corrected without changing its partition bucket or identity.

## D4 — Identity, revisions and idempotence

1. At episode creation, allocate an event ID and stable producer key in persistent worker state/spool. The producer key covers tenant/run/pipeline/epoch/episode identity, not wall-clock retry time. Same-run checkpoint restore preserves it.
2. `event_identity` has primary key `(tenant_id, event_id)`, unique `(tenant_id, producer_key)` and unique `(tenant_id, creation_bucket, event_id)` for foreign-key routing. Creation bucket is UTC commit day at first creation, immutable even when source UTC is unknown.
3. `event_revision` has primary key `(tenant_id, creation_bucket, event_id, revision)` and foreign key to identity's corresponding composite key. Partition by `creation_bucket`; PostgreSQL requires the partition key in unique constraints. The registry prevents cross-partition aliases of the same event.
4. Within one transaction: lock/compare current revision, verify producer/fencing authority and allowlist version, append revision, update current state, append outbox and advance checkpoint. Same key + same payload hash is a no-op; same key + different content is a conflict requiring investigation.
5. An out-of-order revision is buffered/retried or rejected with expected revision; it must not overwrite newer state. Concurrent review uses optimistic version checks and independent audit records.
6. A retried delivery is deduplicated by event/revision; an intentional reprocess has a new run and separate result set. Do not promise semantic dedup across different model versions or changed tracker identities.
7. An explicit, audited run-selection record chooses the canonical result set by camera/activity/source range. Default counts exclude superseded/shadow runs. Human correlation between similar episodes is separate from transport dedup.

Initial implementation may keep revisions unpartitioned until the partition tests are in place, but must preserve immutable creation buckets and the identity constraints from day one. No `PRIMARY KEY(event_id)` on a table partitioned only by occurrence timestamp: PostgreSQL cannot enforce that globally.

## D5 — Lifecycle and gaps

`candidate → active → ended`; candidate evidence can be suppressed before any external alert. Published episodes may become `retracted` by a corrective revision. `ended` has a reason: observed exit, timeout after last confirmation, source gap, configuration change, shutdown or analysis end. UI shows interruption differently from observed exit. Point events such as confirmed crossings publish `ended` immediately with a single source timestamp, using `kind=point` rather than pretending an empty half-open interval overlaps queries.

`last_observed_*` is the last confirmed support, not the newest predicted box. Predicted coordinates can keep a visual track moving but cannot fabricate observed dwell. Short allowed occlusion has explicit bounded uncertainty; a larger gap ends the episode at last supported time and starts a linked new episode after reconfirmation. Disabled pipelines stop opening episodes while host-issued administrative closure remains permitted under the old config.

## D6 — Queries and indexes

- Point occurrence: `start_at >= from AND start_at < to`.
- Interval overlap: `start_at < to AND effective_end > from`, with `effective_end` taken from end time or last supported time for active events. Do not substitute infinity for a stale active event's observed coverage. A separate “currently active” query uses lifecycle state plus health.
- Unknown UTC: query by asset/epoch and rational source positions, not wall-clock range.
- Current event indexes: `(tenant_id, camera_id, start_at DESC, event_id)`, selective activity/time index, partial index on active events; a range/GiST index only if overlap query profiling justifies it. JSONB is for activity-specific attributes; filter-heavy fields are typed columns.
- History is retrieved by identity bucket/event/revision. Time partitions alone cannot accelerate arbitrary overlap queries for episodes that started long ago; current-state indexes are essential.
- Keyset pagination includes the full stable sort key and scope; cap date ranges and response sizes. Revision stream pagination uses durable outbox sequence, not mutable occurrence time.
- Do not add a global GIN index on every JSON object by default. Measure WAL and index write amplification.

## D7 — Numeric series and Redis projection

Series key labels: tenant, camera, pipeline/config family, metric, optional zone/class and canonical result-set version. Never one series per track ID. Units and aggregation semantics are schema fields.

- Flow counts sum unique confirmed crossing episodes. Replays and event retractions cannot increment them twice.
- Occupancy is a gauge: use time-weighted mean or maximum as appropriate, not a sum of snapshots. Persist covered/unknown duration with every bucket.
- Dwell histogram counts one completed canonical episode, not every event update.
- Store aggregate revision and contributing event/run boundary so recomputation is possible after a review or model promotion.
- Redis `TS.ADD`/`TS.MADD` receives **absolute bucket values** with an explicit timestamp, not `*` processing time or retry-sensitive `TS.INCRBY`. A single ordered writer per series (or atomic version guard) ignores stale bucket revisions before using duplicate-policy `LAST`.
- Redis compaction is a serving optimization; durable PostgreSQL rollups remain rebuildable and coverage-aware. A stale/out-of-retention update requires rebuilding the affected projection, not pretending the correction succeeded.
- Redis loss must not destroy events. Rebuild projections from canonical records; retain dedup/version state for at least the replay window. Do not assume all Valkey installations ship the RedisTimeSeries module.

## D8 — Retention without broken evidence

Retention is a policy, even when disk is abundant. Policies separately cover raw video, derived tracks, events/history, metrics, reviews and pinned evidence. Never drop a partition containing an open event or retained/legal-hold/pinned history; separate held records before expiring the rest, or defer that partition's deletion. Audit deletion jobs and enforce tenant scope.

Media expiration updates catalog state. Event metadata can remain with `evidence_expired`; a pin creates an immutable protected media asset, not just a DB flag while MediaMTX independently deletes the underlying file. Use content checksums to detect corruption. Tombstones survive the maximum replay horizon; after that reject resurrection by stale runs unless the operator creates a deliberate new run.

Backups and restores must include schema, event identities/current/history, run selection, media catalog and policy; optional Redis data is not the only backup. Real deployments decide encryption and off-host replication, tested before production claims.

## D9 — Initial API surface

| Endpoint | Contract |
|---|---|
| `POST /v1/jobs` | File/media ID + camera/config + mode; caller-supplied idempotency key; validates capability and returns job ID |
| `GET /v1/jobs/{id}` | Progress in source time, covered/skipped/gap intervals, run version and errors |
| `GET /v1/events` | Tenant-scoped filters, overlap semantics, canonical/shadow flag, stable cursor; UTC or media-relative mode |
| `GET /v1/events/{id}` | Current state, provenance, revisions and evidence availability |
| `GET /v1/events/stream` | SSE revision stream with resume cursor; polling remains fallback |
| `POST /v1/events/{id}/reviews` | Expected revision + verdict/correction/reason; no in-place deletion of model facts |
| `POST /v1/pipelines/validate` | Resolve allowlists, dependency reuse and budget before activation |
| `POST /v1/pipelines/{id}/versions` | Immutable config version; separate activate operation with authorization/audit |
| `GET /v1/capabilities` | Supported versus experimental activities, required models/calibration/cadence |
| `POST /v1/media/{id}/playback` | Authorize and return short-lived scoped playback capability plus time map; no filesystem path exposure |
| `GET /v1/metrics/series` | Numeric series with units, quality and coverage; backend-neutral |
| `POST /v1/webhooks` | Authorized destination, secret reference, activity scope and signed revision envelopes |

Reject oversized uploads, traversal, unauthorized RTSP/HTTP targets and webhook SSRF. Camera provisioning needs a controlled network allowlist; arbitrary user URLs must not reach metadata services/private networks. No unauthenticated MediaMTX admin API or direct database exposed through a portal. Initial demo credentials must be local-only or generated privately, never committed.
