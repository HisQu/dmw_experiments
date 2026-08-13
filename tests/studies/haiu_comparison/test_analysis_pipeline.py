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
        calls.append(("export", run_dir, _["timestamp"]))
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

    assert calls[0] == ("export", root / "raw-academiccloud", "test")
    assert calls[1] == ("export", root / "raw-lmstudio", "test")
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


def test_successful_analysis_archives_only_older_generated_workbooks(
    tmp_path: Path,
) -> None:
    """Keep one active snapshot without moving a human evaluation input."""
    root = tmp_path / "run"
    workbooks = root / "analysis/workbooks/academiccloud"
    workbooks.mkdir(parents=True)
    old_stamp = "20260813T100000CEST"
    current_stamp = "20260813T110000CEST"
    old_names = (
        f"overview-{old_stamp}.xlsx",
        f"masked_historian_quality_review-{old_stamp}.xlsx",
        f"masked_historian_quality_review-{old_stamp}_evaluation_sidecar.xlsx",
        f"historian_quality_review_reveal_key-{old_stamp}.json",
    )
    current_names = tuple(
        name.replace(old_stamp, current_stamp) for name in old_names
    )
    for name in (*old_names, *current_names):
        (workbooks / name).write_text(name, encoding="utf-8")
    evaluated = workbooks / "masked_historian_quality_review_evaluated.xlsx"
    evaluated.write_text("human grades", encoding="utf-8")

    archived = run_analysis._archive_superseded_provider_workbook_snapshots(
        root=root,
        execution_names=("academiccloud",),
        current_timestamp=current_stamp,
    )

    assert {path.name for path in archived} == set(old_names)
    assert all(not (workbooks / name).exists() for name in old_names)
    assert all((workbooks / name).is_file() for name in current_names)
    assert evaluated.is_file()


def test_run_analysis_uses_only_enabled_provider_executions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An AcademicCloud-only run exports without cross-provider review."""
    root = _run(tmp_path)
    run_spec = root / "run.toml"
    run_spec.write_text(
        run_spec.read_text(encoding="utf-8").replace(
            "[executions.lmstudio]\nenabled = true",
            "[executions.lmstudio]\nenabled = false",
        ),
        encoding="utf-8",
    )
    calls: list[tuple[object, ...]] = []

    def fake_export_run(run_dir: Path, **_: object) -> SimpleNamespace:
        calls.append(("export", run_dir, _["timestamp"]))
        return SimpleNamespace(workbook=run_dir / "overview.xlsx")

    def reject_review(**_: object) -> SimpleNamespace:
        raise AssertionError("A one-provider run has no provider comparison.")

    def fake_plots(workbooks: list[Path], **kwargs: object) -> Path:
        calls.append(("plots", *workbooks))
        return Path(str(kwargs["output_root"])) / "plots-test"

    monkeypatch.setattr(run_analysis, "export_run", fake_export_run)
    monkeypatch.setattr(
        run_analysis,
        "export_provider_historian_review_workbook",
        reject_review,
    )
    monkeypatch.setattr(run_analysis, "plot_workbooks", fake_plots)

    artifacts = run_analysis.run_analysis(
        run_dir=root,
        overwrite=True,
        timestamp="test",
    )

    assert calls == [
        ("export", root / "raw-academiccloud", "test"),
        ("plots", root / "raw-academiccloud" / "overview.xlsx"),
    ]
    assert set(artifacts.providers) == {"academiccloud"}
    assert artifacts.provider_review is None
