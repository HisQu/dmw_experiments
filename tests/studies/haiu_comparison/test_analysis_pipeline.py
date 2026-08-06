"""Tests for the one-run analysis entry point."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from dmw_experiments.studies.haiu_comparison.analysis import (
    pipeline as run_analysis,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    RUN_TEMPLATE_ROOT,
)


def _run(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    shutil.copytree(RUN_TEMPLATE_ROOT, root)
    return root


def test_run_analysis_routes_both_executions_into_one_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One command derives provider workbooks, review data, and plots."""
    root = _run(tmp_path)
    calls: list[tuple[object, ...]] = []

    def fake_export_run(run_dir: Path, **_: object) -> SimpleNamespace:
        calls.append(("export", run_dir))
        return SimpleNamespace(workbook=run_dir / "overview.xlsx")

    def fake_review(**kwargs: object) -> SimpleNamespace:
        calls.append(("review", kwargs["workbook_path"]))
        return SimpleNamespace(workbook=kwargs["workbook_path"])

    def fake_plots(workbooks: list[Path], **kwargs: object) -> Path:
        calls.append(("plots", *workbooks))
        return Path(str(kwargs["output_root"])) / "plots-test"

    monkeypatch.setattr(run_analysis, "export_run", fake_export_run)
    monkeypatch.setattr(
        run_analysis,
        "export_provider_historian_review_workbook",
        fake_review,
    )
    monkeypatch.setattr(run_analysis, "plot_workbooks", fake_plots)

    artifacts = run_analysis.run_analysis(
        run_dir=root,
        allow_partial=True,
        overwrite=True,
        timestamp="test",
    )

    assert calls[0] == ("export", root / "raw-academiccloud")
    assert calls[1] == ("export", root / "raw-lmstudio")
    assert artifacts.plots == root / "plots" / "plots-test"


def test_run_analysis_requires_complete_grade_source_pair(
    tmp_path: Path,
) -> None:
    """An evaluated workbook without its reveal key is unusable."""
    with pytest.raises(ValueError, match="requires both"):
        run_analysis.run_analysis(
            run_dir=_run(tmp_path),
            quality_review_workbook=tmp_path / "evaluated.xlsx",
        )
