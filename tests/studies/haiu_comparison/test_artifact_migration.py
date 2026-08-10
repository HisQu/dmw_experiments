"""Tests for lossless conversion of the legacy flat artifact layout."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.analysis.workbooks.results import (
    _load_rows,
    _RunLayout,
)
from dmw_experiments.studies.haiu_comparison.operations import (
    artifact_migration,
)
from dmw_experiments.studies.haiu_comparison.operations.artifact_migration import (
    ArtifactLayoutMigrator,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one legacy fixture object.

    :param path: Fixture destination.
    :param payload: JSON-compatible source object.
    :return: ``None``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _legacy_run(run_root: Path) -> dict[str, object]:
    """Create one collision-bearing schema-v2 execution fixture.

    :param run_root: Complete copied-run-shaped destination.
    :return: Exact terminal result payload used by the fixture.
    """
    raw_root = run_root / "raw-academiccloud"
    provenance_root = raw_root / "intermediates-haiu_rag_ontologizer/provenance"
    reference = provenance_root / "reference_ontology.ttl"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "@prefix : <urn:test:> .\n:Known a :Class .\n", encoding="utf-8"
    )
    reference_sha = artifact_migration._sha256_file(reference)

    frozen_regest = provenance_root / "raw_regests/unit-1.json"
    _write_json(
        frozen_regest,
        {
            "schema_version": 1,
            "source": "preflight_frozen_raw_regest_snapshot",
            "regest_id": "unit-1",
            "header": "Header",
            "subentries": ["Sublemma"],
            "content_sha256": "fixture",
        },
    )
    frozen_regest_sha = artifact_migration._sha256_file(frozen_regest)
    snapshot_path = provenance_root / "raw_regests_manifest.json"
    snapshot = {
        "schema_version": 1,
        "source": "preflight_frozen_raw_regest_snapshot",
        "records": {
            "unit-1": {
                "path": frozen_regest.relative_to(run_root).as_posix(),
                "sha256": frozen_regest_sha,
            }
        },
    }
    _write_json(snapshot_path, snapshot)
    snapshot_reference = {
        "path": snapshot_path.relative_to(run_root).as_posix(),
        "sha256": artifact_migration._sha256_file(snapshot_path),
        "count": 1,
    }
    provenance = {
        "schema_version": 1,
        "inputs": {
            "reference_ontology": {
                "path": reference.relative_to(run_root).as_posix(),
                "sha256": reference_sha,
            }
        },
        "raw_regest_snapshot": snapshot_reference,
    }
    _write_json(provenance_root / "provenance_manifest.json", provenance)

    annotation_root = raw_root / "intermediates-workflow_full_ontology"
    annotation_root.mkdir(parents=True, exist_ok=True)
    annotation = {
        "schema_version": 1,
        "regest_id": "unit-1",
        "content_sha256": "annotation-sha",
        "content": {
            "header_entities": [{"type": "Person", "value": "Ada"}],
            "subentry_entities": [],
        },
    }
    # > This is the actual v2 collision: Stage-1 metadata replaced annotation
    # > JSON while the annotation-only YAML mirror remained intact.
    _write_json(
        annotation_root / "unit-1.json",
        {"schema_version": 1, "capture_status": "captured"},
    )
    (annotation_root / "unit-1.yaml").write_text(
        "schema_version: 1\n"
        "regest_id: unit-1\n"
        "content_sha256: annotation-sha\n"
        "content:\n"
        "  header_entities:\n"
        "    - type: Person\n"
        "      value: Ada\n"
        "  subentry_entities: []\n",
        encoding="utf-8",
    )
    _write_json(
        annotation_root / "unit-1.annotation-attempt.json",
        {
            "status": "completed",
            "regest_id": "unit-1",
            "attempt": 1,
            "content_sha256": annotation["content_sha256"],
        },
    )

    debug_path = run_root / "debug_output/debug_unit-1.json"
    _write_json(debug_path, {"exact": "redundant DMW copy"})
    result = {
        "condition": "workflow_full_ontology",
        "regest_id": "unit-1",
        "success": False,
        "attempt": 1,
        "failure_code": "output_length",
        "raw_stage1_output": "Exact Stage 1",
        "raw_ttl_output": "```ttl\n:Incomplete a :Thing .\n```",
        "prompts": {
            "workflow_stage1": {"system": "S1 system", "user": "S1 user"},
            "workflow_stage2": {"system": "S2 system", "user": "S2 user"},
        },
        "raw_response": {
            "debug_output_path": debug_path.relative_to(run_root).as_posix(),
            "debug_output": {"exact": "returned response"},
        },
        "frozen_annotation_artifact_paths": {
            "json": (
                "raw-academiccloud/intermediates-workflow_full_ontology/"
                "unit-1.json"
            )
        },
    }
    result_path = raw_root / "result-workflow_full_ontology/unit-1.json"
    _write_json(result_path, result)
    _write_json(
        annotation_root / "unit-1.attempt.json",
        {
            "condition": "workflow_full_ontology",
            "regest_id": "unit-1",
            "status": "failed",
            "attempt": 1,
        },
    )

    run_manifest = {
        "schema_version": 6,
        "run_id": "fixture-academiccloud",
        "conditions": [
            "workflow_full_ontology",
            "workflow_rag",
            "haiu_rag_ontologizer",
        ],
        "regest_ids": ["unit-1"],
        "provenance": provenance,
        "raw_regest_snapshot": snapshot_reference,
    }
    _write_json(
        run_root / "environment/academiccloud-run-manifest.json",
        run_manifest,
    )
    _write_json(
        run_root / "environment/academiccloud-environment-lock.json",
        {
            "schema_version": 3,
            "experiment_harness": {
                "commit": "a" * 40,
                "branch": "main",
                "worktree_clean": True,
            },
        },
    )
    (run_root / "run.toml").write_text(
        'schema_version = 3\nstudy = "haiu_comparison"\n',
        encoding="utf-8",
    )
    return result


def test_migration_preserves_payload_and_marks_failed_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "run"
    source_result = _legacy_run(run_root)
    monkeypatch.setattr(
        artifact_migration,
        "_clean_harness_identity",
        lambda: {
            "commit": "b" * 40,
            "branch": "main",
            "worktree_clean": True,
        },
    )

    report = ArtifactLayoutMigrator(
        run_root=run_root,
        execution="academiccloud",
    ).migrate()

    assert report.terminal_cells == 1
    assert report.shared_annotations == 1
    assert report.checkpoints == 1
    assert report.failed_attempts == 1
    attempt = (
        run_root / "raw-academiccloud/intermediates-workflow_full_ontology/"
        "unit-1/attempts/001-failed"
    )
    assert (attempt / "metadata.json").is_file()
    assert (attempt / "prompts/stage-1-system.md").is_file()
    assert (attempt / "responses/stage-1.md").read_text(
        encoding="utf-8"
    ) == "Exact Stage 1"
    assert (
        json.loads(
            gzip.decompress((attempt / "upstream-result.json.gz").read_bytes())
        )
        == source_result
    )
    assert json.loads(
        (
            run_root / "raw-academiccloud/intermediates-shared_annotations/"
            "unit-1/annotation.json"
        ).read_text(encoding="utf-8")
    )["content"] == {
        "header_entities": [{"type": "Person", "value": "Ada"}],
        "subentry_entities": [],
    }
    assert not (
        run_root / "raw-academiccloud/result-workflow_full_ontology/unit-1.json"
    ).exists()
    assert not (run_root / "debug_output/debug_unit-1.json").exists()
    assert (
        run_root
        / report.backup
        / "files/raw-academiccloud/result-workflow_full_ontology/unit-1.json"
    ).is_file()

    layout = _RunLayout.from_output(run_root / "raw-academiccloud")
    analysis_rows, _hashes = _load_rows(layout)
    assert len(analysis_rows) == 1
    for key, value in source_result.items():
        assert analysis_rows[0][key] == value


def test_migration_is_idempotent_after_completion(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "run"
    _legacy_run(run_root)
    monkeypatch.setattr(
        artifact_migration,
        "_clean_harness_identity",
        lambda: {
            "commit": "b" * 40,
            "branch": "main",
            "worktree_clean": True,
        },
    )
    migrator = ArtifactLayoutMigrator(
        run_root=run_root,
        execution="academiccloud",
    )

    first = migrator.migrate()
    second = migrator.migrate()

    assert second == first


def test_migration_marks_failed_retry_retained_only_in_history(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep the available schema-v2 retry summary under ``001-failed``."""
    run_root = tmp_path / "run"
    _legacy_run(run_root)
    result_path = (
        run_root / "raw-academiccloud/result-workflow_full_ontology/unit-1.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "success": True,
            "attempt": 2,
            "attempt_history": [
                {
                    "attempt": 1,
                    "success": False,
                    "error_message": "Provider timeout.",
                },
                {"attempt": 2, "success": True},
            ],
        }
    )
    _write_json(result_path, payload)
    monkeypatch.setattr(
        artifact_migration,
        "_clean_harness_identity",
        lambda: {
            "commit": "b" * 40,
            "branch": "main",
            "worktree_clean": True,
        },
    )

    report = ArtifactLayoutMigrator(
        run_root=run_root,
        execution="academiccloud",
    ).migrate()

    failed = (
        run_root / "raw-academiccloud/intermediates-workflow_full_ontology/"
        "unit-1/attempts/001-failed/metadata.json"
    )
    current = failed.parent.parent / "002/metadata.json"
    failed_payload = json.loads(failed.read_text(encoding="utf-8"))
    assert report.failed_attempts == 1
    assert current.is_file()
    assert (
        failed_payload["attempts"]["legacy_attempt_history"]["error_message"]
        == "Provider timeout."
    )


def test_migration_refuses_retry_pending_legacy_result(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not turn schema-v2's provisional retry row into a terminal result."""
    run_root = tmp_path / "run"
    _legacy_run(run_root)
    checkpoint = (
        run_root / "raw-academiccloud/intermediates-workflow_full_ontology/"
        "unit-1.attempt.json"
    )
    _write_json(
        checkpoint,
        {
            "condition": "workflow_full_ontology",
            "regest_id": "unit-1",
            "status": "retry_pending",
            "attempt": 1,
        },
    )
    monkeypatch.setattr(
        artifact_migration,
        "_clean_harness_identity",
        lambda: {
            "commit": "b" * 40,
            "branch": "main",
            "worktree_clean": True,
        },
    )

    with pytest.raises(ValueError, match="still retry-pending"):
        ArtifactLayoutMigrator(
            run_root=run_root,
            execution="academiccloud",
        ).migrate()

    assert not (run_root / "environment/artifact-migration-backups").exists()
