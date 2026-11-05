# Plan 02 — Make event identity, time and persistence correct

**Status:** Not started. **Depends on:** Plan 01. **Delivers:** typed schemas, a disposable PostgreSQL environment, migrations and durable event transactions.

## Work units

1. Create the minimal installable `avalokan` package and separate serving/benchmark/training dependency groups. Add typed source-time, observation, event, model-manifest, configuration and capability contracts from [data-model.md](../data-model.md).
2. Create tenant/site/camera/config/model/run tables and event identity/current/revision/evidence tables. Include immutable identity buckets, payload hash, sequence checks, foreign keys and scoped uniqueness. Implement interval and point query semantics, including relative-only video.
3. Implement the event/revision/current/outbox/checkpoint transaction with optimistic revision checks and replay dedup. Add producer authority hooks; multi-node lease issuance itself waits until Plan 08.
4. Add time-partitioned numeric observations and versioned coverage-aware aggregate semantics. Keep PostgreSQL as the authoritative store; no Redis dependency yet.
5. Add schema-validated instance/pipeline allowlists, typed activity payloads and deny-all defaults. Reject unknown activities, model metadata mismatches, missing calibration and accidental wildcard enablement.
6. Provide disposable local database setup and supervised service declarations, without production writes. Keep secrets out of tracked files; lifecycle setup is repeatable and not a migration command for a shared DB.

## Acceptance and evidence

- Tests run against actual PostgreSQL, not an in-memory substitute for PostgreSQL constraints.
- Replay same event/revision/payload → exactly one stored revision and outbox item; changed payload at same identity → conflict. Concurrent updates cannot regress state.
- Correct a start time across midnight while preserving identity; create/update an event spanning partitions; demonstrate no invalid global-unique assumption.
- Query an interval starting before the requested range and a point exactly at each boundary. Unknown UTC is queryable only by source coordinates unless explicitly anchored.
- Force rollback after each transaction step: no partial event/outbox/checkpoint state survives. Current state matches folded revision history.
- Wrong-tenant and disallowed-activity writes fail. Test unknown config keys and misspelled activities, not only valid inputs.

## Stop and handoff

Document the migration/rebuild commands, event JSON Schema and database invariants in `results/02.md`. Run setup twice and show service readiness. No detector implementation, external database mutation, or media/UI service yet. Rollback means discard the disposable DB or use a tested local migration; never delete user footage.
