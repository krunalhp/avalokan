# Plan: upload-to-events vertical slice

Use Python 3.11, PyAV, OpenCV, ONNX Runtime CPU, FastAPI/Pydantic, psycopg and
PostgreSQL 15. The UI uses Vite/Preact/TypeScript with native video. Reuse the
verified YOLOX Nano artifact and one inference thread. Keep notebooks unchanged.

## Ownership

- `src/avalokan/contracts.py`: validated immutable run configuration/events.
- `src/avalokan/detector.py`: pinned model contract, preprocessing and NMS.
- `src/avalokan/activities.py`: tracking and small registry-based activity rules.
- `src/avalokan/engine.py`: PTS-driven batch analysis and measurements.
- `src/avalokan/db.py`, `migrations/`: transactions and durable job/event records.
- `src/avalokan/api.py`: upload/query/auth/media boundaries; never runs inference.
- `src/avalokan/worker.py`: bounded subprocess execution and crash recovery.
- `web/`: upload settings, progress, player, timeline and review.
- `.agents/skills/analyzing-cctv/`: agent workflow and API client.

## Sequence

1. Freeze the API contract and Spec Kit tasks; prepare locked dependencies/local DB.
2. Implement contracts, durable storage and independent UI/skill clients.
3. Implement detector, timestamp-aware baseline tracking, plugins and worker.
4. Integrate upload/progress/video/event/review endpoints.
5. Verify temporal boundaries, auth, idempotency, recovery and actual inference.
6. Run the skill and browser end to end; record evidence and update tasks/results.

The parent design's stage ordering is narrowed by the user's request for a usable
upload UI now. We do not wait for the 100-camera-hour release corpus to expose an
explicitly experimental workbench. No accuracy gate is marked passed by this.

## Constitution check

The Spec Kit constitution is still an unratified template. Use the parent spec's
bounded computation, truthful event semantics, provenance and verification gates;
do not claim constitutional ratification. No extensions/hooks are configured.
