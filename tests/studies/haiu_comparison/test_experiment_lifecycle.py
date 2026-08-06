"""Tests for multi-provider lifecycle status and runtime paths."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.shared.supervision import UserServiceManager
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


def test_default_python_keeps_active_interpreter_path() -> None:
    """Service commands retain the active virtual-environment executable."""
    runtime = RuntimePaths.from_config(AppRuntimeConfig())

    assert runtime.publication_python.is_absolute()
    assert runtime.publication_python.name.startswith("python")
