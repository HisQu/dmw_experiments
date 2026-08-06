"""Tests for copied run creation and explicit publication preparation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.operations import promotion
from dmw_experiments.studies.haiu_comparison.operations import run_factory
from dmw_experiments.studies.haiu_comparison.operations.promotion import (
    prepare_promotion,
)
from dmw_experiments.studies.haiu_comparison.operations.run_factory import (
    NewRunRequest,
    create_run,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)


def test_create_run_copies_the_template_into_the_selected_area(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full_root = tmp_path / "full"
    smoke_root = tmp_path / "smoke"
    monkeypatch.setattr(run_factory, "FULL_RUNS_ROOT", full_root)
    monkeypatch.setattr(run_factory, "SMOKE_RUNS_ROOT", smoke_root)

    created = create_run(
        NewRunRequest(
            run_id="provider-smoke",
            mode="smoke",
            executions=("academiccloud",),
        )
    )
    spec = load_run_contract(created)

    assert created == smoke_root / "provider-smoke"
    assert spec.limit == 1
    assert spec.mode == "smoke"
    assert [item.name for item in spec.enabled_executions] == ["academiccloud"]
    assert (created / "INPUTS" / "header_sublemma_input_catalog.json").is_file()


def test_prepare_promotion_replaces_template_placeholder_with_distributions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_root = tmp_path / "smoke"
    monkeypatch.setattr(run_factory, "SMOKE_RUNS_ROOT", smoke_root)
    run_root = create_run(
        NewRunRequest(
            run_id="publishable-smoke",
            mode="smoke",
            executions=("academiccloud",),
        )
    )
    spec = load_run_contract(run_root)
    execution = spec.execution("academiccloud")
    for condition in spec.conditions:
        result_dir = (
            run_root / execution.output_directory_name / f"result-{condition}"
        )
        (result_dir / "unit.json").write_text("{}\n", encoding="utf-8")

    def fake_build(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        output_dir = Path(arguments[arguments.index("--outdir") + 1])
        (output_dir / "dmw_experiments-0.3.0-py3-none-any.whl").touch()
        (output_dir / "dmw_experiments-0.3.0.tar.gz").touch()
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(promotion.subprocess, "run", fake_build)

    artifacts = prepare_promotion(run_root)

    assert artifacts.terminal_cells == 3
    assert artifacts.expected_cells == 3
    assert len(artifacts.distribution_files) == 2
    assert not (run_root / "locks" / "dist" / ".gitkeep").exists()
