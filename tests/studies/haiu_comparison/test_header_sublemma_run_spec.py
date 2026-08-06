"""Tests for non-secret header--sublemma operational run specifications."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
    load_header_sublemma_run_spec,
    validate_isolated_specs,
)
from dmw_experiments.studies.haiu_comparison.validate_header_sublemma_run import (
    EXPERIMENT_ROOT,
    _plan,
)


def _payload() -> dict[str, object]:
    """Return a complete smoke specification fixture.

    :return: JSON-compatible non-secret run specification.
    """
    return {
        "schema_version": 2,
        "study": "haiu_comparison",
        "mode": "smoke",
        "release_stack": "published-dmw-1.1.3",
        "run_id": "header-sublemma-academiccloud-smoke-20260806",
        "provider_profile": "academiccloud-qwen36",
        "source_branch": "publication-academiccloud-177-v158",
        "target_branch": "header_sublemma_academiccloud_smoke_20260806",
        "raw_collection": "RG_raw_header_sublemma_academiccloud_smoke_20260806",
        "ontology_context_version": "1.5.8",
        "input_catalog": "inputs/header_sublemma_input_catalog.json",
        "limit": 1,
        "conditions": [
            "workflow_full_ontology",
            "workflow_rag",
            "haiu_rag_ontologizer",
        ],
        "max_output_tokens": 60000,
        "output_safety_margin_tokens": 4096,
        "ontology_example_limit": 1,
    }


def _write_spec(tmp_path: Path, payload: dict[str, object]) -> Path:
    """Write one test specification.

    :param tmp_path: Pytest-provided temporary directory.
    :param payload: JSON-compatible specification payload.
    :return: Created JSON path.
    """
    path = tmp_path / "run_spec.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_and_renders_isolated_storage_identities(tmp_path: Path) -> None:
    """The validator derives collection names rather than accepting duplicates."""
    spec = load_header_sublemma_run_spec(_write_spec(tmp_path, _payload()))

    spec.validate(EXPERIMENT_ROOT)

    assert _plan(spec)["annotation_collection"] == (
        "annotations__header_sublemma_academiccloud_smoke_20260806"
    )
    assert _plan(spec)["ontology_collection"] == (
        "ontologies__header_sublemma_academiccloud_smoke_20260806"
    )


def test_rejects_credentials_and_unknown_configuration(tmp_path: Path) -> None:
    """Credential material cannot enter the reviewable run specification."""
    payload = _payload()
    payload["password"] = "must-not-be-accepted"

    with pytest.raises(ValueError, match="keys must match"):
        load_header_sublemma_run_spec(_write_spec(tmp_path, payload))


def test_rejects_non_publication_condition_set(tmp_path: Path) -> None:
    """A run cannot silently omit one condition or duplicate another."""
    payload = _payload()
    payload["conditions"] = ["workflow_full_ontology"] * 3
    spec = load_header_sublemma_run_spec(_write_spec(tmp_path, payload))

    with pytest.raises(ValueError, match="conditions"):
        spec.validate(EXPERIMENT_ROOT)


def test_smoke_mode_requires_one_unit(tmp_path: Path) -> None:
    """A smoke contract cannot silently select the complete population."""
    payload = _payload()
    payload["limit"] = 0
    spec = load_header_sublemma_run_spec(_write_spec(tmp_path, payload))

    with pytest.raises(ValueError, match="smoke mode requires limit=1"):
        spec.validate(EXPERIMENT_ROOT)


def test_full_mode_requires_complete_population(tmp_path: Path) -> None:
    """A full contract always uses the catalogue's complete population."""
    payload = _payload()
    payload["mode"] = "full"
    payload["limit"] = 1
    spec = load_header_sublemma_run_spec(_write_spec(tmp_path, payload))

    with pytest.raises(ValueError, match="full mode requires limit=0"):
        spec.validate(EXPERIMENT_ROOT)


def test_smoke_and_full_specs_require_distinct_storage(tmp_path: Path) -> None:
    """A full run cannot reuse smoke annotations or ontologies."""
    smoke_payload = _payload()
    full_payload = _payload()
    full_payload["mode"] = "full"
    full_payload["limit"] = 0
    full_payload["run_id"] = "header-sublemma-academiccloud-full-20260806"
    smoke = load_header_sublemma_run_spec(_write_spec(tmp_path, smoke_payload))
    full_path = tmp_path / "full.json"
    full_path.write_text(json.dumps(full_payload), encoding="utf-8")
    full = load_header_sublemma_run_spec(full_path)

    with pytest.raises(ValueError, match="target_branch"):
        validate_isolated_specs(smoke, full)
