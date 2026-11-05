"""Dataset, model, class-mapping, and split-integrity ledger for Plan 01."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from avalokan.contracts import CLASSES
from avalokan.settings import MODEL_SHA256, MODEL_URL, ROOT

TINY_SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"
TINY_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
)
EVALUATION_SPLITS = {"train", "calibration", "tune", "test"}


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    name: str
    url: str | None = None
    sha256: str | None = None
    max_bytes: int = Field(default=30 * 1024 * 1024, gt=0)
    license: str
    license_class: Literal["permissive", "copyleft_agpl"]
    requires_explicit_license_opt_in: bool = False
    input_name: str = "images"
    input_shape: tuple[int, int, int, int] = (1, 3, 416, 416)
    output_shape: tuple[int, int, int] = (1, 3549, 85)
    channel_order: Literal["BGR"] = "BGR"
    pad_value: int = 114
    precision: Literal["fp32", "int8_conv_qdq", "int8_naive_qdq"] = "fp32"
    base_model_id: str | None = None

    @model_validator(mode="after")
    def check_contract(self):
        if self.license_class == "copyleft_agpl" and not self.requires_explicit_license_opt_in:
            raise ValueError("AGPL models must require explicit license opt-in")
        if self.precision == "fp32" and (not self.url or not self.sha256):
            if not self.requires_explicit_license_opt_in:
                raise ValueError("FP32 runtime models require pinned URL and SHA-256")
        if self.precision != "fp32" and not self.base_model_id:
            raise ValueError("Quantized variants must reference base_model_id")
        return self


class FrameEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_path: str
    local_path: str
    sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def safe_paths(self):
        for path in (self.archive_path, self.local_path):
            if path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"Unsafe path in manifest: {path}")
        return self


class SequenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    dataset: str
    source_url: str
    download_url: str | None = None
    license: str
    attribution: str
    camera_id: str
    scene_group: str
    capture_day: str
    overlap_group: str
    timing_basis: Literal[
        "known_pts", "synthesized_frame_order", "frame_only_no_pts", "synthetic_fixture"
    ]
    known_source_fps: bool
    temporal_accuracy_valid: bool
    counts_for_cctv_accuracy: bool
    permitted_use: Literal[
        "smoke_and_calibration_only",
        "vehicle_detection_only",
        "staged_research_only",
        "restricted_competition_only",
        "synthetic_timing_math_only",
        "held_out_event_evaluation",
    ]
    split: Literal[
        "smoke",
        "calibration",
        "train",
        "tune",
        "test",
        "unassigned_overlap",
        "restricted_unavailable",
    ]
    transformations: str
    byte_range: tuple[int, int] | None = None
    archive_md5: str | None = None
    files: list[FrameEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timing_and_accuracy_claims(self):
        if self.timing_basis == "synthetic_fixture" and self.counts_for_cctv_accuracy:
            raise ValueError("Synthetic fixtures cannot count toward CCTV accuracy")
        if not self.known_source_fps and self.temporal_accuracy_valid:
            raise ValueError("Unknown source FPS cannot validate temporal accuracy")
        if self.split in {"tune", "test"} and not self.counts_for_cctv_accuracy:
            raise ValueError(f"Split {self.split} requires counts_for_cctv_accuracy=True")
        return self


class MissingDataEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stratum: str
    required_conditions: str
    status: Literal["missing_long_pts", "smoke_frames_only", "restricted_access"]
    blocked_activities: list[str]
    notes: str


class ClassMappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_name: str
    coco_index: int | None = None
    status: Literal["supported_coco80", "unsupported_by_coco80_head"]
    notes: str


class MatchingTolerances(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    spatial_iou_threshold: float = Field(default=0.5, ge=0.1, le=0.95)
    crossing_time_tolerance_s: float = Field(default=0.6, ge=0.05, le=5.0)
    dwell_onset_tolerance_s: float = Field(default=1.0, ge=0.1, le=10.0)
    dwell_duration_relative_tolerance: float = Field(default=0.25, ge=0.05, le=1.0)


class ReferenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    activity: str
    object_class: str
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    direction: str | None = None
    kind: Literal["positive", "hard_negative"] = "positive"
    notes: str = ""


class BenchmarkLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: int = 1
    models: list[ModelSpec]
    sequences: list[SequenceManifest]
    missing_data_matrix: list[MissingDataEntry]
    class_mapping: list[ClassMappingEntry]
    matching_tolerances: MatchingTolerances
    synthetic_timing_reference_events: list[ReferenceEvent]


def dhash_64(image: np.ndarray) -> int:
    """Compute a 64-bit horizontal gradient hash for near-duplicate frame detection."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = 0
    for bit in diff.flatten():
        bits = (bits << 1) | int(bool(bit))
    return bits


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def validate_partition_integrity(
    sequences: list[SequenceManifest],
    frame_hashes_by_sequence: dict[str, list[int]] | None = None,
    max_near_duplicate_hamming: int = 10,
) -> dict:
    """Enforce camera/scene/day/network separation and near-duplicate rejection across splits."""
    eval_sequences = [s for s in sequences if s.split in EVALUATION_SPLITS]
    seen_cameras: dict[str, str] = {}
    seen_scene_days: dict[tuple[str, str], str] = {}
    seen_overlap_groups: dict[str, str] = {}

    for seq in eval_sequences:
        if seq.camera_id in seen_cameras and seen_cameras[seq.camera_id] != seq.split:
            raise ValueError(
                f"Camera leakage across splits: {seq.camera_id} in "
                f"{seen_cameras[seq.camera_id]} and {seq.split}"
            )
        seen_cameras[seq.camera_id] = seq.split

        scene_day = (seq.scene_group, seq.capture_day)
        if scene_day in seen_scene_days and seen_scene_days[scene_day] != seq.split:
            raise ValueError(
                f"Scene/day leakage across splits: {scene_day} in "
                f"{seen_scene_days[scene_day]} and {seq.split}"
            )
        seen_scene_days[scene_day] = seq.split

        if (
            seq.overlap_group in seen_overlap_groups
            and seen_overlap_groups[seq.overlap_group] != seq.split
        ):
            raise ValueError(
                f"Dataset network overlap across splits: {seq.overlap_group} in "
                f"{seen_overlap_groups[seq.overlap_group]} and {seq.split}"
            )
        seen_overlap_groups[seq.overlap_group] = seq.split

    near_duplicate_checks = 0
    if frame_hashes_by_sequence:
        split_by_seq = {s.id: s.split for s in eval_sequences}
        seq_ids = [s.id for s in eval_sequences if s.id in frame_hashes_by_sequence]
        for i, seq_a in enumerate(seq_ids):
            for seq_b in seq_ids[i + 1 :]:
                if split_by_seq[seq_a] == split_by_seq[seq_b]:
                    continue
                for h_a in frame_hashes_by_sequence[seq_a]:
                    for h_b in frame_hashes_by_sequence[seq_b]:
                        near_duplicate_checks += 1
                        dist = hamming_distance(h_a, h_b)
                        if dist <= max_near_duplicate_hamming:
                            raise ValueError(
                                f"Near-duplicate frame leakage between {seq_a} "
                                f"({split_by_seq[seq_a]}) and {seq_b} ({split_by_seq[seq_b]}): "
                                f"dhash Hamming distance {dist} <= {max_near_duplicate_hamming}"
                            )

    return {
        "valid": True,
        "evaluated_sequences": len(eval_sequences),
        "near_duplicate_pairs_checked": near_duplicate_checks,
    }


def _load_noida_frame_entries() -> list[FrameEntry]:
    manifest_path = ROOT / ".amp/in/artifacts/trafficcam-noida-manifest.json"
    if manifest_path.is_file():
        raw = json.loads(manifest_path.read_text())
        return [FrameEntry.model_validate(item) for item in raw["files"]]
    # Fallback pinned hashes for the 30 TrafficCAM Noida frames (even indices 0..58)
    return _DEFAULT_NOIDA_FRAMES


_DEFAULT_NOIDA_FRAMES = [
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame0.jpg",
        local_path="datasets/trafficcam-smoke/frame0.jpg",
        sha256="8bfd9015cdca0f1a49ed2ebb68b5fdb31a8d25f797462f3756cfc0765f313acf",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame2.jpg",
        local_path="datasets/trafficcam-smoke/frame2.jpg",
        sha256="323aa9d0f80e684473ca945d8b2cacffc54033116a0e34626103bc868d0f8766",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame4.jpg",
        local_path="datasets/trafficcam-smoke/frame4.jpg",
        sha256="e7bc4149e20b0d05d6a1708236a823557931e299a0960511446caa30cb010c8a",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame6.jpg",
        local_path="datasets/trafficcam-smoke/frame6.jpg",
        sha256="ae2aed437c0bf7bf47f671298c6c6744659e89d99aba944b4a348f4c4b9d743a",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame8.jpg",
        local_path="datasets/trafficcam-smoke/frame8.jpg",
        sha256="97151ccaebae637b16199682ce918724c8cfe98fc5c43ea60c3b1cea4e64a5c1",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame10.jpg",
        local_path="datasets/trafficcam-smoke/frame10.jpg",
        sha256="e833cbd6cb628ffcb374e5cee10a4782a35d8b729eb3f882375ae0f35fec8421",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame12.jpg",
        local_path="datasets/trafficcam-smoke/frame12.jpg",
        sha256="f19b251b86a207a34996d7e4a28699aa2a09453bce9a872aa58c18c4643ec2ef",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame14.jpg",
        local_path="datasets/trafficcam-smoke/frame14.jpg",
        sha256="21f0eac3c93683b2e4ce6beb6ee595bfdeee14c5c9ef664fb2cd71e07eb59ffc",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame16.jpg",
        local_path="datasets/trafficcam-smoke/frame16.jpg",
        sha256="66b82f096ab8d454116225192aa89bd32e954d51e06641d08455e6d0278a670a",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame18.jpg",
        local_path="datasets/trafficcam-smoke/frame18.jpg",
        sha256="e77fc43218214a6211de945b248625aca46f6d85d17c810fcc10b4cc40fe056c",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame20.jpg",
        local_path="datasets/trafficcam-smoke/frame20.jpg",
        sha256="1030702901f8fc1f90a0bc85077d208b7b2c59d40ce53cfd0176e131038bf071",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame22.jpg",
        local_path="datasets/trafficcam-smoke/frame22.jpg",
        sha256="e8a572391405d5ce3fba719fc818364bcd4a3f6ac64c6f4fe3de1e71fb0595c4",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame24.jpg",
        local_path="datasets/trafficcam-smoke/frame24.jpg",
        sha256="28f6f0e80ff0f0eec4fa731c68572292304d97f05762530ad485784b23f107dc",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame26.jpg",
        local_path="datasets/trafficcam-smoke/frame26.jpg",
        sha256="80dac5bbe26597b50558f59145cf664475b076338af04d18d8d72f373300f93c",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame28.jpg",
        local_path="datasets/trafficcam-smoke/frame28.jpg",
        sha256="776519d9e568bbc5d48530cdb14b07c0a35165c0af62d598c513f057035f641e",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame30.jpg",
        local_path="datasets/trafficcam-smoke/frame30.jpg",
        sha256="28da369475524f271db103ec5d2ef9106012fd06c8e4f338e32fae4f7ebda617",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame32.jpg",
        local_path="datasets/trafficcam-smoke/frame32.jpg",
        sha256="27fedb26f9a218bbe8f445107aa8940f9a70d58e66c28122e4da9e2fc6e913d6",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame34.jpg",
        local_path="datasets/trafficcam-smoke/frame34.jpg",
        sha256="171160f1e7046775cbcf18fa1e94b8d04a4cc270bc276e1c01b92e261529f410",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame36.jpg",
        local_path="datasets/trafficcam-smoke/frame36.jpg",
        sha256="3d2054cbdc8408cfedd83ca877872a7ef4bcf886d24655bd35f85f7484173571",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame38.jpg",
        local_path="datasets/trafficcam-smoke/frame38.jpg",
        sha256="1c1498d3beafde6456e9957001e813ac6de8cb028182880c9bd86b4cf0ebd4a2",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame40.jpg",
        local_path="datasets/trafficcam-smoke/frame40.jpg",
        sha256="73be0ad19f8de0bc1ba9596e2cc6c3bdd7e09daea6ddff24d58958b06e9156e3",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame42.jpg",
        local_path="datasets/trafficcam-smoke/frame42.jpg",
        sha256="7261a4fcf41a30d623ed647147fbd1b53d825d2d45a900ca4a923dbc79beebf8",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame44.jpg",
        local_path="datasets/trafficcam-smoke/frame44.jpg",
        sha256="2904fa51515e97a703bcea167b9f5b066ff3bba4a8567878b95436cad6b07c11",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame46.jpg",
        local_path="datasets/trafficcam-smoke/frame46.jpg",
        sha256="eee186296b9da8cf516d39a09c112be14cc5c106b9174dcb2f72288fc480f07d",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame48.jpg",
        local_path="datasets/trafficcam-smoke/frame48.jpg",
        sha256="df28e9473a6af0ce0ccce01f892ed354d72fa735a6c2d99d9817b37b53cd2296",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame50.jpg",
        local_path="datasets/trafficcam-smoke/frame50.jpg",
        sha256="8173b43303181550a035ee1309f2249369a2c64f7153146753eeb1eefa0fa2cc",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame52.jpg",
        local_path="datasets/trafficcam-smoke/frame52.jpg",
        sha256="570c9e70e733d922dd4a9e2e07431b611fed76c1e3b38fe098ce1ae6f10160dd",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame54.jpg",
        local_path="datasets/trafficcam-smoke/frame54.jpg",
        sha256="77373c1d87041debe33aed1139dc1aabf901f709b6f9d89ec70fed58db6c38f3",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame56.jpg",
        local_path="datasets/trafficcam-smoke/frame56.jpg",
        sha256="b82a039e7f75dda4ac91035d0e43fd605640275d722576d2f39ee141ca2df3ca",
    ),
    FrameEntry(
        archive_path="Fully_annotate/Noida_1650519000.2172463/frame58.jpg",
        local_path="datasets/trafficcam-smoke/frame58.jpg",
        sha256="14524a2900bae3fb1ec2214fe4f3b887382c148af433f7a2950666e2ca20de0e",
    ),
]


def default_ledger() -> BenchmarkLedger:
    return BenchmarkLedger(
        models=[
            ModelSpec(
                id="yolox_nano_fp32",
                name="YOLOX Nano ONNX FP32",
                url=MODEL_URL,
                sha256=MODEL_SHA256,
                license="Apache-2.0",
                license_class="permissive",
                precision="fp32",
            ),
            ModelSpec(
                id="yolox_tiny_fp32",
                name="YOLOX Tiny ONNX FP32",
                url=TINY_URL,
                sha256=TINY_SHA256,
                license="Apache-2.0",
                license_class="permissive",
                precision="fp32",
            ),
            ModelSpec(
                id="yolox_nano_int8_conv_qdq",
                name="YOLOX Nano ONNX INT8 (Opset-13 Conv-only per-channel QDQ)",
                license="Apache-2.0",
                license_class="permissive",
                precision="int8_conv_qdq",
                base_model_id="yolox_nano_fp32",
            ),
            ModelSpec(
                id="yolox_tiny_int8_conv_qdq",
                name="YOLOX Tiny ONNX INT8 (Opset-13 Conv-only per-channel QDQ)",
                license="Apache-2.0",
                license_class="permissive",
                precision="int8_conv_qdq",
                base_model_id="yolox_tiny_fp32",
            ),
            ModelSpec(
                id="ultralytics_yolo11n",
                name="Ultralytics YOLO11n (excluded unless AGPL/enterprise opted in)",
                license="AGPL-3.0-or-Enterprise",
                license_class="copyleft_agpl",
                requires_explicit_license_opt_in=True,
                precision="fp32",
            ),
        ],
        sequences=[
            SequenceManifest(
                id="trafficcam_noida_smoke",
                dataset="TrafficCAM",
                source_url="https://doi.org/10.6084/m9.figshare.25399681",
                download_url="https://ndownloader.figshare.com/files/45011947",
                license="CC BY 4.0",
                attribution=(
                    "Zhongying Deng, Yanqi Cheng, Lihao Liu, Shujun Wang, Rihuan Ke, "
                    "Carola-Bibiane Schönlieb and Angelica I Aviles-Rivero"
                ),
                camera_id="noida_1650519000",
                scene_group="noida_arterial_day",
                capture_day="2022-04-21",
                overlap_group="trafficcam_noida_1650519000",
                timing_basis="synthesized_frame_order",
                known_source_fps=False,
                temporal_accuracy_valid=False,
                counts_for_cctv_accuracy=False,
                permitted_use="smoke_and_calibration_only",
                split="calibration",
                transformations="30 even-indexed 1920x1080 JPEG frames muxed at synthetic 10 fps",
                byte_range=(0, 35550774),
                archive_md5="07d5819efeb150d6095e85bb37dcfb4a",
                files=_load_noida_frame_entries(),
            ),
            SequenceManifest(
                id="uvh26_bengaluru_frames",
                dataset="UVH-26",
                source_url="https://huggingface.co/datasets/iisc-aim/UVH-26",
                license="CC BY 4.0",
                attribution="IISc AIM & Bengaluru Traffic Police",
                camera_id="btp_unresolved_camera_pool",
                scene_group="bengaluru_traffic_day",
                capture_day="2025-02-unspecified",
                overlap_group="iisc_bengaluru_traffic_police",
                timing_basis="frame_only_no_pts",
                known_source_fps=False,
                temporal_accuracy_valid=False,
                counts_for_cctv_accuracy=False,
                permitted_use="vehicle_detection_only",
                split="unassigned_overlap",
                transformations="Disjoint frame samples without continuous PTS or camera IDs",
            ),
            SequenceManifest(
                id="bmd45_bengaluru_frames",
                dataset="BMD-45",
                source_url="https://huggingface.co/datasets/iisc-aim/BMD-45",
                license="CC BY 4.0",
                attribution="IISc AIM & Bengaluru Traffic Police",
                camera_id="btp_unresolved_camera_pool",
                scene_group="bengaluru_traffic_day",
                capture_day="2025-02-unspecified",
                overlap_group="iisc_bengaluru_traffic_police",
                timing_basis="frame_only_no_pts",
                known_source_fps=False,
                temporal_accuracy_valid=False,
                counts_for_cctv_accuracy=False,
                permitted_use="vehicle_detection_only",
                split="unassigned_overlap",
                transformations="Shares source camera network with UVH-26; cannot serve as held-out test after UVH tuning",
            ),
            SequenceManifest(
                id="iitb_corridor_staged",
                dataset="IITB-Corridor",
                source_url="https://rodrigues-royston.github.io/Multi-timescale_Trajectory_Prediction/",
                license="Academic research-only (non-commercial)",
                attribution="IIT Bombay Multi-timescale Trajectory Prediction authors",
                camera_id="iitb_corridor_cam1",
                scene_group="iitb_campus_corridor",
                capture_day="unspecified",
                overlap_group="iitb_corridor",
                timing_basis="synthesized_frame_order",
                known_source_fps=False,
                temporal_accuracy_valid=False,
                counts_for_cctv_accuracy=False,
                permitted_use="staged_research_only",
                split="restricted_unavailable",
                transformations="Single-scene staged anomalies; not redistributable or commercial",
            ),
            SequenceManifest(
                id="bengaluru_mobility_challenge_2024",
                dataset="Bengaluru Mobility Challenge 2024",
                source_url="https://ieee-dataport.org/competitions/bengaluru-mobility-challenge-2024",
                license="Restricted competition terms",
                attribution="IEEE DataPort / Bengaluru Mobility Challenge organizers",
                camera_id="bmc_restricted",
                scene_group="bengaluru_traffic_long",
                capture_day="unspecified",
                overlap_group="iisc_bengaluru_traffic_police",
                timing_basis="known_pts",
                known_source_fps=True,
                temporal_accuracy_valid=True,
                counts_for_cctv_accuracy=False,
                permitted_use="restricted_competition_only",
                split="restricted_unavailable",
                transformations="Requires approved competition participant credentials; not auto-downloadable",
            ),
            SequenceManifest(
                id="synthetic_pts_schedule_fixture",
                dataset="Avalokan Synthetic Timing Fixture",
                source_url="local://benchmarks/synthetic_pts_schedule_fixture",
                license="MIT",
                attribution="Avalokan repository fixture",
                camera_id="synthetic_cam_01",
                scene_group="synthetic_math_check",
                capture_day="1970-01-01",
                overlap_group="synthetic_math_check",
                timing_basis="synthetic_fixture",
                known_source_fps=True,
                temporal_accuracy_valid=True,
                counts_for_cctv_accuracy=False,
                permitted_use="synthetic_timing_math_only",
                split="smoke",
                transformations="Deterministic 10 fps PTS trajectory check for cadence/gating math only",
            ),
        ],
        missing_data_matrix=[
            MissingDataEntry(
                stratum="stationary_dense_traffic_long_pts",
                required_conditions=">=30 min continuous fixed CCTV with trustworthy PTS and Indian mixed traffic",
                status="smoke_frames_only",
                blocked_activities=["line.crossed", "vehicle.stopped", "vehicle.wrong_way"],
                notes="TrafficCAM Noida has 30 frames without original PTS; UVH-26/BMD-45 are frame-only.",
            ),
            MissingDataEntry(
                stratum="stationary_people_dwell",
                required_conditions="Continuous fixed CCTV with stationary people >=60s for motion-gate & dwell recall",
                status="missing_long_pts",
                blocked_activities=["zone.dwell", "queue.long"],
                notes="Required before enabling motion gating or certifying dwell recall in production.",
            ),
            MissingDataEntry(
                stratum="empty_scenes_false_alarm",
                required_conditions="Multi-hour empty/low-activity scenes with foliage, shadows, and lighting transitions",
                status="missing_long_pts",
                blocked_activities=["object.present", "zone.dwell", "line.crossed"],
                notes="Required to bound <=0.1 false alert episodes per camera-hour.",
            ),
            MissingDataEntry(
                stratum="night_ir_monochrome",
                required_conditions="Fixed CCTV night monochrome IR and sodium/LED streetlighting clips",
                status="missing_long_pts",
                blocked_activities=["object.present", "zone.dwell", "line.crossed"],
                notes="Daylight-only models cannot claim night/IR precision or recall.",
            ),
            MissingDataEntry(
                stratum="headlight_glare_and_reflections",
                required_conditions="Night/dusk oncoming headlight bloom and wet-road reflections",
                status="missing_long_pts",
                blocked_activities=["line.crossed", "object.present"],
                notes="Needed to measure false vehicle/person triggers from specular glare.",
            ),
            MissingDataEntry(
                stratum="monsoon_rain_and_occlusion",
                required_conditions="Heavy rain streaks, lens droplets, and dense multi-wheeler occlusion",
                status="missing_long_pts",
                blocked_activities=["object.present", "line.crossed", "zone.dwell"],
                notes="All core activities remain marked experimental until scene-disjoint field footage is collected.",
            ),
        ],
        class_mapping=[
            *[
                ClassMappingEntry(
                    class_name=name,
                    coco_index=idx,
                    status="supported_coco80",
                    notes=f"COCO-80 class index {idx} in YOLOX Nano/Tiny.",
                )
                for idx, name in sorted(CLASSES.items())
            ],
            ClassMappingEntry(
                class_name="auto_rickshaw",
                coco_index=None,
                status="unsupported_by_coco80_head",
                notes="Visible in TrafficCAM Noida; COCO-80 YOLOX conflates into car/truck/motorcycle or misses.",
            ),
            ClassMappingEntry(
                class_name="cycle_rickshaw",
                coco_index=None,
                status="unsupported_by_coco80_head",
                notes="Visible in TrafficCAM Noida; requires India traffic fine-tuning (Plan 09).",
            ),
            ClassMappingEntry(
                class_name="e_rickshaw",
                coco_index=None,
                status="unsupported_by_coco80_head",
                notes="Absent from COCO-80 taxonomy; requires UVH-26/custom class head.",
            ),
            ClassMappingEntry(
                class_name="tractor",
                coco_index=None,
                status="unsupported_by_coco80_head",
                notes="Visible in TrafficCAM Noida; COCO-80 YOLOX maps to truck or misses.",
            ),
            ClassMappingEntry(
                class_name="tempo_traveller_lcv",
                coco_index=None,
                status="unsupported_by_coco80_head",
                notes="Indian light commercial vehicles require dedicated class mapping in Plan 09.",
            ),
        ],
        matching_tolerances=MatchingTolerances(),
        synthetic_timing_reference_events=[
            ReferenceEvent(
                activity="object.present",
                object_class="person",
                start_s=0.0,
                end_s=5.0,
                kind="positive",
                notes="Stationary person inside zone across 5.0s span (tests motion-gate safety).",
            ),
            ReferenceEvent(
                activity="zone.dwell",
                object_class="person",
                start_s=0.0,
                end_s=5.0,
                kind="positive",
                notes="Stationary person dwell >= 3.0s threshold inside zone.",
            ),
            ReferenceEvent(
                activity="line.crossed",
                object_class="car",
                start_s=2.0,
                end_s=2.0,
                direction="left_to_right",
                kind="positive",
                notes="Car crossing vertical line x=0.5 left to right.",
            ),
            ReferenceEvent(
                activity="zone.dwell",
                object_class="car",
                start_s=1.0,
                end_s=2.5,
                kind="hard_negative",
                notes="Transient car passing through zone for 1.5s (< 3.0s dwell threshold); must not emit dwell.",
            ),
            ReferenceEvent(
                activity="line.crossed",
                object_class="motorcycle",
                start_s=0.0,
                end_s=4.0,
                kind="hard_negative",
                notes="Motorcycle jittering within +/-0.015 deadband of x=0.5; must not emit crossing.",
            ),
        ],
    )
