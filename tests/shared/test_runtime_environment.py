"""Tests for exhaustive run-local environment contracts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dmw_experiments.shared.config.runtime_environment import (
    validate_run_environment_contract,
)
from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
    load_run_spec,
)
from dmw_experiments.studies.haiu_comparison.paths import RUN_TEMPLATE_ROOT


def _copied_template(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    shutil.copytree(RUN_TEMPLATE_ROOT, root)
    return root


def test_complete_shared_and_provider_contract_is_accepted(
    tmp_path: Path,
) -> None:
    """The tracked template names every measured setting without secrets."""
    root = _copied_template(tmp_path)
    execution = load_run_spec(root).execution("academiccloud")

    shared, provider = validate_run_environment_contract(root, execution)

    assert shared.name == "run.env"
    assert provider.name == "run.academiccloud.env"


def test_active_real_secret_is_rejected(tmp_path: Path) -> None:
    """Credential values cannot enter a copied run directory."""
    root = _copied_template(tmp_path)
    shared = root / "run.env"
    shared.write_text(
        shared.read_text(encoding="utf-8") + "\nMONGO_URI=secret\n",
        encoding="utf-8",
    )
    execution = load_run_spec(root).execution("academiccloud")

    with pytest.raises(ValueError, match="must not assign secret"):
        validate_run_environment_contract(root, execution)
