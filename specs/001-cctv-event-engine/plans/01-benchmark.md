# Plan 01 — Establish the India CCTV benchmark before choosing the fastest model

**Status:** Harness, dataset/license ledger, INT8 comparison, and Pareto profile completed locally in [results/01.md](../results/01.md); production activity accuracy gates remain blocked pending authorized long-PTS India field recordings. **Depends on:** existing orb setup. **Delivers:** a repeatable benchmark and dataset/license ledger, not a production model claim.

## Scope and decisions

Start with the verified TrafficCAM Noida sample and YOLOX Nano/Tiny ONNX artifacts in [research.md](../research.md). Build the maintained harness instead of expanding a disposable probe into the runtime. Include CPU one/two/four-thread comparisons; separate low latency from total CPU work. Keep Ultralytics comparisons behind an explicit licensing choice.

## Work units

1. Add `benchmarks/` CLI/config and manifest schema. Track URLs, license, attribution, checksums, source camera/scene, timing provenance, transformations, permitted use and split. Cache models/data outside Git; no automatic multi-GB download on orb startup.
2. Implement a bounded, explicit sample fetch command. Verify size/hash/ZIP paths and reject HTML/login responses. Keep the existing Noida clip smoke-only; its synthesized playback FPS is not original timing.
3. Collect authorized long clips with known PTS: stationary/dense traffic, stationary people, empty scenes, night/IR, glare, rain and occlusion. If unavailable, publish the missing-data matrix. Use TrafficCAM/UVH/BMD only for their labeled capabilities; record unresolved camera overlap.
4. Define detection class mapping including unsupported rickshaw/tractor subclasses. Label a small event subset independently: crossings, entrances, dwell intervals and hard negatives. Freeze matching tolerances and scene/day-separated train/calibration/tune/test manifests before tuning.
5. Benchmark decoder-only, resize/preprocess, inference-only, postprocess and simple tracking separately, plus the combined path. Full source-FPS detection is the reference schedule. Compare 0.5/1/2/5 fps, forced refresh, ROI crop and motion gate only where event labels support the comparison.
6. Compare ONNX FP32 with calibrated INT8; native OpenVINO only on supported hardware. No quantization score claim from random tensors. Fix thread pools, run repeated interleaved trials, separate cold/warm startup, and record hardware/cgroup limits, RSS, p50/p95, CPU-seconds/video-hour, covered video time and detector call count.
7. Produce a Pareto table: a configuration wins only if no other configuration is both cheaper and at least as accurate/timely. Freeze a provisional model/preprocessing/time-aware tracking profile for Plan 03. Record licenses and exact artifact hashes.

## Acceptance and evidence

- A fresh checkout reproduces the bounded smoke probe with one documented command after setup; no hidden local paths or credentials.
- Output JSON distinguishes model-only from end-to-end timing and unknown source FPS from real duration. Incorrect shape, preprocessing/channel order and missing execution-provider support fail loudly.
- Dataset partition/near-duplicate tests catch adjacent-scene leakage. Synthetic fixtures check timing/math only; no synthetic accuracy result presented as CCTV accuracy.
- Save raw results and a short benchmark report with every exclusion. The current probe's ~12 ms Nano call is a comparison point, not a pass threshold.
- If no profile satisfies core quality, record why and choose the next model/scene-data experiment. Do not compensate by suppressing difficult frames from evaluation.

## Stop and handoff

Write `results/01.md` with reproducible commands, chosen provisional artifacts, class support and missing labels. If long-event data is unavailable, subsequent infrastructure work may proceed as experimental; production activity gates remain blocked. Do not start a UI, Kafka cluster, training run or production service in this stage.
