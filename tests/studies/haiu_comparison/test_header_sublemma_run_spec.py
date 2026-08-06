"""Tests for the copied-run TOML contract."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
    load_run_spec,
)
from dmw_experiments.studies.haiu_comparison.paths import RUN_TEMPLATE_ROOT


def _run(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    shutil.copytree(RUN_TEMPLATE_ROOT, root)
    return root


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_loads_both_isolated_provider_executions(tmp_path: Path) -> None:
    """One run owns independently named storage for both providers."""
    spec = load_run_spec(_run(tmp_path))

    assert [item.name for item in spec.enabled_executions] == [
        "academiccloud",
        "lmstudio",
    ]
    assert spec.execution("academiccloud").annotation_collection == (
        "annotations__template_academiccloud"
    )
    assert spec.execution("lmstudio").ontology_collection == (
        "ontologies__template_lmstudio"
    )


def test_rejects_unknown_toml_configuration(tmp_path: Path) -> None:
    """Credentials and ad-hoc fields cannot enter the scientific contract."""
    root = _run(tmp_path)
    with (root / "run.toml").open("a", encoding="utf-8") as stream:
        stream.write('\npassword = "must-not-be-accepted"\n')

    with pytest.raises(ValueError, match="keys must match"):
        load_run_spec(root)


def test_smoke_mode_requires_one_unit(tmp_path: Path) -> None:
    """A smoke contract cannot silently select the complete population."""
    root = _run(tmp_path)
    _replace(root / "run.toml", 'mode = "full"', 'mode = "smoke"')

    with pytest.raises(ValueError, match="smoke mode requires limit=1"):
        load_run_spec(root)


def test_provider_storage_must_be_distinct(tmp_path: Path) -> None:
    """Providers cannot reuse annotations, ontologies, or raw collections."""
    root = _run(tmp_path)
    _replace(
        root / "run.toml",
        'target_branch = "template_lmstudio"',
        'target_branch = "template_academiccloud"',
    )

    with pytest.raises(ValueError, match="target_branch"):
        load_run_spec(root)
