"""Tests for lifecycle validation and durable status counting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from dmw_experiments.artifacts import RunWorkspace
from dmw_experiments.config import AppRuntimeConfig
from dmw_experiments.execution.lifecycle import ExperimentLifecycle
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.operations.run_spec import (
    load_header_sublemma_run_spec,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.paths import (
    SPEC_ROOT,
)
from dmw_experiments.supervision.systemd_services import UserServiceManager


def _inactive_command_runner(
    command: list[str],
    **_: Any,
) -> subprocess.CompletedProcess[str]:
    """Return systemd's loaded-but-inactive property output.

    :param command: Argument vector retained in the completed record.
    :param _: Ignored subprocess keyword arguments.
    :return: Successful inactive service inspection.
    """
    return subprocess.CompletedProcess(command, 0, "loaded\ninactive\n", "")


def test_status_distinguishes_success_failure_and_retry(
    tmp_path: Path,
) -> None:
    """Raw rows are terminal evidence while retry-pending remains provisional."""
    spec_path = SPEC_ROOT / "academiccloud-header-sublemma-smoke.json"
    spec = load_header_sublemma_run_spec(spec_path)
    output = tmp_path / "output"
    workspace = RunWorkspace.create(spec.result_directory(output), spec_path)
    first = workspace.root / "raw" / spec.conditions[0] / "unit.json"
    first.parent.mkdir(parents=True)
    first.write_text(json.dumps({"success": False}), encoding="utf-8")
    attempt = workspace.root / "attempts" / spec.conditions[0] / "unit.json"
    attempt.parent.mkdir(parents=True)
    attempt.write_text(
        json.dumps({"status": "retry_pending"}), encoding="utf-8"
    )
    environment = tmp_path / "provider.env"
    environment.write_text("DATAMODEL_LOGIN=test\n", encoding="utf-8")
    config = AppRuntimeConfig(
        storage_root=output,
        academiccloud_env_file=environment,
    )
    lifecycle = ExperimentLifecycle(
        config=config,
        services=UserServiceManager(runner=_inactive_command_runner),
    )

    status = lifecycle.status(spec_path)

    assert status.expected_cells == 3
    assert status.terminal_cells == 1
    assert status.failed_cells == 1
    assert status.retry_pending_cells == 1
    assert status.strict_analysis_ready is False


def test_validate_rejects_smoke_spec_for_full_command(tmp_path: Path) -> None:
    """The obvious full-run command cannot launch a one-unit contract."""
    environment = tmp_path / "provider.env"
    environment.write_text("DATAMODEL_LOGIN=test\n", encoding="utf-8")
    config = AppRuntimeConfig(
        storage_root=tmp_path / "output",
        publication_python=Path(__file__),
        academiccloud_env_file=environment,
    )
    lifecycle = ExperimentLifecycle(
        config=config,
        services=UserServiceManager(runner=_inactive_command_runner),
    )

    try:
        lifecycle.validate(
            SPEC_ROOT / "academiccloud-header-sublemma-smoke.json",
            expected_mode="full",
        )
    except ValueError as error:
        assert "requires a 'full' run spec" in str(error)
    else:
        raise AssertionError("Smoke spec unexpectedly passed full validation.")
