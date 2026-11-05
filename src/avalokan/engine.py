import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import UUID, uuid5

import av
from psycopg.types.json import Jsonb

from .activities import TRACKER_VERSION, Activities, Tracker
from .contracts import AnalysisConfig
from .db import connect
from .detector import Detector
from .media import prepare_playback
from .settings import MODEL_SHA256, Settings


def analyze(path, format, config, detector, progress=lambda _: None, max_duration=600):
    started, cpu_started = time.perf_counter(), time.process_time()
    tracker = Tracker(max_gap=1.5 / config.sample_fps)
    plugins = Activities(config)
    events, metrics = [], []
    decoded = analyzed = 0
    first = previous = None
    next_sample = 0.0
    last_progress = -1.0
    with av.open(
        str(path), format=format, options={"protocol_whitelist": "file,pipe"}
    ) as container:
        stream = container.streams.video[0]
        stream.thread_count = 1
        for frame in container.decode(stream):
            decoded += 1
            if decoded > 90000 or frame.width > 3840 or frame.height > 2160:
                raise ValueError("Decoded video exceeds resource limits")
            if frame.pts is None or frame.time_base is None:
                raise ValueError("Video has no trustworthy presentation timestamps")
            absolute = float(frame.pts * frame.time_base)
            if first is None:
                first = absolute
            timestamp = absolute - first
            if previous is not None and timestamp <= previous:
                raise ValueError("Video has duplicate or backward presentation timestamps")
            if timestamp > max_duration:
                raise ValueError("Decoded video exceeds duration limit")
            previous = timestamp
            if timestamp + 1e-7 < next_sample:
                continue
            next_sample = timestamp + 1 / config.sample_fps
            if config.allowed_activities:
                detections = detector.detect(
                    frame.to_ndarray(format="bgr24"), config.classes, config.confidence
                )
                tracks = tracker.update(timestamp, detections)
                events.extend(plugins.observe(timestamp, tracks))
                metrics.append(
                    {"time_s": timestamp, "counts": dict(Counter(t.object_class for t in tracks))}
                )
                analyzed += 1
                if len(events) > 50000:
                    raise ValueError("Event limit exceeded; split the clip or narrow activities")
            if timestamp - last_progress >= 1:
                progress(timestamp)
                last_progress = timestamp
    if decoded == 0:
        raise ValueError("Video contains no decodable frames")
    events.extend(plugins.close())
    events.sort(key=lambda e: (e.start_s, e.end_s, e.track_id, e.activity))
    elapsed = time.perf_counter() - started
    return (
        events,
        metrics,
        {
            "decoded_frames": decoded,
            "analyzed_frames": analyzed,
            "elapsed_s": elapsed,
            "cpu_s": time.process_time() - cpu_started,
            "duration_s": previous,
            "analysis_fps": analyzed / elapsed,
            "model_sha256": MODEL_SHA256 if config.allowed_activities else None,
            "tracker_version": TRACKER_VERSION,
            "sample_fps": config.sample_fps,
            "time_basis": "presentation_time_relative_to_first_frame",
            "source_start_s": first,
            "coverage": "sampled; not continuous; missing detections break track continuity",
        },
    )


def run_job(settings, job_id, expected_attempt=None):
    job_started = time.perf_counter()
    with connect(settings) as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
        media = conn.execute("SELECT * FROM media WHERE id=%s", (job["media_id"],)).fetchone()
    expected_attempt = job["attempts"] if expected_attempt is None else expected_attempt
    if job["status"] != "running" or job["attempts"] != expected_attempt:
        raise ValueError("Job no longer owns publication")
    config = AnalysisConfig.model_validate(job["config"])
    if set(config.allowed_activities) - settings.allowed:
        raise ValueError("Job activities are no longer permitted by this instance")
    with Path(media["path"]).open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != media["sha256"]:
            raise ValueError("Uploaded media checksum changed")
    start = time.perf_counter()
    playback = prepare_playback(media)
    preparation = time.perf_counter() - start
    with connect(settings) as conn:
        conn.execute("UPDATE media SET playback_path=%s WHERE id=%s", (str(playback), media["id"]))
    detector = Detector(settings.model) if config.allowed_activities else None

    def progress(timestamp):
        with connect(settings) as conn:
            conn.execute(
                "UPDATE jobs SET progress=%s WHERE id=%s AND status='running' AND attempts=%s",
                (min(0.99, timestamp / media["duration_s"]), job_id, expected_attempt),
            )

    events, metrics, stats = analyze(media["path"], media["format"], config, detector, progress)
    # Check playable video start against source mapping. FFmpeg normally makes
    # H.264 MP4 start at zero; reject a shifted proxy rather than silently mis-seek.
    with av.open(str(playback)) as clip:
        frame = next(clip.decode(video=0))
        if abs(float(frame.pts * frame.time_base)) > 0.1:
            raise ValueError(
                "Playback start cannot be aligned; export the clip with a zero start time"
            )
    stats["playback_preparation_s"] = preparation
    provenance = {
        "model_sha256": stats["model_sha256"],
        "tracker_version": TRACKER_VERSION,
        "plugin_version": "1",
        "config": config.model_dump(),
        "media_sha256": media["sha256"],
        "time_basis": stats["time_basis"],
        "source_start_s": stats["source_start_s"],
        "confidence_meaning": "detector support (minimum for intervals), not calibrated probability",
    }
    with connect(settings) as conn:
        state = conn.execute(
            "SELECT status,attempts FROM jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if state["status"] != "running" or state["attempts"] != expected_attempt:
            raise ValueError("Job no longer owns publication")
        for index, event in enumerate(events):
            if event.activity not in config.allowed_activities:
                raise ValueError("Event outside job allowlist")
            conn.execute(
                """INSERT INTO events(id,job_id,activity,object_class,track_id,start_s,end_s,
                         summary,confidence,attributes,provenance) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    uuid5(UUID(str(job_id)), str(index)),
                    job_id,
                    event.activity,
                    event.object_class,
                    event.track_id,
                    event.start_s,
                    event.end_s,
                    event.summary,
                    event.confidence,
                    Jsonb(event.attributes),
                    Jsonb(provenance),
                ),
            )
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO metric_samples(job_id,time_s,counts) VALUES(%s,%s,%s)",
                [(job_id, m["time_s"], Jsonb(m["counts"])) for m in metrics],
            )
        stats["total_processing_s"] = time.perf_counter() - job_started
        conn.execute(
            "UPDATE jobs SET status='completed',progress=1,stats=%s,finished_at=now(),error=NULL WHERE id=%s",
            (Jsonb(stats), job_id),
        )
    return stats


if __name__ == "__main__":
    print(json.dumps(run_job(Settings(), UUID(sys.argv[1]), int(sys.argv[2]))))
