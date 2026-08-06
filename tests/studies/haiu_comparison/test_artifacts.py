import json
from pathlib import Path

import pytest

import haiu.utils as ut

from dmw_experiments.studies.haiu_comparison.comparison_experiment.artifacts import (
    ArtifactWriter,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    ExperimentResult,
)
from dmw_experiments.studies.haiu_comparison.model.traces import (
    RegestText,
)


def _writer(run_root: Path) -> ArtifactWriter:
    """Create an AcademicCloud writer inside a copied-run-shaped root."""
    return ArtifactWriter(run_root / "raw-academiccloud")


def test_artifact_paths_are_relative_to_run_directory(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_full_ontology",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_full_ontology",
            "regest_id": "11000127",
            "raw_ttl_output": "@prefix : <x:> .\n:i a :Thing .",
            "prompts": {
                "stage1": {
                    "system": "System prompt",
                    "user": "User prompt",
                }
            },
        },
    )

    row = writer.write_result(result)

    assert (
        row["raw_artifact_path"]
        == "raw-academiccloud/result-workflow_full_ontology/11000127.json"
    )
    assert (
        row["raw_ttl_artifact_path"]
        == "raw-academiccloud/result-workflow_full_ontology/11000127.ttl"
    )
    assert (
        row["raw_yaml_artifact_path"]
        == "raw-academiccloud/result-workflow_full_ontology/11000127.yaml"
    )
    assert row["retrieved_ttl_artifact_path"] is None
    assert row["retrieved_yaml_artifact_path"] is None
    assert row["retrieval_snapshot_fidelity"] is None
    assert row["retrieval_sidecars_complete"] is None
    assert row["prompt_artifact_paths"] == {
        "stage1_system": (
            "raw-academiccloud/intermediates-workflow_full_ontology/"
            "11000127_stage1_system.md"
        ),
        "stage1_user": (
            "raw-academiccloud/intermediates-workflow_full_ontology/"
            "11000127_stage1_user.md"
        ),
    }
    assert (tmp_path / "run" / str(row["raw_ttl_artifact_path"])).read_text(
        encoding="utf-8"
    ) == "@prefix : <x:> .\n:i a :Thing ."
    assert (
        ut.load_yaml(tmp_path / "run" / str(row["raw_yaml_artifact_path"]))
        == result.payload
    )


def test_existing_rows_are_recovered_from_raw_artifacts(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_full_ontology",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_full_ontology",
            "regest_id": "11000127",
            "success": True,
            "prompts": {
                "stage1": {
                    "system": "System prompt",
                    "user": "User prompt",
                }
            },
        },
    )
    expected = writer.write_result(result)

    assert writer.load_existing_rows() == [expected]


def test_normalized_rows_do_not_duplicate_large_raw_payloads(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    payload = {
        "condition": "workflow_rag",
        "regest_id": "11000127",
        "success": True,
        "prompt_tokens": 123,
        "raw_response": {"provider_payload": "raw response"},
        "generation_attempts": [{"diagnostics": {"rawTtlOutput": "ttl"}}],
        "ontology_context": {"retrieved_turtle": "context"},
        "prompts": {"stage1": {"user": "prompt"}},
        "raw_stage1_output": "plan",
        "raw_ttl_output": "ttl",
        "explanation": "plan",
        "tbox": "schema",
        "abox": "data",
    }

    row = writer.write_result(
        ExperimentResult(
            condition="workflow_rag",
            regest_id="11000127",
            success=True,
            payload=payload,
        )
    )

    assert row["prompt_tokens"] == 123
    assert (
        row["raw_artifact_path"]
        == "raw-academiccloud/result-workflow_rag/11000127.json"
    )
    for field in (
        "raw_response",
        "generation_attempts",
        "ontology_context",
        "prompts",
        "raw_stage1_output",
        "raw_ttl_output",
        "explanation",
        "tbox",
        "abox",
    ):
        assert field not in row
    raw_payload = json.loads(
        (tmp_path / "run" / str(row["raw_artifact_path"])).read_text(
            encoding="utf-8"
        )
    )
    assert raw_payload == payload
    assert writer.load_existing_rows() == [row]


def test_annotation_attempt_state_is_recovered_separately(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    payload = {
        "status": "failed",
        "regest_id": "11000127",
        "attempt": 3,
        "attempt_history": [{"attempt": 3, "success": False}],
    }

    writer.write_annotation_attempt_state(regest_id="11000127", payload=payload)

    assert writer.load_annotation_attempt_state(regest_id="11000127") == payload
    assert writer.load_annotation_attempt_state(regest_id="missing") is None


def test_annotation_attempt_state_amendment_archives_then_resets(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    payload = {
        "status": "failed",
        "regest_id": "11000127",
        "attempt": 3,
    }
    writer.write_annotation_attempt_state(regest_id="11000127", payload=payload)

    archive = writer.archive_annotation_attempt_state_for_amendment(
        amendment_id="lmstudio-runtime-20260803",
        regest_id="11000127",
    )

    assert archive is not None
    assert writer.load_annotation_attempt_state(regest_id="11000127") is None
    archived_state = (
        tmp_path
        / "run"
        / str(archive["superseded_annotation_attempt_state_path"])
    )
    assert json.loads(archived_state.read_text(encoding="utf-8")) == payload
    assert (
        writer.archive_annotation_attempt_state_for_amendment(
            amendment_id="lmstudio-runtime-20260803",
            regest_id="11000127",
        )
        == archive
    )


def test_workflow_turtle_is_not_reconstructed_from_tbox_and_abox(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "tbox": ":A a owl:Class .",
            "abox": ":i a :A .\n```",
            "ontology_context": {
                "retrieved_turtle": ":Existing a owl:Class .",
                "retrieval_snapshot": {
                    "snapshot_fidelity": "native_full_graph",
                },
            },
        },
    )

    row = writer.write_result(result)

    assert row["raw_ttl_artifact_path"] is None
    assert not (
        tmp_path / "run" / "raw-academiccloud/result-workflow_rag/11000127.ttl"
    ).exists()


def test_result_without_turtle_still_writes_raw_yaml(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=False,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "success": False,
        },
    )

    row = writer.write_result(result)

    assert row["raw_ttl_artifact_path"] is None
    assert row["raw_yaml_artifact_path"] == (
        "raw-academiccloud/result-workflow_rag/11000127.yaml"
    )
    assert row["retrieval_sidecars_complete"] is False
    assert not list((tmp_path / "run" / "raw_ttl").glob("**/*.ttl"))


def test_stage1_sidecar_reconstructs_legacy_explanation_without_mutating_raw(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "explanation": "Exact Designer reply",
        },
    )

    row = writer.write_result(result)

    assert row["raw_stage1_artifact_path"] is not None
    assert row["raw_stage1_metadata_artifact_path"] == (
        "raw-academiccloud/intermediates-workflow_rag/11000127.json"
    )
    assert (tmp_path / "run" / str(row["raw_stage1_artifact_path"])).read_text(
        encoding="utf-8"
    ) == "Exact Designer reply"
    metadata = json.loads(
        (
            tmp_path / "run" / str(row["raw_stage1_metadata_artifact_path"])
        ).read_text(encoding="utf-8")
    )
    assert metadata["capture_status"] == "captured"
    assert metadata["source"] == "reconstructed_from_explanation"


def test_stage1_sidecar_records_unavailable_response_without_fabrication(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_full_ontology",
        regest_id="11000127",
        success=False,
        payload={
            "condition": "workflow_full_ontology",
            "regest_id": "11000127",
            "output_truncated": True,
        },
    )

    row = writer.write_result(result)

    assert row["raw_stage1_artifact_path"] is None
    metadata = json.loads(
        (
            tmp_path / "run" / str(row["raw_stage1_metadata_artifact_path"])
        ).read_text(encoding="utf-8")
    )
    assert metadata["capture_status"] == "unavailable"
    assert "insufficient" in metadata["unavailable_reason"]


def test_failed_upstream_attempt_turtle_is_preserved_separately(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_full_ontology",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_full_ontology",
            "regest_id": "11000127",
            "raw_ttl_output": "# --- TBOX ---\n:Current a owl:Class .",
            "generation_attempts": [
                {
                    "attempt": 1,
                    "success": False,
                    "diagnostics": {"rawTtlOutput": "```ttl\ninvalid\n```"},
                },
                {"attempt": 2, "success": True, "diagnostics": {}},
            ],
        },
    )

    row = writer.write_result(result)

    assert row["attempt_ttl_artifact_paths"] == {
        "attempt_1": "raw-academiccloud/result-workflow_full_ontology/11000127.attempt-1.ttl"
    }
    assert (
        tmp_path
        / "run"
        / "raw-academiccloud/result-workflow_full_ontology/11000127.attempt-1.ttl"
    ).read_text(encoding="utf-8") == "```ttl\ninvalid\n```"


def test_native_haiu_retrieval_snapshot_is_written_with_portable_paths(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "ontology_context": {
                "retrieved_turtle": ":i a :Thing .",
                "retrieval_snapshot": {
                    "snapshot_fidelity": "native_full_graph",
                    "workdir": "/private/workdir",
                    "chunks": [{"content": "source"}],
                    "entities": [{"entity_name": "Thing"}],
                    "relationships": [],
                },
            },
        },
    )

    row = writer.write_result(result)

    assert row["retrieved_ttl_artifact_path"] == (
        "raw-academiccloud/intermediates-workflow_rag/11000127.retrieved.ttl"
    )
    assert row["retrieved_yaml_artifact_path"] == (
        "raw-academiccloud/intermediates-workflow_rag/11000127.retrieved.yaml"
    )
    assert row["retrieval_snapshot_fidelity"] == "native_full_graph"
    assert row["retrieval_sidecars_complete"] is True
    assert (
        tmp_path / "run" / str(row["retrieved_ttl_artifact_path"])
    ).read_text(encoding="utf-8") == ":i a :Thing ."
    snapshot = ut.load_yaml(
        tmp_path / "run" / str(row["retrieved_yaml_artifact_path"])
    )
    assert snapshot["chunks"] == [{"content": "source"}]
    assert snapshot["snapshot_fidelity"] == "native_full_graph"
    assert snapshot["export_yaml_path"] == (
        "raw-academiccloud/intermediates-workflow_rag/11000127.retrieved.yaml"
    )
    assert "workdir" not in snapshot
    assert "/private" not in json.dumps(snapshot)


def test_legacy_rag_retrieval_is_not_reconstructed_from_stage1_prompt(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    marker = (
        "## Referenzontologie (Ausschnitt, Turtle)\n"
        "Dies ist ein relevanter Ausschnitt der bestehenden Gesamtontologie. "
        "Er ist in Turtle notiert.\n"
        "```ttl\n"
    )
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=True,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "ontology_context": {
                "retrieval_metadata": {
                    "retrieval_status": {"status": "ok"},
                }
            },
            "prompts": {
                "workflow": {
                    "user": (f"Before\n{marker}:i a :Thing .\n```\nAfter"),
                }
            },
        },
    )

    row = writer.write_result(result)

    assert row["retrieved_ttl_artifact_path"] is None
    assert row["retrieved_yaml_artifact_path"] is None
    assert row["retrieval_sidecars_complete"] is False


def test_rematerializing_result_without_turtle_removes_stale_ttl(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    writer = _writer(run_dir)
    ttl_path = run_dir / "raw-academiccloud/result-workflow_rag/11000127.ttl"
    ttl_path.parent.mkdir(parents=True, exist_ok=True)
    ttl_path.write_text("stale output", encoding="utf-8")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=False,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "success": False,
        },
    )

    writer.write_result(result)

    assert not ttl_path.exists()


def test_existing_raw_documents_without_raw_turtle_keep_yaml_only(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw-academiccloud" / "result-workflow_full_ontology"
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "condition": "workflow_full_ontology",
        "regest_id": "11000127",
        "tbox": ":A a owl:Class .",
        "abox": ":i a :A .",
    }
    (raw_dir / "11000127.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    writer = _writer(run_dir)

    counts = writer.materialize_existing_raw_documents()

    assert counts == {
        "yaml": 1,
        "ttl": 0,
        "stage1": 0,
        "stage1_unavailable": 1,
        "retrieved_yaml": 0,
        "retrieved_ttl": 0,
    }
    assert not (
        run_dir / "raw-academiccloud/result-workflow_full_ontology/11000127.ttl"
    ).exists()
    assert (
        ut.load_yaml(
            run_dir
            / "raw-academiccloud/result-workflow_full_ontology/11000127.yaml"
        )
        == payload
    )
    assert not (
        run_dir / "analysis/intermediate/academiccloud-results.jsonl"
    ).exists()


def test_run_manifest_is_immutable(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    manifest = {"run_id": "fixed", "model": "model-a"}

    path = writer.ensure_run_manifest(
        manifest,
        has_existing_results=False,
    )
    resumed_path = writer.ensure_run_manifest(
        manifest,
        has_existing_results=True,
    )

    assert resumed_path == path
    assert json.loads(path.read_text(encoding="utf-8")) == manifest
    with pytest.raises(ValueError, match="differs"):
        writer.ensure_run_manifest(
            {"run_id": "fixed", "model": "model-b"},
            has_existing_results=True,
        )


def test_run_manifest_rejects_legacy_results(tmp_path: Path) -> None:
    writer = _writer(tmp_path)

    with pytest.raises(ValueError, match="without a run manifest"):
        writer.ensure_run_manifest(
            {"run_id": "fixed"},
            has_existing_results=True,
        )


def test_run_amendment_is_immutable(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    payload = {"kind": "output_cap_recovery", "replacement_cap": 60_000}

    path = writer.ensure_run_amendment(
        amendment_id="output-cap-60000",
        payload=payload,
    )

    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert (
        writer.ensure_run_amendment(
            amendment_id="output-cap-60000",
            payload=payload,
        )
        == path
    )
    with pytest.raises(ValueError, match="differs"):
        writer.ensure_run_amendment(
            amendment_id="output-cap-60000",
            payload={"replacement_cap": 80_000},
        )


def test_output_cap_amendment_archives_all_result_evidence(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path / "run")
    result = ExperimentResult(
        condition="workflow_rag",
        regest_id="11000127",
        success=False,
        payload={
            "condition": "workflow_rag",
            "regest_id": "11000127",
            "prompts": {"stage2": {"user": "Exact prompt"}},
            "raw_ttl_output": ":Incomplete a :Ontology .",
            "ontology_context": {
                "retrieved_turtle": ":Existing a owl:Class .",
                "retrieval_snapshot": {
                    "snapshot_fidelity": "native_full_graph",
                },
            },
        },
    )
    writer.write_result(result)
    writer.write_attempt_state(
        condition="workflow_rag",
        regest_id="11000127",
        payload={"status": "failed"},
    )

    archive = writer.archive_result_for_amendment(
        amendment_id="output-cap-60000",
        condition="workflow_rag",
        regest_id="11000127",
    )

    archive_root = (
        tmp_path
        / "run"
        / "environment"
        / "academiccloud-superseded"
        / "output-cap-60000"
    )
    assert archive["canonical_raw_artifact_path"] == (
        "environment/academiccloud-superseded/output-cap-60000/"
        "raw-academiccloud/result-workflow_rag/11000127.json"
    )
    assert (
        archive_root / "raw-academiccloud/result-workflow_rag/11000127.json"
    ).is_file()
    assert (
        archive_root / "raw-academiccloud/result-workflow_rag/11000127.yaml"
    ).is_file()
    assert (
        archive_root / "raw-academiccloud/result-workflow_rag/11000127.ttl"
    ).read_text(encoding="utf-8") == ":Incomplete a :Ontology ."
    assert (
        archive_root
        / "raw-academiccloud/intermediates-workflow_rag/11000127.retrieved.ttl"
    ).is_file()
    assert (
        archive_root / "raw-academiccloud/intermediates-workflow_rag/"
        "11000127_stage2_user.md"
    ).is_file()
    assert (
        archive_root
        / "raw-academiccloud/intermediates-workflow_rag/11000127.attempt.json"
    ).is_file()
    assert (
        writer.archive_result_for_amendment(
            amendment_id="output-cap-60000",
            condition="workflow_rag",
            regest_id="11000127",
        )
        == archive
    )


def test_attempt_state_marks_started_condition_pair(tmp_path: Path) -> None:
    writer = _writer(tmp_path)

    assert (
        writer.has_attempt_state(condition="workflow_rag", regest_id="1")
        is False
    )
    path = writer.write_attempt_state(
        condition="workflow_rag",
        regest_id="1",
        payload={"status": "running"},
    )

    assert writer.has_attempt_state(
        condition="workflow_rag",
        regest_id="1",
    )
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "running"}


def test_attempt_state_can_be_loaded_for_resume(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    payload = {"status": "failed", "attempt": 3}

    assert (
        writer.load_attempt_state(
            condition="workflow_rag",
            regest_id="missing",
        )
        is None
    )

    writer.write_attempt_state(
        condition="workflow_rag",
        regest_id="1",
        payload=payload,
    )

    assert (
        writer.load_attempt_state(
            condition="workflow_rag",
            regest_id="1",
        )
        == payload
    )


def test_frozen_annotation_is_written_as_raw_json_and_yaml(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    payload = {
        "schema_version": 1,
        "regest_id": "1",
        "content_sha256": "abc",
        "content": {
            "header_entities": [{"type": "Person", "value": "Ada"}],
            "subentry_entities": [],
        },
    }

    paths = writer.write_frozen_annotation(
        regest_id="1",
        payload=payload,
    )

    assert paths == {
        "json": (
            "raw-academiccloud/intermediates-workflow_full_ontology/1.json"
        ),
        "yaml": (
            "raw-academiccloud/intermediates-workflow_full_ontology/1.yaml"
        ),
        "workflow_rag_json": (
            "raw-academiccloud/intermediates-workflow_rag/1.json"
        ),
        "workflow_rag_yaml": (
            "raw-academiccloud/intermediates-workflow_rag/1.yaml"
        ),
    }
    assert writer.load_frozen_annotation(regest_id="1") == payload
    assert ut.load_yaml(tmp_path / paths["yaml"]) == payload


def test_frozen_regests_are_reused_without_refetching(tmp_path: Path) -> None:
    writer = _writer(tmp_path / "run")
    requested: list[str] = []

    def fetch(regest_id: str) -> RegestText:
        requested.append(regest_id)
        return RegestText(regest_id=regest_id, header="Header")

    first, first_snapshot = writer.ensure_frozen_regests(
        regest_ids=["1", "2"],
        fetcher=fetch,
    )
    second, second_snapshot = writer.ensure_frozen_regests(
        regest_ids=["1", "2"],
        fetcher=lambda _regest_id: (_ for _ in ()).throw(AssertionError()),
    )

    assert requested == ["1", "2"]
    assert first == second
    assert first_snapshot == second_snapshot
    assert first_snapshot["count"] == 2
