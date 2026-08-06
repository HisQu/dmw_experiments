#!/usr/bin/env python3
"""Run the reproducible DMW–Haiu analysis pipeline from raw observations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.export_results_workbook import (
    ExportPaths,
    HistorianProviderComparisonPaths,
    export_provider_historian_review_workbook,
    export_run,
)
from dmw_experiments.studies.haiu_comparison.plot_results_workbooks import (
    plot_workbooks,
)


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    """Collect every derived artifact emitted by one analysis invocation.

    :param academiccloud: Per-run export derived from AcademicCloud raw rows.
    :param lmstudio: Per-run export derived from LM Studio raw rows.
    :param provider_review: Fresh, ungraded provider-separated review export.
    :param plots: Timestamped figure and grade-analysis directory.
    """

    academiccloud: ExportPaths
    lmstudio: ExportPaths
    provider_review: HistorianProviderComparisonPaths
    plots: Path


def run_analysis(
    *,
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    provider_review_workbook: Path,
    output_root: Path,
    allow_partial: bool = False,
    audit_csv: bool = False,
    overwrite: bool = False,
    timestamp: str | None = None,
    quality_review_workbook: Path | None = None,
    quality_reveal_key: Path | None = None,
) -> AnalysisArtifacts:
    """Export per-run workbooks, an ungraded review, and all figures.

    The quality-review workbook is deliberately an independent input. A fresh
    review may gain packets as a run progresses, so this function never
    overwrites a human-evaluated review or its corresponding reveal key.

    :param academiccloud_run_dir: AcademicCloud ``output/runs/<run-id>`` directory.
    :param lmstudio_run_dir: LM Studio ``output/runs/<run-id>`` directory.
    :param provider_review_workbook: New ungraded review-workbook destination.
    :param output_root: Parent directory for timestamped plot exports.
    :param allow_partial: Label exports as diagnostic while either run remains
        incomplete.
    :param audit_csv: Emit machine-readable raw-derived audit tables.
    :param overwrite: Replace exporter-owned per-run and provider-review files.
    :param timestamp: Stable plot timestamp for reproducible or test exports.
    :param quality_review_workbook: Optional separately evaluated review input.
    :param quality_reveal_key: Matching reveal key for the evaluated workbook.
    :return: Paths to all generated derived artifacts.
    :raises ValueError: If historian-grade inputs are incomplete or would
        overwrite the separately evaluated workbook.
    """
    if (quality_review_workbook is None) != (quality_reveal_key is None):
        raise ValueError(
            "Historian grade analysis requires both quality_review_workbook "
            "and quality_reveal_key."
        )
    if (
        quality_review_workbook is not None
        and quality_review_workbook.expanduser().resolve()
        == provider_review_workbook.expanduser().resolve()
    ):
        raise ValueError(
            "provider_review_workbook must be a fresh ungraded review, not "
            "the separately evaluated quality_review_workbook."
        )

    academiccloud = export_run(
        academiccloud_run_dir,
        allow_partial=allow_partial,
        audit_csv=audit_csv,
        overwrite=overwrite,
    )
    lmstudio = export_run(
        lmstudio_run_dir,
        allow_partial=allow_partial,
        audit_csv=audit_csv,
        overwrite=overwrite,
    )
    provider_review = export_provider_historian_review_workbook(
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        workbook_path=provider_review_workbook,
        allow_partial=allow_partial,
        overwrite=overwrite,
    )
    plots = plot_workbooks(
        [academiccloud.workbook, lmstudio.workbook],
        output_root=output_root,
        timestamp=timestamp,
        quality_review_workbook=quality_review_workbook,
        quality_reveal_key=quality_reveal_key,
    )
    return AnalysisArtifacts(
        academiccloud=academiccloud,
        lmstudio=lmstudio,
        provider_review=provider_review,
        plots=plots,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the one-command raw-data analysis interface.

    :return: Configured command-line parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Export both raw DMW–Haiu runs, a fresh provider review, and "
            "timestamped plots in one reproducible invocation."
        )
    )
    parser.add_argument(
        "academiccloud_run_dir",
        type=Path,
        help="AcademicCloud output/runs/<run-id> directory.",
    )
    parser.add_argument(
        "lmstudio_run_dir",
        type=Path,
        help="LM Studio output/runs/<run-id> directory.",
    )
    parser.add_argument(
        "--provider-review-output",
        type=Path,
        help=(
            "Fresh ungraded provider-review workbook. Defaults to a "
            "timestamped file under --output-root."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help=(
            "Parent for timestamped review and plot artifacts. Defaults to "
            "the shared parent of both run directories."
        ),
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Label exports as diagnostic while either source run is incomplete.",
    )
    parser.add_argument(
        "--audit-csv",
        action="store_true",
        help="Also write raw-derived audit CSV files for each provider run.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Replace only exporter-owned per-run artifacts and the fresh "
            "provider-review destination. Never replaces plot directories."
        ),
    )
    parser.add_argument(
        "--timestamp",
        help=(
            "Stable timestamp used in plots-TIMESTAMP and the default review "
            "filename. Defaults to the current local time."
        ),
    )
    parser.add_argument(
        "--quality-review-workbook",
        type=Path,
        help=(
            "Optional separately evaluated historian review. Requires "
            "--quality-reveal-key."
        ),
    )
    parser.add_argument(
        "--quality-reveal-key",
        type=Path,
        help=(
            "Reveal key that exactly matches --quality-review-workbook. "
            "Requires --quality-review-workbook."
        ),
    )
    return parser


def _default_output_root(
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
) -> Path:
    """Find the shared results directory without guessing a host path.

    :param academiccloud_run_dir: AcademicCloud run directory.
    :param lmstudio_run_dir: LM Studio run directory.
    :return: Shared direct parent of both run directories.
    :raises ValueError: If runs are not siblings under one results directory.
    """
    academiccloud_parent = academiccloud_run_dir.expanduser().resolve().parent
    lmstudio_parent = lmstudio_run_dir.expanduser().resolve().parent
    if academiccloud_parent != lmstudio_parent:
        raise ValueError(
            "Use --output-root when provider run directories do not share "
            "one direct runs parent."
        )
    return academiccloud_parent


def _timestamp(value: str | None) -> str:
    """Choose a reusable timestamp for one coherent artifact set.

    :param value: Optional caller-provided timestamp.
    :return: Caller value or timezone-aware local timestamp.
    """
    return value or datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%Z")


def main(argv: list[str] | None = None) -> int:
    """Execute the complete raw-data analysis pipeline.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    timestamp = _timestamp(args.timestamp)
    output_root = (
        args.output_root.expanduser().resolve()
        if args.output_root is not None
        else _default_output_root(
            args.academiccloud_run_dir,
            args.lmstudio_run_dir,
        )
    )
    provider_review_workbook = (
        args.provider_review_output.expanduser().resolve()
        if args.provider_review_output is not None
        else output_root
        / f"historian_quality_review_academiccloud_lmstudio_{timestamp}.xlsx"
    )
    artifacts = run_analysis(
        academiccloud_run_dir=args.academiccloud_run_dir,
        lmstudio_run_dir=args.lmstudio_run_dir,
        provider_review_workbook=provider_review_workbook,
        output_root=output_root,
        allow_partial=args.allow_partial,
        audit_csv=args.audit_csv,
        overwrite=args.overwrite,
        timestamp=timestamp,
        quality_review_workbook=args.quality_review_workbook,
        quality_reveal_key=args.quality_reveal_key,
    )
    print(f"AcademicCloud workbook: {artifacts.academiccloud.workbook}")
    print(f"LM Studio workbook: {artifacts.lmstudio.workbook}")
    print(f"Fresh provider review: {artifacts.provider_review.workbook}")
    print(
        "Fresh provider evaluation sidecar: "
        f"{artifacts.provider_review.evaluation_sidecar}"
    )
    print(f"Fresh provider reveal key: {artifacts.provider_review.reveal_key}")
    print(f"Plots and grade analysis: {artifacts.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
