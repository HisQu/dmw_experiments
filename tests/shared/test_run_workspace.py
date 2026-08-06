"""Tests for the self-contained generated run directory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dmw_experiments.shared.artifacts import RunWorkspace


def test_workspace_freezes_spec_and_keeps_logs_with_run(tmp_path: Path) -> None:
    """A fresh run owns its spec, service logs, and readable journal."""
    spec = tmp_path / "source.json"
    spec.write_text('{"run_id": "smoke"}\n', encoding="utf-8")

    workspace = RunWorkspace.create(tmp_path / "runs" / "smoke", spec)

    assert workspace.run_spec.read_bytes() == spec.read_bytes()
    assert workspace.babysit_log.parent == workspace.root / "logs"
    assert workspace.babysit_log.is_file()
    event = json.loads(
        workspace.events_file.read_text(encoding="utf-8").splitlines()[0]
    )
    assert event["event"] == "workspace_created"


def test_workspace_rejects_changed_resume_spec(tmp_path: Path) -> None:
    """A resume cannot silently replace the original run contract."""
    spec = tmp_path / "source.json"
    spec.write_text('{"run_id": "smoke"}\n', encoding="utf-8")
    workspace = RunWorkspace.create(tmp_path / "runs" / "smoke", spec)
    spec.write_text('{"run_id": "different"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="differs"):
        RunWorkspace.open(workspace.root, spec)


def test_workspace_service_registry_is_atomic_and_readable(
    tmp_path: Path,
) -> None:
    """Current unit names survive process handoffs as ordinary JSON."""
    spec = tmp_path / "source.json"
    spec.write_text("{}\n", encoding="utf-8")
    workspace = RunWorkspace.create(tmp_path / "run", spec)

    workspace.write_services({"runner": "example-runner.service"})

    assert workspace.load_services() == {"runner": "example-runner.service"}
