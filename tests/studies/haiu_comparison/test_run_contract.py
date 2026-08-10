"""Tests for the copied-run TOML contract."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)
from dmw_experiments.studies.haiu_comparison.model.run_directory import (
    HaiuComparisonRun,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    RUN_TEMPLATE_ROOT,
)


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
    spec = load_run_contract(_run(tmp_path))

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
    assert spec.ontology_example_limit == 0


def test_existing_run_keeps_its_frozen_release_stack(tmp_path: Path) -> None:
    """A runtime patch must not require rewriting an existing run contract."""
    root = _run(tmp_path)
    _replace(
        root / "run.toml",
        'release_stack = "published-dmw-1.1.4"',
        'release_stack = "published-dmw-1.1.3"',
    )

    assert load_run_contract(root).release_stack == "published-dmw-1.1.3"


def test_rejects_unrecognized_release_stack(tmp_path: Path) -> None:
    """Only stack identities with an explicit transition path are readable."""
    root = _run(tmp_path)
    _replace(
        root / "run.toml",
        'release_stack = "published-dmw-1.1.4"',
        'release_stack = "published-dmw-9.9.9"',
    )

    with pytest.raises(ValueError, match="release_stack must be one of"):
        load_run_contract(root)


def test_run_directory_owns_cell_paths(tmp_path: Path) -> None:
    """Every lifecycle phase resolves artifacts through one run boundary."""
    root = _run(tmp_path)

    run = HaiuComparisonRun.open(root)

    assert run.input_catalog_path == (
        root / "INPUTS/header_sublemma_input_catalog.json"
    )
    assert (
        run.intermediate_directory("academiccloud", "workflow_rag")
        == root / "raw-academiccloud/intermediates-workflow_rag"
    )
    assert (
        run.result_directory("lmstudio", "haiu_rag_ontologizer")
        == root / "raw-lmstudio/result-haiu_rag_ontologizer"
    )


def test_rejects_unknown_toml_configuration(tmp_path: Path) -> None:
    """Credentials and ad-hoc fields cannot enter the scientific contract."""
    root = _run(tmp_path)
    with (root / "run.toml").open("a", encoding="utf-8") as stream:
        stream.write('\npassword = "must-not-be-accepted"\n')

    with pytest.raises(ValueError, match="keys must match"):
        load_run_contract(root)


def test_smoke_mode_requires_one_unit(tmp_path: Path) -> None:
    """A smoke contract cannot silently select the complete population."""
    root = _run(tmp_path)
    _replace(root / "run.toml", 'mode = "full"', 'mode = "smoke"')

    with pytest.raises(ValueError, match="smoke mode requires limit=1"):
        load_run_contract(root)


def test_provider_storage_must_be_distinct(tmp_path: Path) -> None:
    """Providers cannot reuse annotations, ontologies, or raw collections."""
    root = _run(tmp_path)
    _replace(
        root / "run.toml",
        'target_branch = "template_lmstudio"',
        'target_branch = "template_academiccloud"',
    )

    with pytest.raises(ValueError, match="target_branch"):
        load_run_contract(root)
