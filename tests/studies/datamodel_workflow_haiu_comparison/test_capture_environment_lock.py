"""Tests for non-secret environment-lock capture helpers."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from dmw_experiments.studies.datamodel_workflow_haiu_comparison import (
    capture_environment_lock,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.input_catalog import (
    canonical_json_sha256,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.prepare_header_sublemma_environment import (
    PairEnvironmentSpec,
    build_import_manifest,
    write_manifest,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.paths import (
    INPUT_ROOT,
)


def test_provider_runtime_hashes_endpoints_and_profile_file(
    tmp_path: Path,
) -> None:
    """AcademicCloud capture must retain hashes rather than endpoint literals."""
    profile_file = tmp_path / "academiccloud.env"
    profile_file.write_text("NON_SECRET_PROFILE=true\n", encoding="utf-8")
    runtime = capture_environment_lock._provider_runtime(
        Namespace(
            provider_profile="academiccloud-qwen36",
            chat_endpoint="https://chat.example/v1",
            embedding_endpoint="https://embedding.example/v1",
            provider_environment_file=profile_file,
            lmstudio_model_file=None,
            lmstudio_model_file_sha256="",
            lmstudio_runtime_version="",
            lmstudio_context_window_tokens=None,
        )
    )

    assert runtime["profile"]["quantization"] == "FP8"
    assert runtime[
        "chat_endpoint_sha256"
    ] == capture_environment_lock._sha256_bytes(b"https://chat.example/v1")
    assert "https://chat.example/v1" not in str(runtime)
    assert runtime["provider_environment_file_sha256"] == (
        capture_environment_lock._sha256_file(profile_file)
    )


def test_lmstudio_runtime_requires_file_version_and_context(
    tmp_path: Path,
) -> None:
    """Q6 provenance cannot be captured without all capacity evidence."""
    profile_file = tmp_path / "lmstudio.env"
    profile_file.write_text("NON_SECRET_PROFILE=true\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="LM Studio Q6 requires"):
        capture_environment_lock._provider_runtime(
            Namespace(
                provider_profile="lmstudio-qwen36-q6",
                chat_endpoint="http://127.0.0.1:1234/v1",
                embedding_endpoint="https://embedding.example/v1",
                provider_environment_file=profile_file,
                lmstudio_model_file=None,
                lmstudio_model_file_sha256="",
                lmstudio_runtime_version="",
                lmstudio_context_window_tokens=None,
            )
        )


def test_lmstudio_runtime_records_model_file_hash(tmp_path: Path) -> None:
    """Q6 evidence includes model-file identity and loaded context capacity."""
    profile_file = tmp_path / "lmstudio.env"
    profile_file.write_text("NON_SECRET_PROFILE=true\n", encoding="utf-8")
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"q6-weights")
    runtime = capture_environment_lock._provider_runtime(
        Namespace(
            provider_profile="lmstudio-qwen36-q6",
            chat_endpoint="http://127.0.0.1:1234/v1",
            embedding_endpoint="https://embedding.example/v1",
            provider_environment_file=profile_file,
            lmstudio_model_file=model_file,
            lmstudio_model_file_sha256="",
            lmstudio_runtime_version="0.4.1",
            lmstudio_context_window_tokens=262_144,
        )
    )

    assert runtime["profile"]["quantization"] == "Q6"
    assert runtime["lmstudio"] == {
        "model_file_sha256": capture_environment_lock._sha256_file(model_file),
        "runtime_version": "0.4.1",
        "context_window_tokens": 262_144,
    }


def test_lmstudio_runtime_accepts_verified_remote_model_hash(
    tmp_path: Path,
) -> None:
    """Linked-device evidence can use a previously verified artifact digest."""
    profile_file = tmp_path / "lmstudio.env"
    profile_file.write_text("NON_SECRET_PROFILE=true\n", encoding="utf-8")
    model_file_sha256 = "a" * 64

    runtime = capture_environment_lock._provider_runtime(
        Namespace(
            provider_profile="lmstudio-qwen36-q6",
            chat_endpoint="http://127.0.0.1:1234/v1",
            embedding_endpoint="https://embedding.example/v1",
            provider_environment_file=profile_file,
            lmstudio_model_file=None,
            lmstudio_model_file_sha256=model_file_sha256,
            lmstudio_runtime_version="0.4.1",
            lmstudio_context_window_tokens=262_144,
        )
    )

    assert runtime["lmstudio"] == {
        "model_file_sha256": model_file_sha256,
        "runtime_version": "0.4.1",
        "context_window_tokens": 262_144,
    }


def test_pair_capture_records_catalogue_and_isolated_dmw_identity(
    tmp_path: Path,
) -> None:
    catalogue_path = INPUT_ROOT / "header_sublemma_input_catalog.json"
    catalog = load_header_sublemma_catalog(catalogue_path)
    spec = PairEnvironmentSpec(
        database_name="UserData",
        raw_collection="RG_raw_pair_academiccloud",
        branch_registry_collection="ontology_branches",
        annotation_base_collection="annotations",
        ontology_base_collection="ontologies",
        source_branch="publication-academiccloud",
        target_branch="pair_academiccloud",
        ontology_context_version="1.15.0",
    )
    manifest_path = tmp_path / "import.json"
    write_manifest(
        manifest_path,
        build_import_manifest(
            catalog=catalog,
            spec=spec,
            storage_evidence={
                "source_branch": {
                    "branch_slug": spec.source_branch,
                    "github_branch": spec.source_branch,
                    "github_tag_scope": spec.source_branch,
                    "latest_version": "1.15.0",
                },
                "target_branch": {
                    "branch_slug": spec.target_branch,
                    "branch_name": "Pair run",
                    "github_branch": spec.source_branch,
                    "github_tag_scope": spec.source_branch,
                    "annotation_collection": "annotations__pair_academiccloud",
                    "ontology_collection": "ontologies__pair_academiccloud",
                    "latest_version": "1.15.0",
                    "status": "active",
                    "creator_id": "haiu_header_sublemma_experiment",
                },
                "collections": {
                    "raw": spec.raw_collection,
                    "annotation": "annotations__pair_academiccloud",
                    "ontology": "ontologies__pair_academiccloud",
                    "branch_registry": spec.branch_registry_collection,
                },
                "raw_population": {
                    "document_count": len(catalog.records),
                    "canonical_sha256": canonical_json_sha256(
                        catalog.dmw_raw_documents()
                    ),
                },
            },
        ),
    )
    args = Namespace(
        input_catalog=catalogue_path,
        dmw_input_manifest=manifest_path,
        provider_profile="academiccloud-qwen36",
        dmw_raw_collection=spec.raw_collection,
        dmw_annotation_collection="annotations__pair_academiccloud",
        dmw_ontology_collection="ontologies__pair_academiccloud",
        dmw_ontology_branch=spec.target_branch,
        ontology_context_version=spec.ontology_context_version,
    )

    evidence = capture_environment_lock._pair_input_evidence(args)

    assert evidence is not None
    assert evidence["input_population"]["input_unit_count"] == 480
    assert evidence["dmw_data_identity"] == {
        "branch": "pair_academiccloud",
        "raw": "RG_raw_pair_academiccloud",
        "annotation": "annotations__pair_academiccloud",
        "ontology": "ontologies__pair_academiccloud",
        "ontology_context_version": "1.15.0",
    }


def test_approved_haiu_report_rejects_editable_installation() -> None:
    """The snapshot command must enforce the same Haiu release gate as runs."""
    repositories = {
        str(expected["repository"]): {"commit": "a" * 40}
        for expected in capture_environment_lock.APPROVED_DISTRIBUTIONS.values()
    }
    packages = {
        distribution_name: {
            "version": expected["version"],
            "source": {
                "editable": False,
                "vcs": "git",
                "url": expected["url"],
                "requested_revision": expected["revision"],
                "commit_id": "a" * 40,
            },
        }
        for distribution_name, expected in (
            capture_environment_lock.APPROVED_DISTRIBUTIONS.items()
        )
    }
    packages["haiu"] = {
        **packages["haiu"],
        "source": {
            **packages["haiu"]["source"],
            "editable": True,
        },
    }
    report = {"packages": packages}

    with pytest.raises(SystemExit, match="non-editable haiu==1.8.0"):
        capture_environment_lock._require_approved_distributions(
            report,
            repositories,
        )
