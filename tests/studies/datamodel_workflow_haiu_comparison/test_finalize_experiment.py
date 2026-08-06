"""Tests for the operational final-analysis completion gate."""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from dmw_experiments.supervision import finalizer


@pytest.fixture
def finalizer_module():
    """Return the packaged final-analysis gate.

    :return: Imported finalizer module.
    """
    return finalizer


def _write_json(path: Path, payload: object) -> None:
    """Create one JSON fixture file.

    :param path: Target fixture path.
    :param payload: JSON-compatible content.
    :return: ``None`` after writing the fixture.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_inspect_run_matrix_requires_all_terminal_cells(
    tmp_path: Path,
    finalizer_module: ModuleType,
) -> None:
    """Missing observations and retry-pending rows keep export gated."""
    run_dir = tmp_path / "run"
    regest_ids = ["alpha", "beta"]
    _write_json(
        run_dir / "summaries" / "run_manifest.json",
        {"regest_ids": regest_ids},
    )

    incomplete = finalizer_module.inspect_run_matrix(run_dir)

    assert incomplete.expected_cells == 6
    assert incomplete.raw_cells == 0
    assert len(incomplete.missing_cells) == 6
    assert not incomplete.is_complete

    for condition in finalizer_module.CONDITIONS:
        for regest_id in regest_ids:
            _write_json(
                run_dir / "raw" / condition / f"{regest_id}.json",
                {"condition": condition, "regest_id": regest_id},
            )
    _write_json(
        run_dir / "attempts" / "workflow_rag" / "alpha.json",
        {"status": "retry_pending"},
    )

    retry_pending = finalizer_module.inspect_run_matrix(run_dir)

    assert retry_pending.raw_cells == 6
    assert retry_pending.missing_cells == ()
    assert retry_pending.retry_pending_cells == ("workflow_rag/alpha",)
    assert not retry_pending.is_complete

    _write_json(
        run_dir / "attempts" / "workflow_rag" / "alpha.json",
        {"status": "complete"},
    )

    complete = finalizer_module.inspect_run_matrix(run_dir)

    assert complete.is_complete


def test_run_final_analysis_uses_strict_export(
    tmp_path: Path,
    finalizer_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finalization materializes both runs before one non-partial export."""
    calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], *, check: bool, cwd: Path) -> None:
        assert check
        calls.append((command, cwd))

    monkeypatch.setattr(finalizer_module.subprocess, "run", fake_run)
    experiment_dir = tmp_path / "experiment"
    academiccloud_run_dir = tmp_path / "results" / "academiccloud"
    lmstudio_run_dir = tmp_path / "results" / "lmstudio"

    finalizer_module.run_final_analysis(
        experiment_dir=experiment_dir,
        analysis_python=tmp_path / "python",
        materialize_script=experiment_dir / "materialize_raw_artifacts.py",
        analysis_script=experiment_dir / "run_analysis.py",
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        output_root=tmp_path / "results",
        quality_review_workbook=tmp_path / "evaluated.xlsx",
        quality_reveal_key=tmp_path / "reveal_key.json",
        timestamp="final",
    )

    assert len(calls) == 3
    assert calls[0][0][-1] == str(academiccloud_run_dir)
    assert calls[1][0][-1] == str(lmstudio_run_dir)
    analysis_command = calls[2][0]
    assert "--allow-partial" not in analysis_command
    assert "--overwrite" in analysis_command
    assert "--audit-csv" in analysis_command
    assert analysis_command[-2:] == ["--timestamp", "final"]
    assert {cwd for _, cwd in calls} == {experiment_dir}
