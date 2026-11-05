# Research and measured evidence

**Investigated:** 2026-10-15. Primary sources below were read directly or inspected through a repository research agent. Architectural choices are recommendations; cited benchmark results do not establish Avalokan performance.

## F1 — Fewer model calls matter more than a new language

Most fixed-camera frames repeat background and often repeat object state. The useful chain is decode → object/pose observations → trajectories → temporal rules/classifiers → structured episodes → template text. Camera-specific filters and shared intermediate observations can eliminate work. Busy scenes, brief events and stationary hazards limit those savings.

- [NoScope paper](https://arxiv.org/html/1703.02529v3): cascaded difference detectors and specialized classifiers accelerated narrow video queries against a reference neural model. Its presence-window metric, old detector baseline and camera-specific optimization do **not** prove equivalent event recall or general activity understanding here.
- [Reducto paper](https://web.cs.ucla.edu/~harryxu/papers/li-sigcomm20.pdf): content-dependent frame filtering with feedback on query accuracy. The lesson is adaptive calibration and measured error, not copying a fixed motion threshold or importing its reported speedups.
- [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html): static calibration is normally appropriate for CNNs; INT8 performance depends on operator/backend/CPU support, and accuracy can regress. Quantize against representative CCTV and compare event quality, not just model file size.

**Decision:** profile the full pipeline, reduce redundant inference, share results, and implement application semantics in Python around native kernels. GPU batching can be more economical at high camera density, despite higher device power; benchmark watts/video-hour when energy measurement is available.

## F2 — A real Noida CCTV sequence was downloaded and inspected

Source: [TrafficCAM figshare record](https://doi.org/10.6084/m9.figshare.25399681), dataset described by its publisher as stationary-camera street sequences from eight Indian cities; [paper](https://arxiv.org/abs/2211.09620). The figshare API reports **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**. Credit: Zhongying Deng, Yanqi Cheng, Lihao Liu, Shujun Wang, Rihuan Ke, Carola-Bibiane Schönlieb and Angelica I Aviles-Rivero. The preview is a derived visualization with changed playback timing, not an original continuous recording.

Downloaded archive entries: `Fully_annotate/Noida_1650519000.2172463/frame0.jpg` through `frame58.jpg`, even indices, 30 frames at 1920×1080. Source archive: [Fully_annotate.zip](https://ndownloader.figshare.com/files/45011947), size 2,020,305,572 bytes, publisher MD5 `07d5819efeb150d6095e85bb37dcfb4a`.

Used HTTP byte-range reads instead of fetching the entire archive. The containing range was 35,550,775 bytes; each extracted frame's ZIP CRC was verified and SHA-256 recorded. Frames are local under ignored `datasets/trafficcam-smoke/`. The user-review manifest is `.amp/in/artifacts/trafficcam-noida-manifest.json`; the preview is `.amp/in/artifacts/trafficcam-noida-preview.mp4`.

Visual inspection found an elevated fixed CCTV scene with cars, motorcycles, auto/cycle-rickshaws, pedestrians and a tractor/trailer. Visible challenges: very small distant objects, overlap, heterogeneous vehicles, hard shadows and pedestrians near lane edges. Nothing graphic was observed.

**Timing limit:** source FPS/timebase is not authoritatively established. The 3-second preview was synthesized at 10 fps in numeric frame order. Its timestamps cannot validate dwell, speed, event onset or original decoder throughput. The camera overlay contains a date/time but is not treated as a trustworthy UTC anchor. This is a smoke-test sequence, not an accuracy dataset or representative night/monsoon evaluation.

## F3 — Initial CPU inference probe: more threads can waste computation

Measured in this shared orb: four visible vCPUs, Intel Xeon @ 2.60 GHz, Python 3.11.14, ONNX Runtime 1.31.0, CPUExecutionProvider. Official YOLOX ONNX release artifacts, batch 1, 416×416 BGR float32 top-left letterbox with padding 114, no normalization. Input frames are the 30 Noida frames above. Warmup: 10 calls per configuration; measurement: three passes (90 calls). Inter-op threads 1, intra-op threads as shown, sequential executor, idle spinning disabled, OpenCV threads 1.

| Model | Inference threads | Median wall ms | p95 wall ms | Mean process CPU ms/call |
|---|---:|---:|---:|---:|
| YOLOX Nano | 1 | 11.92 | 15.41 | 12.54 |
| YOLOX Nano | 2 | 10.74 | 12.79 | 16.78 |
| YOLOX Nano | 4 | 11.07 | 12.04 | 24.41 |
| YOLOX Tiny | 1 | 43.29 | 48.89 | 44.42 |
| YOLOX Tiny | 2 | 27.70 | 32.69 | 51.76 |
| YOLOX Tiny | 4 | 21.05 | 25.08 | 61.65 |

Output arrays were checked for expected `(1, 3549, 85)` shape and finite values. They were **not** scored against annotations. CPU time includes small output-validation overhead; wall time measures `session.run`. Decoder, NMS, tracker, rules, DB, networking, cold startup and preprocessing are excluded from these inference values. Inputs are reused in memory; no energy/GPU/INT8 measurement was made. Sequential configuration order and shared-host contention limit statistical generalization.

On this probe, Nano with one thread used about half the CPU time of four threads with only a small wall-latency difference. Tiny gained lower latency from four threads but used more total CPU. This directly supports separate low-compute and low-latency profiles. It does **not** establish which model has acceptable Indian CCTV accuracy, how many cameras a host supports, or that Nano is globally fastest.

Raw measurements/method metadata: `.amp/in/artifacts/cctv-inference-probe.json`. Artifact hashes:

- [YOLOX Nano ONNX](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx): `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`.
- [YOLOX Tiny ONNX](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx): `427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7`.

Plan 01 replaces this scratch probe with a maintained end-to-end benchmark harness. No “3× faster” claim has passed yet.

## F4 — Model and tracker choice must include licensing and time semantics

[YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) is Apache-2.0. Its official Nano/Tiny table reports 0.91M/5.06M parameters and COCO AP 25.8/32.8 at 416×416. These are general benchmark figures, not our CCTV results. Its [ONNX example](https://github.com/Megvii-BaseDetection/YOLOX/tree/main/demo/ONNXRuntime) permits lightweight runtime inference without shipping the training framework. Export flags such as dynamic batch do not imply dynamic image dimensions; pin exact input/output contracts.

[ByteTrack](https://github.com/FoundationVision/ByteTrack) is MIT. Its [Kalman implementation](https://github.com/FoundationVision/ByteTrack/blob/main/yolox/tracker/kalman_filter.py) uses `dt = 1`; its [tracker](https://github.com/FoundationVision/ByteTrack/blob/main/yolox/tracker/byte_tracker.py) increments frame IDs per update. The `frame_rate` constructor argument rescales the lost-track buffer, not the motion time step. Changing detector rate without changing these semantics can cause ID switches and incorrect dwell durations.

[Ultralytics' licensing page](https://www.ultralytics.com/license) describes its code/models as AGPL or enterprise-licensed. Do not assume exporting a YOLO11 model to ONNX removes those obligations. Existing tutorial installation is not production license approval. Check artifact and training-data terms separately even when source code is Apache/MIT. This is an engineering dependency review, not legal advice.

Proposed candidate order: YOLOX Nano/Tiny FP32 → quality-constrained runtime/INT8 comparison → a larger permissible detector or scene-specific fine-tuning if needed. Keep YOLO11n as an explicitly licensed comparison candidate, not a hidden runtime dependency. Do not select a model based on GFLOPs or a vendor GPU latency table alone.

## F5 — India data supports some tasks, not all requested activities

| Source | Verified relevance/access | Restriction or blind spot |
|---|---|---|
| [TrafficCAM](https://doi.org/10.6084/m9.figshare.25399681) | CC BY 4.0, public figshare; actual Noida sample downloaded; vehicle/pedestrian masks | Short frame sequences; original timing needs verification; inspect each scene and group camera-related clips |
| [UVH-26](https://huggingface.co/datasets/iisc-aim/UVH-26), [paper](https://arxiv.org/abs/2511.02563) | IISc/Bengaluru Traffic Police fixed-camera vehicle frames; ungated CC BY 4.0 card; Indian vehicle classes | Daytime February data; no event duration/person labels; public metadata lacks reliable camera IDs for scene-disjoint claims |
| [BMD-45](https://huggingface.co/datasets/iisc-aim/BMD-45) | Larger Bengaluru CCTV vehicle-frame dataset; research agent verified public CC BY 4.0 card | Same source network/time period as UVH-26; possible overlap; not independent held-out proof after UVH tuning |
| [IITB-Corridor](https://rodrigues-royston.github.io/Multi-timescale_Trajectory_Prediction/) | Fixed IIT Bombay corridor, staged activities including loitering/running/fighting/unattended object; frame-level labels | Research-only terms, one scene, staged anomalies; do not redistribute or assume commercial training permission |
| [Bengaluru Mobility Challenge](https://ieee-dataport.org/competitions/bengaluru-mobility-challenge-2024) | Long traffic videos potentially useful for trajectories/counting | Approved-participant access; not treated as an already available dataset |

No verified open corpus here establishes India night/IR/monsoon fall/fight/fire/queue false-alarm rates. Obtain authorized, non-graphic scene footage before release claims. Do not use dashcam IDD/road-driving video as if it were fixed CCTV. Do not download graphic news crime/accident compilations as a convenient benchmark.

Split by actual camera/scene/day, not randomly adjacent frames. Where camera IDs are hidden, use conservative visual scene clustering and near-duplicate exclusion, explicitly report unresolved leakage and restrict conclusions. Keep training/calibration/tuning/test distinct; do not call BMD-45 independent simply because it has a different dataset name from UVH-26.

## F6 — PostgreSQL fits event history; Redis fits numeric projections

- [PostgreSQL partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): unique/primary constraints must include partition keys. A naive time-partitioned `UNIQUE(event_id)` design is invalid. Mutable event start time must not be the only identity/partition anchor.
- [PostgreSQL license](https://www.postgresql.org/about/licence/): permissive open-source license. Start with native features and routine partition jobs; add pg_partman when justified by maintenance needs.
- [Redis TimeSeries](https://redis.io/docs/latest/develop/data-types/timeseries/): timestamped real-valued samples, labels and aggregation; not arbitrary event-document storage. Retention is relative to the latest series timestamp, not necessarily a wall-clock deletion timer for an idle camera.
- [Redis license](https://github.com/redis/redis/blob/unstable/LICENSE.txt): Redis 8 has RSALv2/SSPLv1/AGPLv3 choices; use/review the AGPL option for an open-source deployment. Do not describe all modern Redis as BSD.
- [TimescaleDB license](https://github.com/timescale/timescaledb/blob/main/LICENSE), [feature editions](https://docs.tigerdata.com/about/latest/timescaledb-editions/): Apache-licensed core versus TSL components; continuous aggregates, columnstore and policy automation are not all in the Apache edition. TSL is source-available, not OSI open source.
- [ClickHouse ReplacingMergeTree](https://clickhouse.com/docs/engines/table-engines/mergetree-family/replacingmergetree): replacement happens during merges, not immediate relational uniqueness. Good derived analytics candidate; less simple as mutable event-authority storage.

**Decision:** PostgreSQL authoritative store plus a Redis TimeSeries adapter for scalar dashboard series when requested/needed. Avoid two authoritative databases and cross-store transactions. Storage choice is revisited using event insert, correction, overlap-query and retention workloads, not generic ingestion benchmarks.

## F7 — Kafka and playback solve different problems from model inference

[Kafka producer configuration](https://kafka.apache.org/43/configuration/producer-configs) and [broker configuration](https://kafka.apache.org/43/configuration/broker-configs) define bounded request/batch sizes and producer/consumer semantics. A raw 1080p RGB frame is much larger than the roughly 1 MiB default request/batch limits. Increasing limits does not eliminate frame-copy, network and retention costs. Kafka is useful for distributed event fan-out/replay, not a faster object detector or a replacement for RTSP/media storage.

[MediaMTX playback](https://mediamtx.org/docs/features/playback) exposes recorded time ranges and MP4/fMP4 retrieval; [browser integration](https://mediamtx.org/docs/read/web-browsers) supports HLS and WebRTC; [WebRTC codec constraints](https://mediamtx.org/docs/features/webrtc-specific-features) include browser-dependent H.265 and H.264 B-frame restrictions. [MediaMTX](https://github.com/bluenviron/mediamtx) is MIT; [hls.js](https://github.com/video-dev/hls.js) is Apache-2.0. Both are reused infrastructure, not reasons to build a large application framework.

**Decision:** original compressed recording, native video/hls.js and independent media serving. Prefer camera codec configuration over continuous transcoding. A stream/container being supported by MediaMTX is not proof every target browser can decode its codec. Validate Chrome/Firefox/Safari support on actual target devices; headless Chromium alone cannot certify Safari or hardware decoding.

## What has not been established

No production hardware capacity, accuracy, INT8 benefit, end-to-end speedup, GPU-vs-CPU economics, long-period false-alarm rate, or safety reliability has been measured. The current orb experiment is only an inference/resource tradeoff probe on one short daylight scene. These unknowns are explicit gates in Plans 01, 07 and 08 rather than assumptions hidden in the implementation.
