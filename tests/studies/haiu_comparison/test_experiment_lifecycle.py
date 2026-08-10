"""Tests for multi-provider lifecycle status and runtime paths."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from dmw_experiments.shared.artifacts import RunWorkspace
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.shared.supervision import UserServiceManager
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)
from dmw_experiments.studies.haiu_comparison.operations.lifecycle import (
    ExperimentLifecycle,
)
from dmw_experiments.studies.haiu_comparison.operations.runtime import (
    RuntimePaths,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    RUN_TEMPLATE_ROOT,
)


def _inactive_runner(
    command: list[str], **_: Any
) -> subprocess.CompletedProcess[str]:
    """Return a loaded but inactive systemd state."""
    return subprocess.CompletedProcess(command, 0, "loaded\ninactive\n", "")


def _active_runner(
    command: list[str], **_: Any
) -> subprocess.CompletedProcess[str]:
    """Return a loaded and active systemd state for safety checks."""
    return subprocess.CompletedProcess(command, 0, "loaded\nactive\n", "")


def _smoke_run(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    shutil.copytree(RUN_TEMPLATE_ROOT, root)
    contract = root / "run.toml"
    text = contract.read_text(encoding="utf-8")
    text = text.replace('mode = "full"', 'mode = "smoke"').replace(
        "limit = 0", "limit = 1"
    )
    contract.write_text(text, encoding="utf-8")
    return root


def test_status_distinguishes_provider_success_failure_and_retry(
    tmp_path: Path,
) -> None:
    """Terminal rows and provisional retry checkpoints remain distinct."""
    root = _smoke_run(tmp_path)
    result = (
        root
        / "raw-academiccloud"
        / "result-workflow_full_ontology"
        / "unit.json"
    )
    result.write_text(json.dumps({"success": False}), encoding="utf-8")
    attempt = (
        root
        / "raw-academiccloud"
        / "intermediates-workflow_full_ontology"
        / "unit.attempt.json"
    )
    attempt.write_text(
        json.dumps({"status": "retry_pending"}), encoding="utf-8"
    )
    lifecycle = ExperimentLifecycle(
        config=AppRuntimeConfig(),
        services=UserServiceManager(runner=_inactive_runner),
    )

    status = lifecycle.status(root, execution_names=("academiccloud",))

    provider = status.executions["academiccloud"]
    assert provider.expected_cells == 3
    assert provider.terminal_cells == 1
    assert provider.failed_cells == 1
    assert provider.retry_pending_cells == 1
    assert provider.strict_analysis_ready is False


def test_status_reads_nested_schema_v3_results_and_checkpoints(
    tmp_path: Path,
) -> None:
    """Count per-unit result bundles without relying on flat legacy files."""
    root = _smoke_run(tmp_path)
    result = (
        root
        / "raw-academiccloud"
        / "result-workflow_full_ontology"
        / "unit"
        / "result.json"
    )
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "record_type": "haiu_comparison_terminal_cell",
                "outcome": {"success": True},
            }
        ),
        encoding="utf-8",
    )
    checkpoint = (
        root
        / "raw-academiccloud"
        / "intermediates-workflow_rag"
        / "unit"
        / "checkpoint.json"
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(
        json.dumps({"status": "retry_pending"}),
        encoding="utf-8",
    )
    lifecycle = ExperimentLifecycle(
        config=AppRuntimeConfig(),
        services=UserServiceManager(runner=_inactive_runner),
    )

    status = lifecycle.status(root, execution_names=("academiccloud",))

    provider = status.executions["academiccloud"]
    assert provider.terminal_cells == 1
    assert provider.successful_cells == 1
    assert provider.failed_cells == 0
    assert provider.retry_pending_cells == 1


@pytest.mark.parametrize(
    "operation",
    ("refresh_artifacts", "adopt_runtime_transition"),
)
def test_runtime_patch_operations_refuse_active_provider_services(
    tmp_path: Path,
    operation: str,
) -> None:
    root = _smoke_run(tmp_path)
    lifecycle = ExperimentLifecycle(
        config=AppRuntimeConfig(),
        services=UserServiceManager(runner=_active_runner),
    )
    kwargs: dict[str, object] = {
        "execution_names": ("academiccloud",),
    }
    if operation == "adopt_runtime_transition":
        kwargs["reason"] = "test transition"

    with pytest.raises(RuntimeError, match="Pause the execution"):
        getattr(lifecycle, operation)(root, **kwargs)


def test_artifact_migration_refuses_active_provider_services(
    tmp_path: Path,
) -> None:
    """Require an explicit durable pause before changing artifact paths."""
    root = _smoke_run(tmp_path)
    lifecycle = ExperimentLifecycle(
        config=AppRuntimeConfig(),
        services=UserServiceManager(runner=_active_runner),
    )

    with pytest.raises(RuntimeError, match="Pause the execution"):
        lifecycle.migrate_artifacts(
            root,
            execution_names=("academiccloud",),
        )


def test_default_python_keeps_active_interpreter_path() -> None:
    """Service commands retain the active virtual-environment executable."""
    runtime = RuntimePaths.from_config(AppRuntimeConfig())

    assert runtime.publication_python.is_absolute()
    assert runtime.publication_python.name.startswith("python")


def test_haiu_storage_is_created_for_new_run_and_required_for_resume(
    tmp_path: Path,
) -> None:
    """Fresh starts own Haiu storage and resumptions require that evidence."""
    root = _smoke_run(tmp_path)
    execution = load_run_contract(root).execution("academiccloud")
    workspace = RunWorkspace.open(root, execution.name)
    lifecycle = ExperimentLifecycle(
        config=AppRuntimeConfig(),
        services=UserServiceManager(runner=_inactive_runner),
    )

    storage = lifecycle._prepare_haiu_storage(
        workspace=workspace,
        execution=execution,
        resume=False,
    )

    assert storage == root / "environment" / "haiu-academiccloud"
    assert storage.is_dir()
    storage.rmdir()
    with pytest.raises(ValueError, match="Cannot resume without Haiu storage"):
        lifecycle._prepare_haiu_storage(
            workspace=workspace,
            execution=execution,
            resume=True,
        )
