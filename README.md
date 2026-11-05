# Avalokan

An experimental, CPU-first CCTV clip workbench: **upload → analyze → timestamped
events → review/query**. The original notebooks remain available for research.

## What works now

- Upload MP4/MOV/MKV clips up to 250 MiB, ten minutes and 3840×2160.
- Enable an explicit activity allowlist per run: object presence, vertical-line
  crossing and rectangular-zone dwell. An instance can further restrict it.
- Shared YOLOX Nano inference at 1/2/5 sampled fps, conservative source-time IoU
  tracking, and small Python activity plugins. No LLM or per-frame captioning.
- PostgreSQL stores durable jobs, immutable event facts, provenance, timestamped
  occupancy samples and append-only human reviews. Original media stays on disk.
- Preact UI with native browser video, event seeking/filtering and human reviews.
  H.264 is remuxed; other accepted codecs get a one-thread H.264 playback proxy.
- Versioned API with OpenAPI and a repository [agent skill](.agents/skills/analyzing-cctv/SKILL.md).

**All activities are experimental.** Scores are uncalibrated model support, not
probabilities. Tracks are not identities. Sampling can miss short events;
occlusion and missed detections break continuity. Empty results mean “not
observed,” not “did not happen.” Times are clip-relative, not capture UTC.

Fighting, falling, fire, theft, PPE, anomalies, live RTSP, distributed workers,
Redis projections and automated training are **not implemented**. They remain in
the [ten-stage roadmap](specs/001-cctv-event-engine/plan.md); do not use this
workbench for safety decisions or infer criminal intent from its output.

## Run in an Amp orb

```bash
.agents/setup
amp orb services ensure
```

Open the workbench portal printed by the second command. The checked-in service
configuration explicitly enables **demo mode without application authentication**.
All viewers of that portal share clips and results. Use only non-sensitive test
footage. This is not a production deployment.

Setup installs Python 3.11.14, locked Python dependencies, Specify CLI 1.2.0,
FFmpeg and PostgreSQL 15; initializes a private local database; downloads a
checksum-pinned YOLOX Nano ONNX artifact; and builds the locked UI with the orb's
Node/npm. It does not download datasets, train, authenticate or start servers.
Supervised services start separately. `.agents/resume` only checks the Python
environment; snapshots reuse dependencies instead of reinstalling them on resume.
Changes must reach the project's default branch to prepare future orbs.

See [quickstart and configuration](specs/002-clip-workbench/quickstart.md) for
token mode, API commands, storage, limits and verification. See the
[extension guide](specs/002-clip-workbench/extensions.md) to add an activity
without rewriting transport or storage.

## Development and Spec Kit

The active milestone is [002 — Clip workbench](specs/002-clip-workbench/spec.md),
with a [plan](specs/002-clip-workbench/plan.md),
[task tracker](specs/002-clip-workbench/tasks.md),
[API contract](specs/002-clip-workbench/contracts/api.md), and
[verification results](specs/002-clip-workbench/results.md).
The parent [design and research](specs/001-cctv-event-engine/spec.md) cover the
larger product. Spec Kit commands are in `.agents/commands/`; the constitution
is still an unratified template.

```bash
specify check
SPECIFY_FEATURE=002-clip-workbench .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
uv run --locked pytest -q
uv run --locked python -m unittest discover -s .agents/skills/analyzing-cctv/scripts
uv run --locked ruff check src tests
npm --prefix web run build
```

Tests require the local PostgreSQL service and use disposable schemas. Runtime
code imports from `src` (`PYTHONPATH=src` outside pytest). The workbench does not
import PyTorch; CPU-only PyTorch, Ultralytics, JupyterLab, TensorBoard, Comet and
ONNX export tools are retained for the notebooks. Skip notebook `%pip install`
cells to preserve the lockfile. `VideoAnalysis.ipynb` uses Colab paths such as
`/content/sample_data/cctv.mp4`; adjust them before local execution. Comet requires
separate authentication; use TensorBoard for local logging.
