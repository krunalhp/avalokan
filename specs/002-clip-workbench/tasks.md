# Tasks: CCTV clip workbench

Input: spec.md, plan.md, contracts/api.md; parent research and architecture.
Status: locally implemented and verified; see results.md. Not pushed or deployed.
Checkboxes mean implemented AND verified, not merely written.

## Foundation
- [X] T001 Lock runtime/test dependencies and extend `.agents/setup` plus `.amp/services.yaml`.
- [X] T002 Implement validated contracts and PostgreSQL migrations in `src/avalokan/` and `migrations/`.

## US1 — Upload and analyze
Independent test: upload real CCTV, submit job, wait, retrieve persisted facts.
- [X] T003 [US1] Implement pinned ONNX detector and PTS batch engine in `src/avalokan/detector.py` and `engine.py`.
- [X] T004 [US1] Implement durable queue, bounded worker, retry and API in `src/avalokan/worker.py` and `api.py`.
- [X] T005 [US1] Test media rejection, authentication, idempotency and restart in `tests/`.

## US4 — Extend activities
Independent test: deterministic observations exercise plugins without media or DB.
- [X] T006 [US4] Implement shared tracking and registry rules in `src/avalokan/activities.py`.
- [X] T007 [US4] Verify gap, dwell boundary, crossing jitter and allowlists in `tests/test_activities.py`.

## US2 — Video review
Independent test: browser upload, progress, playback, seek, filter and review.
- [X] T008 [P] [US2] Build Preact workbench in `web/` against the frozen API contract.
- [X] T009 [US2] Verify real desktop/narrow and empty/error/result states; record evidence in `results.md`.

## US3 — Agent access
Independent test: skill client uploads/analyzes/queries through the real HTTP API.
- [X] T010 [P] [US3] Add `.agents/skills/analyzing-cctv/` with API client and safety/reporting instructions.
- [X] T011 [US3] Verify pagination and the skill workflow against the running service.

## Integration
- [X] T012 Update `README.md`, `quickstart.md`, extension guide and `results.md`; rerun setup twice, tests and build.

Dependencies: T001/T002 precede backend integration. T008 and T010 can run in
parallel against contracts/api.md, with disjoint files. T003/T006 precede T004;
T005/T007/T009/T011 precede final T012. No task marks a parent production gate
complete; live streams and specialist accuracy remain in the original roadmap.
