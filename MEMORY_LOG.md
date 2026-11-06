# Avalokan Change Memory Log

Append-only log of debugging sessions and changes to the workbench. Newest last.
Maintained by agents running the `debugging-footage-runs` skill; one entry per
diagnosed issue or shipped change.

---

## 2026-11-06 — Orb setup for fresh sandboxes

- **Change:** Added `.agents/setup` and `.agents/resume` (commit `41d2272`) so fresh
  orbs start with the toolchain ready. Later rewritten upstream in `3371587` to use
  `uv sync --locked`, Postgres 15, model install, and web build; that version is
  authoritative (cold ~30 s, warm ~8 s, idempotent, verified twice).
- **Verified:** Setup run twice; clean login shell sees the full environment.

## 2026-11-06 — URL ingest (YouTube and other sites) for the workbench

- **Symptom:** The app only accepted local file uploads; the user's footage is on
  YouTube (e.g. `https://www.youtube.com/watch?v=HqcSyLIxEPc`).
- **Change:** New `POST /v1/media/url` + `GET /v1/media-ingests/{id}` endpoints
  (contract updated in `specs/002-clip-workbench/contracts/api.md`), backed by a new
  `media_ingests` table (`migrations/002_url_ingest.sql`, `db.migrate` now applies
  all `migrations/*.sql` in order). Downloads run via `yt-dlp` in a bounded
  background thread of the API process; the downloaded clip passes through the same
  ffprobe validation as uploads. Web form gained a "From URL" source
  (`web/src/components/UploadForm.tsx`, `web/src/api.ts`); dependency `yt-dlp` added
  to `pyproject.toml`/`uv.lock`.
- **Verified:** `pytest tests/ -q`: all 14 workbench/activity tests pass. E2E: a
  direct video URL ingested → analyzed → 5 events emitted; UI "From URL" flow
  screenshot-checked.

## 2026-11-06 — Structured trace monitoring

- **Symptom:** Worker only printed `Analyzing job …/Completed job …`; failures were
  opaque and ingests unlogged; nothing correlated API requests with jobs.
- **Change:** New `src/avalokan/tracing.py` — one JSON line per event with
  `trace_id` (`req_*` per HTTP request, `ing_*` per URL ingest, job UUID during
  analysis). API middleware logs every request with status + duration and returns
  `X-Trace-Id`; worker logs `job.start` / `job.completed` (with frame stats) /
  `job.failed` / `job.engine_failed` (child stderr tail); upload/submit/ingest emit
  lifecycle events.
- **Verified:** Trace lines observed in `amp orb service logs avalokan` across a
  full URL→job→events run.

## 2026-11-06 — Desktop sign-in flow for YouTube cookies

- **Symptom:** User reported "not accepting url" for YouTube footage. Diagnosis via
  the portal UI: the form accepts and submits the URL correctly; the ingest fails
  because YouTube blocks anonymous downloads from the orb's datacenter IP on every
  player client.
- **Change:** Cookie sourcing now supports two modes: a Netscape cookies file
  (`.data/secrets/youtube-cookies.txt` or `AVALOKAN_YTDLP_COOKIES`) or the signed-in
  Desktop Chrome profile (`AVALOKAN_YTDLP_COOKIES_FROM_BROWSER=chrome` in
  `.amp/services.yaml`, read via `yt-dlp --cookies-from-browser`). New
  `.amp/open-youtube-signin.sh` launches Desktop Chrome with its profile at
  `~/.config/google-chrome` so the user can sign into YouTube once and the ingest
  worker reuses those cookies.
- **Verified:** Workbench tests pass; service restarted with the env flag.

## 2026-11-06 — Known open issues (not yet fixed)

- **YouTube blocks datacenter downloads:** all player clients return "Sign in to
  confirm you're not a bot" from this orb's IP. Cookie support is wired (file or
  Desktop Chrome profile); awaiting the user's one-time YouTube sign-in, then URL
  ingest of YouTube links will work.
- **Two pre-existing benchmark test failures** (`tests/test_benchmark.py::
  test_partition_validator_rejects_camera_scene_network_and_near_duplicate_leakage`,
  `test_int8_calibration_rejects_non_images_and_conv_qdq_preserves_scores`): the
  TrafficCAM fixture fetches bytes 0–35,550,774 of the 2 GB figshare file
  `45011947`, and that slice now starts with `__MACOSX` resource-fork entries using
  ZIP data descriptors, which `extract_verified_zip_entries` rejects by design.
  Present before any of today's changes; fixing it means re-deriving a valid byte
  range (or central-directory parsing) for the Noida frames.
