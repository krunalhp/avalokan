import io
import zipfile

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from avalokan.settings import ROOT
from benchmarks.harness import (
    BenchmarkDetector,
    compute_pareto_frontier,
    ensure_model_artifact,
    ensure_noida_smoke_dataset,
    extract_verified_zip_entries,
    preprocess_yolox_416,
    quantize_yolox_int8,
    reject_html_or_oversized,
    run_synthetic_timing_check,
)
from benchmarks.ledger import (
    FrameEntry,
    ModelSpec,
    SequenceManifest,
    default_ledger,
    dhash_64,
    validate_partition_integrity,
)


def _base_eval_sequence(**overrides) -> dict:
    base = {
        "id": "seq_a",
        "dataset": "TestCCTV",
        "source_url": "https://example.com/cctv",
        "license": "CC BY 4.0",
        "attribution": "Test attribution",
        "camera_id": "cam_01",
        "scene_group": "junction_01",
        "capture_day": "2026-01-10",
        "overlap_group": "network_a",
        "timing_basis": "known_pts",
        "known_source_fps": True,
        "temporal_accuracy_valid": True,
        "counts_for_cctv_accuracy": True,
        "permitted_use": "held_out_event_evaluation",
        "split": "tune",
        "transformations": "none",
    }
    base.update(overrides)
    return base


def test_partition_validator_rejects_camera_scene_network_and_near_duplicate_leakage():
    # 1. Synthetic or unknown-FPS sequences cannot claim CCTV/temporal accuracy
    with pytest.raises(ValidationError, match="Synthetic fixtures"):
        SequenceManifest.model_validate(
            _base_eval_sequence(timing_basis="synthetic_fixture", counts_for_cctv_accuracy=True)
        )
    with pytest.raises(ValidationError, match="Unknown source FPS"):
        SequenceManifest.model_validate(
            _base_eval_sequence(known_source_fps=False, temporal_accuracy_valid=True)
        )

    # 2. Same camera across tune and test fails
    s1 = SequenceManifest.model_validate(_base_eval_sequence(id="s1", split="tune"))
    s2_same_cam = SequenceManifest.model_validate(
        _base_eval_sequence(
            id="s2",
            split="test",
            scene_group="junction_02",
            capture_day="2026-01-11",
            overlap_group="network_b",
        )
    )
    with pytest.raises(ValueError, match="Camera leakage"):
        validate_partition_integrity([s1, s2_same_cam])

    # 3. Same scene/day across train and test fails
    s2_same_scene_day = SequenceManifest.model_validate(
        _base_eval_sequence(
            id="s2",
            split="test",
            camera_id="cam_02",
            overlap_group="network_b",
        )
    )
    with pytest.raises(ValueError, match="Scene/day leakage"):
        validate_partition_integrity([s1, s2_same_scene_day])

    # 4. Overlapping dataset network (e.g. UVH-26 in tune and BMD-45 in test) fails
    s2_same_network = SequenceManifest.model_validate(
        _base_eval_sequence(
            id="s2",
            split="test",
            camera_id="cam_02",
            scene_group="junction_02",
            capture_day="2026-01-11",
        )
    )
    with pytest.raises(ValueError, match="Dataset network overlap"):
        validate_partition_integrity([s1, s2_same_network])

    # 5. Adjacent Noida frames placed in disjoint splits are caught by perceptual dhash_64
    s2_disjoint_meta = SequenceManifest.model_validate(
        _base_eval_sequence(
            id="s2",
            split="test",
            camera_id="cam_02",
            scene_group="junction_02",
            capture_day="2026-01-11",
            overlap_group="network_b",
        )
    )
    frame_paths, _ = ensure_noida_smoke_dataset()
    frame0 = cv2.imread(str(frame_paths[0]))
    frame2 = cv2.imread(str(frame_paths[1]))
    with pytest.raises(ValueError, match="Near-duplicate frame leakage"):
        validate_partition_integrity(
            [s1, s2_disjoint_meta],
            frame_hashes_by_sequence={"s1": [dhash_64(frame0)], "s2": [dhash_64(frame2)]},
        )


def test_fetch_and_runtime_guards_reject_html_traversal_agpl_and_bad_contracts(tmp_path):
    with pytest.raises(ValueError, match="HTML/login"):
        reject_html_or_oversized(
            b"<!DOCTYPE html><html>login</html>", "application/octet-stream", 1024
        )
    with pytest.raises(ValueError, match="HTML/login"):
        reject_html_or_oversized(b"binary", "text/html; charset=utf-8", 1024)
    with pytest.raises(ValueError, match="size limit"):
        reject_html_or_oversized(b"x" * 20, "application/octet-stream", 10)

    # Path traversal in ZIP is rejected before writing
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.jpg", b"payload")
    with pytest.raises(ValueError, match="Unsafe"):
        extract_verified_zip_entries(
            buf.getvalue(),
            [FrameEntry(archive_path="safe.jpg", local_path="safe.jpg", sha256="0" * 64)],
            root=tmp_path,
        )

    # AGPL models require explicit opt-in
    ledger = default_ledger()
    agpl_spec = next(m for m in ledger.models if m.id == "ultralytics_yolo11n")
    with pytest.raises(PermissionError, match="allow-agpl"):
        ensure_model_artifact(agpl_spec, allow_agpl=False)

    # Wrong channel order, input shape, or unavailable provider fail loudly
    dummy_img = np.zeros((100, 120, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="BGR"):
        preprocess_yolox_416(dummy_img, channel_order="RGB")
    with pytest.raises(ValueError, match="input shape"):
        preprocess_yolox_416(dummy_img, input_shape=(1, 3, 640, 640))

    nano_spec = next(m for m in ledger.models if m.id == "yolox_nano_fp32")
    nano_path = ROOT / ".data/models/yolox_nano.onnx"
    with pytest.raises(ValueError, match="unavailable"):
        BenchmarkDetector(nano_path, nano_spec, provider="OpenVINOExecutionProvider")


def test_int8_calibration_rejects_non_images_and_conv_qdq_preserves_scores(tmp_path):
    nano_path = ROOT / ".data/models/yolox_nano.onnx"
    with pytest.raises(ValueError, match="at least one verified"):
        quantize_yolox_int8(nano_path, [], tmp_path / "out.onnx")
    bad_file = tmp_path / "not_an_image.bin"
    bad_file.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="not a valid image"):
        quantize_yolox_int8(nano_path, [bad_file], tmp_path / "out.onnx")

    frame_paths, _ = ensure_noida_smoke_dataset()
    calib = frame_paths[:10]
    naive_path = quantize_yolox_int8(
        nano_path,
        calib,
        ROOT / ".data/models/yolox_nano_int8_naive_qdq.onnx",
        mode="int8_naive_qdq",
    )
    conv_path = quantize_yolox_int8(
        nano_path,
        calib,
        ROOT / ".data/models/yolox_nano_int8_conv_qdq.onnx",
        mode="int8_conv_qdq",
    )
    frame0 = cv2.imread(str(frame_paths[0]))
    tensor, _ = preprocess_yolox_416(frame0)
    naive_spec = ModelSpec(
        id="yolox_nano_int8_naive_qdq",
        name="Naive QDQ",
        license="Apache-2.0",
        license_class="permissive",
        precision="int8_naive_qdq",
        base_model_id="yolox_nano_fp32",
    )
    conv_spec = ModelSpec(
        id="yolox_nano_int8_conv_qdq",
        name="Conv QDQ",
        license="Apache-2.0",
        license_class="permissive",
        precision="int8_conv_qdq",
        base_model_id="yolox_nano_fp32",
    )
    naive_det = BenchmarkDetector(naive_path, naive_spec)
    conv_det = BenchmarkDetector(conv_path, conv_spec)
    naive_raw = naive_det.infer_raw(tensor)
    conv_raw = conv_det.infer_raw(tensor)
    assert float(naive_raw[:, 4].max()) < 0.3
    assert int(((naive_raw[:, 4] * naive_raw[:, 5:].max(axis=1)) >= 0.3).sum()) == 0
    assert float(conv_raw[:, 4].max()) > 0.70
    assert int(((conv_raw[:, 4] * conv_raw[:, 5:].max(axis=1)) >= 0.3).sum()) >= 15


def test_schedule_motion_gate_stationary_person_and_pareto_dominance():
    safe_mg = run_synthetic_timing_check(
        schedule_fps=2.0, motion_gate=True, keep_active_tracks_alive=True
    )
    unsafe_mg = run_synthetic_timing_check(
        schedule_fps=2.0, motion_gate=True, keep_active_tracks_alive=False
    )
    fps_1 = run_synthetic_timing_check(schedule_fps=1.0, motion_gate=False)
    assert safe_mg["positive_recall"] == 1.0 and safe_mg["hard_negative_violations"] == 0
    assert unsafe_mg["positive_recall"] < safe_mg["positive_recall"]
    assert fps_1["positive_recall"] == pytest.approx(2 / 3, rel=1e-3)
    assert safe_mg["counts_for_cctv_accuracy"] is False

    profiles = [
        {
            "profile_id": "fast_low_cpu",
            "cpu_seconds_per_video_hour_at_2fps": 90.0,
            "p95_ms": 13.0,
            "matched_box_recall_vs_fp32": 1.0,
            "reference_detector_recall": 0.55,
        },
        {
            "profile_id": "strictly_worse_threads",
            "cpu_seconds_per_video_hour_at_2fps": 210.0,
            "p95_ms": 16.0,
            "matched_box_recall_vs_fp32": 1.0,
            "reference_detector_recall": 0.55,
        },
        {
            "profile_id": "high_recall_int8",
            "cpu_seconds_per_video_hour_at_2fps": 195.0,
            "p95_ms": 28.0,
            "matched_box_recall_vs_fp32": 0.94,
            "reference_detector_recall": 0.94,
        },
        {
            "profile_id": "degraded_int8",
            "cpu_seconds_per_video_hour_at_2fps": 120.0,
            "p95_ms": 19.0,
            "matched_box_recall_vs_fp32": 0.25,
            "reference_detector_recall": 0.15,
        },
    ]
    evaluated = {
        p["profile_id"]: p for p in compute_pareto_frontier(profiles, min_self_fp32_recall=0.85)
    }
    assert evaluated["fast_low_cpu"]["pareto_optimal"] is True
    assert evaluated["high_recall_int8"]["pareto_optimal"] is True
    assert evaluated["strictly_worse_threads"]["pareto_optimal"] is False
    assert evaluated["strictly_worse_threads"]["dominated_by"] == "fast_low_cpu"
    assert evaluated["degraded_int8"]["pareto_optimal"] is False
    assert "exclusion_reason" in evaluated["degraded_int8"]
