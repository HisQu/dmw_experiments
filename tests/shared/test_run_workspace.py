"""Tests for operational evidence inside a copied run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dmw_experiments.shared.artifacts import RunWorkspace


def _workspace(tmp_path: Path) -> RunWorkspace:
    root = tmp_path / "smoke"
    root.mkdir()
    (root / "run.toml").write_text('run_id = "smoke"\n', encoding="utf-8")
    return RunWorkspace.open(root, "academiccloud")


def test_workspace_freezes_contract_and_keeps_logs_with_run(
    tmp_path: Path,
) -> None:
    """A provider journal and immutable digest remain inside the run."""
    workspace = _workspace(tmp_path)

    workspace.freeze_contract()
    workspace.append_babysit(heading="Started", bullets=("Contract frozen.",))

    assert workspace.run_spec_digest.is_file()
    assert workspace.babysit_log.parent == workspace.root / "logs"
    event = json.loads(workspace.events_file.read_text().splitlines()[0])
    assert event["event"] == "run_contract_frozen"


def test_workspace_rejects_changed_resume_contract(tmp_path: Path) -> None:
    """A resume cannot silently replace the first-launch TOML."""
    workspace = _workspace(tmp_path)
    workspace.freeze_contract()
    workspace.run_spec.write_text('run_id = "different"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="differs"):
        workspace.require_frozen_contract()


def test_workspace_service_registry_is_provider_specific(
    tmp_path: Path,
) -> None:
    """Provider unit names survive process handoffs as ordinary JSON."""
    workspace = _workspace(tmp_path)

    workspace.write_services({"runner": "example-runner.service"})

    assert workspace.load_services() == {"runner": "example-runner.service"}
    assert workspace.services_file.name == "academiccloud-services.json"
