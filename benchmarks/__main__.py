"""Command-line entry point for the Plan 01 CCTV benchmark harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from avalokan.settings import ROOT, Settings

from .harness import (
    ensure_model_artifact,
    ensure_noida_smoke_dataset,
    run_full_benchmark,
)
from .ledger import default_ledger, dhash_64, validate_partition_integrity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description="Avalokan CCTV benchmark harness and dataset/license ledger (Plan 01).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch_p = sub.add_parser("fetch", help="Fetch and verify bounded smoke frames and ONNX models.")
    fetch_p.add_argument(
        "--allow-agpl",
        action="store_true",
        help="Explicitly allow fetching AGPL-licensed comparison models.",
    )

    sub.add_parser("validate-manifest", help="Validate dataset/model ledger and split integrity.")

    run_p = sub.add_parser(
        "run", help="Run stage-isolated, model/thread/INT8, and schedule benchmarks."
    )
    run_p.add_argument(
        "--trials", type=int, default=3, help="Interleaved trials per model profile."
    )
    run_p.add_argument("--warmup", type=int, default=6, help="Warmup calls before measurement.")
    run_p.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".amp/in/artifacts/benchmark-plan01.json",
        help="Path to write JSON benchmark report.",
    )

    args = parser.parse_args(argv)
    settings = Settings()
    ledger = default_ledger()

    if args.command == "fetch":
        frames, clip = ensure_noida_smoke_dataset(ledger)
        models = {}
        for spec in ledger.models:
            if spec.precision != "fp32":
                continue
            if spec.requires_explicit_license_opt_in and not args.allow_agpl:
                models[spec.id] = "skipped (requires --allow-agpl)"
                continue
            path = ensure_model_artifact(spec, settings=settings, allow_agpl=args.allow_agpl)
            models[spec.id] = str(path.relative_to(ROOT))
        print(
            json.dumps(
                {
                    "status": "ok",
                    "noida_frames": len(frames),
                    "noida_smoke_clip": str(clip.relative_to(ROOT)),
                    "models": models,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "validate-manifest":
        import cv2

        frames, _clip = ensure_noida_smoke_dataset(ledger)
        hashes = [dhash_64(cv2.imread(str(p))) for p in frames]
        integrity = validate_partition_integrity(
            ledger.sequences,
            frame_hashes_by_sequence={"trafficcam_noida_smoke": hashes},
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "schema_version": ledger.schema_version,
                    "models": len(ledger.models),
                    "sequences": len(ledger.sequences),
                    "missing_data_strata": len(ledger.missing_data_matrix),
                    "supported_classes": [
                        c.class_name for c in ledger.class_mapping if c.status == "supported_coco80"
                    ],
                    "unsupported_indian_subclasses": [
                        c.class_name
                        for c in ledger.class_mapping
                        if c.status == "unsupported_by_coco80_head"
                    ],
                    "partition_integrity": integrity,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "run":
        report = run_full_benchmark(trials=args.trials, warmup_calls=args.warmup, settings=settings)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(args.output),
                    "pareto_optimal_profiles": [
                        p["profile_id"]
                        for p in report["model_thread_precision_pareto"]
                        if p["pareto_optimal"]
                    ],
                    "provisional_low_compute": report["provisional_profile_for_plan_03"][
                        "low_compute_profile"
                    ]["model_id"],
                },
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
