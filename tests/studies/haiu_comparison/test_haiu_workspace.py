"""Tests for the reference workspace shared by both RAG conditions."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from haiu import HaiuRC

from dmw_experiments.studies.haiu_comparison.data_collection.haiu import (
    workspace as workspace_module,
)
from dmw_experiments.studies.haiu_comparison.data_collection.haiu.workspace import (
    prepare_reference_workspace,
)
from dmw_experiments.studies.haiu_comparison.model.inputs import (
    DmwPairImportManifest,
)


def test_preparation_uses_frozen_branch_aware_reference_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turtle = "@prefix : <https://example.org/> .\n:Known a :Class .\n"
    reference_path = tmp_path / "reference.ttl"
    reference_path.write_text(turtle, encoding="utf-8")
    contract_path = tmp_path / "retrieval_workspace.json"
    contract_path.write_text(
        json.dumps(_contract(workspace_module.ttl_sha256(turtle))),
        encoding="utf-8",
    )
    base_rc = _base_rc()
    derived_rc = cast(HaiuRC, SimpleNamespace(name="derived"))
    captured: dict[str, Any] = {}

    def make_rc(ontology_ref, *, base_rc):
        captured["derived_ref"] = ontology_ref
        captured["base_rc"] = base_rc
        return derived_rc

    async def prepare(**kwargs):
        captured.update(kwargs)
        return True, {"entities": 12}

    monkeypatch.setenv("GITHUB_ONTOLOGY_REPO_NAME", "Ontology-Development")
    monkeypatch.setattr(workspace_module, "make_rc_for_ref", make_rc)
    monkeypatch.setattr(workspace_module, "_prepare_workspace", prepare)

    prepared = prepare_reference_workspace(
        base_rc=base_rc,
        contract_path=contract_path,
        reference_ontology_path=reference_path,
        dmw_input_manifest=_dmw_manifest(),
    )

    assert prepared.rc is derived_rc
    assert prepared.synchronized is True
    assert prepared.sync_result == {"entities": 12}
    assert prepared.ontology_ref.ref_name == "publication-test_v1.5.8"
    assert captured["base_rc"] is base_rc
    assert captured["ontology_turtle"] == turtle
    assert prepared.manifest_entry() == {
        "preparation": "verified_before_condition_timing",
        "ontology_ref": _contract(workspace_module.ttl_sha256(turtle))[
            "ontology_ref"
        ],
        "embedding_model": "qwen3-embedding-4b",
        "workdir_base": (
            "DMW/ontologies/HisQu__Ontology-Development/"
            "tag__publication-test_v1.5.8"
        ),
        "workspace": "canonical",
    }


def test_preparation_rejects_contract_for_another_reference_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.ttl"
    reference_path.write_text(":Current a :Class .\n", encoding="utf-8")
    contract_path = tmp_path / "retrieval_workspace.json"
    contract_path.write_text(
        json.dumps(_contract("0" * 64)),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_ONTOLOGY_REPO_NAME", "Ontology-Development")

    with pytest.raises(ValueError, match="frozen DMW reference identity"):
        prepare_reference_workspace(
            base_rc=_base_rc(),
            contract_path=contract_path,
            reference_ontology_path=reference_path,
            dmw_input_manifest=_dmw_manifest(),
        )


def test_workspace_preparation_initializes_fresh_corpus_root(
    tmp_path: Path,
) -> None:
    rc = cast(
        HaiuRC,
        SimpleNamespace(
            rag=SimpleNamespace(
                storage=SimpleNamespace(
                    fpb_customkg_yaml=(
                        tmp_path / "Corpus" / "CustomKG" / "custom_kg"
                    )
                )
            )
        ),
    )

    workspace_module._ensure_workspace_storage(rc)

    assert (tmp_path / "Corpus").is_dir()


def _base_rc() -> HaiuRC:
    return cast(
        HaiuRC,
        SimpleNamespace(
            rag=SimpleNamespace(
                haiu_settings=SimpleNamespace(model_embed="qwen3-embedding-4b")
            )
        ),
    )


def _dmw_manifest() -> DmwPairImportManifest:
    return DmwPairImportManifest(
        path=Path("dmw-input-manifest.json"),
        file_sha256="1" * 64,
        content_sha256="2" * 64,
        payload={
            "ontology_context_version": "1.5.8",
            "target_branch": {
                "github_branch": "publication-test",
                "github_tag_scope": "publication-test",
            },
        },
    )


def _contract(turtle_sha256: str) -> dict[str, Any]:
    return {
        "snapshot_schema": 2,
        "ontology_ref": {
            "repo": "HisQu/Ontology-Development",
            "ref_type": "tag",
            "ref_name": "publication-test_v1.5.8",
            "base_ref_name": "publication-test",
            "commit_sha": None,
            "file_path": "files/processed/rg_ontology.ttl",
            "ttl_sha256": turtle_sha256,
            "ontology_family_id": "HisQu/Ontology-Development",
        },
        "embedding_model": "qwen3-embedding-4b",
        "retrieval_mode": "hybrid",
        "workspace": "canonical",
    }
