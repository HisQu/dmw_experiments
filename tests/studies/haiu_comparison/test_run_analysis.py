from pathlib import Path
from types import SimpleNamespace

import pytest

from dmw_experiments.studies.haiu_comparison import (
    run_analysis,
)


def test_run_analysis_delegates_to_existing_exporters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One command forwards the exact inputs to the existing pipeline layers."""
    academiccloud_run_dir = tmp_path / "results/academiccloud"
    lmstudio_run_dir = tmp_path / "results/lmstudio"
    review_output = tmp_path / "results/fresh_review.xlsx"
    evaluated_review = tmp_path / "results/evaluated_review.xlsx"
    reveal_key = tmp_path / "results/evaluated_review_reveal_key.json"
    calls: list[tuple[object, ...]] = []

    def fake_export_run(
        run_dir: Path,
        *,
        allow_partial: bool,
        audit_csv: bool,
        overwrite: bool,
    ) -> SimpleNamespace:
        calls.append(
            ("export_run", run_dir, allow_partial, audit_csv, overwrite)
        )
        return SimpleNamespace(workbook=run_dir / "analysis/overview.xlsx")

    def fake_provider_review(
        *,
        academiccloud_run_dir: Path,
        lmstudio_run_dir: Path,
        workbook_path: Path,
        allow_partial: bool,
        overwrite: bool,
    ) -> SimpleNamespace:
        calls.append(
            (
                "provider_review",
                academiccloud_run_dir,
                lmstudio_run_dir,
                workbook_path,
                allow_partial,
                overwrite,
            )
        )
        return SimpleNamespace(
            workbook=workbook_path,
            reveal_key=workbook_path.with_name("fresh_review_reveal_key.json"),
        )

    def fake_plot_workbooks(
        workbooks: list[Path],
        *,
        output_root: Path,
        timestamp: str,
        quality_review_workbook: Path,
        quality_reveal_key: Path,
    ) -> Path:
        calls.append(
            (
                "plot_workbooks",
                workbooks,
                output_root,
                timestamp,
                quality_review_workbook,
                quality_reveal_key,
            )
        )
        return output_root / f"plots-{timestamp}"

    monkeypatch.setattr(run_analysis, "export_run", fake_export_run)
    monkeypatch.setattr(
        run_analysis,
        "export_provider_historian_review_workbook",
        fake_provider_review,
    )
    monkeypatch.setattr(run_analysis, "plot_workbooks", fake_plot_workbooks)

    artifacts = run_analysis.run_analysis(
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        provider_review_workbook=review_output,
        output_root=tmp_path / "results",
        allow_partial=True,
        audit_csv=True,
        overwrite=True,
        timestamp="20260731T140000CEST",
        quality_review_workbook=evaluated_review,
        quality_reveal_key=reveal_key,
    )

    assert artifacts.plots == tmp_path / "results/plots-20260731T140000CEST"
    assert artifacts.provider_review.workbook == review_output
    assert calls == [
        ("export_run", academiccloud_run_dir, True, True, True),
        ("export_run", lmstudio_run_dir, True, True, True),
        (
            "provider_review",
            academiccloud_run_dir,
            lmstudio_run_dir,
            review_output,
            True,
            True,
        ),
        (
            "plot_workbooks",
            [
                academiccloud_run_dir / "analysis/overview.xlsx",
                lmstudio_run_dir / "analysis/overview.xlsx",
            ],
            tmp_path / "results",
            "20260731T140000CEST",
            evaluated_review,
            reveal_key,
        ),
    ]


def test_run_analysis_requires_complete_grade_source_pair(
    tmp_path: Path,
) -> None:
    """A review without its matching reveal key cannot be safely unmasked."""
    with pytest.raises(ValueError, match="requires both"):
        run_analysis.run_analysis(
            academiccloud_run_dir=tmp_path / "academiccloud",
            lmstudio_run_dir=tmp_path / "lmstudio",
            provider_review_workbook=tmp_path / "fresh_review.xlsx",
            output_root=tmp_path,
            quality_review_workbook=tmp_path / "evaluated_review.xlsx",
        )


def test_run_analysis_never_replaces_the_evaluated_review(
    tmp_path: Path,
) -> None:
    """A fresh review export cannot target the manual-grade source workbook."""
    evaluated_review = tmp_path / "evaluated_review.xlsx"
    with pytest.raises(ValueError, match="fresh ungraded review"):
        run_analysis.run_analysis(
            academiccloud_run_dir=tmp_path / "academiccloud",
            lmstudio_run_dir=tmp_path / "lmstudio",
            provider_review_workbook=evaluated_review,
            output_root=tmp_path,
            quality_review_workbook=evaluated_review,
            quality_reveal_key=tmp_path / "evaluated_review_reveal_key.json",
        )


def test_default_output_root_requires_sibling_run_directories(
    tmp_path: Path,
) -> None:
    """The default cannot guess a results root from unrelated source paths."""
    with pytest.raises(ValueError, match="--output-root"):
        run_analysis._default_output_root(
            tmp_path / "first/academiccloud",
            tmp_path / "second/lmstudio",
        )
