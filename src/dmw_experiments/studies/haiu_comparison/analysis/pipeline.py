#!/usr/bin/env python3
"""Regenerate every derived Haiu comparison artifact from one run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.analysis.workbooks.results import (
    ExportPaths,
    HistorianProviderComparisonPaths,
    export_provider_historian_review_workbook,
    export_run,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)
from dmw_experiments.studies.haiu_comparison.analysis.plots.results import (
    plot_workbooks,
)


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    """Collect every derived artifact emitted by one invocation.

    :param providers: Provider-specific workbook exports keyed by execution.
    :param provider_review: Fresh ungraded cross-provider review export when
        both provider executions are enabled.
    :param plots: Timestamped figure and grade-analysis directory.
    """

    providers: dict[str, ExportPaths]
    provider_review: HistorianProviderComparisonPaths | None
    plots: Path


def run_analysis(
    *,
    run_dir: Path,
    allow_partial: bool = False,
    audit_csv: bool = False,
    overwrite: bool = False,
    timestamp: str | None = None,
    quality_review_workbook: Path | None = None,
    quality_reveal_key: Path | None = None,
) -> AnalysisArtifacts:
    """Export workbooks, a review packet, and figures inside one run.

    :param run_dir: Complete copied run containing enabled provider executions.
    :param allow_partial: Permit labelled diagnostics before all cells finish.
    :param audit_csv: Emit machine-readable raw-derived audit tables.
    :param overwrite: Replace exporter-owned workbook files.
    :param timestamp: Stable plot timestamp for tests or repeatable exports.
    :param quality_review_workbook: Optional separately evaluated review input.
    :param quality_reveal_key: Matching reveal key for the evaluated workbook.
    :return: Paths to provider workbooks, review files, and plots.
    :raises ValueError: If enabled provider data or paired grade inputs are
        missing.
    """
    if (quality_review_workbook is None) != (quality_reveal_key is None):
        raise ValueError(
            "Historian grade analysis requires both quality_review_workbook "
            "and quality_reveal_key."
        )
    root = run_dir.expanduser().resolve()
    spec = load_run_contract(root)
    enabled = tuple(execution.name for execution in spec.enabled_executions)
    missing = [name for name in enabled if not (root / f"raw-{name}").is_dir()]
    if missing:
        raise ValueError(
            "Analysis requires enabled provider directories: "
            + ", ".join(missing)
        )

    stamp = timestamp or datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%Z")
    providers = {
        name: export_run(
            root / f"raw-{name}",
            allow_partial=allow_partial,
            audit_csv=audit_csv,
            overwrite=overwrite,
        )
        for name in enabled
    }
    provider_review: HistorianProviderComparisonPaths | None = None
    if set(enabled) == {"academiccloud", "lmstudio"}:
        review_path = (
            root
            / "analysis"
            / "workbooks"
            / f"historian_quality_review_academiccloud_lmstudio_{stamp}.xlsx"
        )
        if quality_review_workbook is not None and (
            quality_review_workbook.expanduser().resolve()
            == review_path.resolve()
        ):
            raise ValueError(
                "The fresh ungraded review cannot replace the evaluated input."
            )
        provider_review = export_provider_historian_review_workbook(
            academiccloud_run_dir=root / "raw-academiccloud",
            lmstudio_run_dir=root / "raw-lmstudio",
            workbook_path=review_path,
            allow_partial=allow_partial,
            overwrite=overwrite,
        )
    plots = plot_workbooks(
        [providers[name].workbook for name in enabled],
        output_root=root / "plots",
        timestamp=stamp,
        quality_review_workbook=quality_review_workbook,
        quality_reveal_key=quality_reveal_key,
    )
    return AnalysisArtifacts(
        providers=providers,
        provider_review=provider_review,
        plots=plots,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the single-run analysis interface.

    :return: Configured command-line parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--audit-csv", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timestamp")
    parser.add_argument("--quality-review-workbook", type=Path)
    parser.add_argument("--quality-reveal-key", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the complete raw-data analysis pipeline.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    artifacts = run_analysis(
        run_dir=args.run_dir,
        allow_partial=args.allow_partial,
        audit_csv=args.audit_csv,
        overwrite=args.overwrite,
        timestamp=args.timestamp,
        quality_review_workbook=args.quality_review_workbook,
        quality_reveal_key=args.quality_reveal_key,
    )
    for name, provider in artifacts.providers.items():
        print(f"{name} workbook: {provider.workbook}")
    if artifacts.provider_review is not None:
        print(f"Fresh provider review: {artifacts.provider_review.workbook}")
    print(f"Plots and grade analysis: {artifacts.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
