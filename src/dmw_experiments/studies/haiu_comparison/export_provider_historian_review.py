#!/usr/bin/env python3
"""Export provider review rows and their separate evaluation sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.export_results_workbook import (
    export_provider_historian_evaluation_sidecar,
    export_provider_historian_review_workbook,
)


def main(argv: list[str] | None = None) -> int:
    """Create a combined review surface and guide sidecar.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    review_workbook_path = Path(args.output)
    if args.sidecar_only:
        sidecar = export_provider_historian_evaluation_sidecar(
            academiccloud_run_dir=Path(args.academiccloud_run_dir),
            lmstudio_run_dir=Path(args.lmstudio_run_dir),
            review_workbook_path=review_workbook_path,
            allow_partial=args.allow_partial,
            overwrite=args.overwrite,
        )
        print(f"Evaluation sidecar: {sidecar}")
        return 0

    paths = export_provider_historian_review_workbook(
        academiccloud_run_dir=Path(args.academiccloud_run_dir),
        lmstudio_run_dir=Path(args.lmstudio_run_dir),
        workbook_path=review_workbook_path,
        allow_partial=args.allow_partial,
        overwrite=args.overwrite,
    )
    print(f"Provider review workbook: {paths.workbook}")
    print(f"Evaluation sidecar: {paths.evaluation_sidecar}")
    print(f"Provider reveal key: {paths.reveal_key}")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build command-line arguments for the provider comparison workbook.

    :return: Configured command-line parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Export AcademicCloud and LM Studio review worksheets with a "
            "separate guide and ontology-catalogue sidecar."
        )
    )
    parser.add_argument(
        "academiccloud_run_dir",
        help="RESULTS/<academiccloud-run-id> directory.",
    )
    parser.add_argument(
        "lmstudio_run_dir",
        help="RESULTS/<lmstudio-run-id> directory.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Combined .xlsx destination outside individual analysis directories.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Create a clearly labelled diagnostic workbook from partial runs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only this command's workbook, sidecar, and reveal key.",
    )
    parser.add_argument(
        "--sidecar-only",
        action="store_true",
        help=(
            "Refresh only the evaluation sidecar for an existing review "
            "workbook; never modify its manual rows or reveal key."
        ),
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
