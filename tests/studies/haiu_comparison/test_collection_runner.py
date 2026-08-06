import argparse
import hashlib
import json
import time
from types import SimpleNamespace
from pathlib import Path
from typing import Any, cast

import pytest

from dmw_experiments.studies.haiu_comparison.data_collection import (
    runner as run_experiment,
)
from dmw_experiments.studies.haiu_comparison.data_collection import retry_policy
from dmw_experiments.studies.haiu_comparison.data_collection.arguments import (
    build_parser as _build_parser,
)
from haiu import HaiuRC

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.annotations import (
    FrozenAnnotationError,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    ExperimentResult,
)
from dmw_experiments.studies.haiu_comparison.model.providers import (
    provider_profile,
)
from dmw_experiments.studies.haiu_comparison.model.inputs import (
    canonical_json_sha256,
    load_dmw_pair_import_manifest,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.model.traces import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    TEMPLATE_INPUT_ROOT,
)
from dmw_experiments.studies.haiu_comparison.preparation.dmw_storage import (
    PairEnvironmentSpec,
    build_import_manifest,
    write_manifest,
)
from dmw_experiments.studies.haiu_comparison.data_collection.runner import (
    _annotation_preparation_failure_result,
    _condition_order_for_index,
    _experiment_result_from_row,
    _ordered_rows,
    _run_condition_once,
    _run_condition_with_retries,
    _run_manifest,
    _selected_model_entry,
    _workflow_config,
)
from dmw_experiments.studies.haiu_comparison.data_collection.retry_policy import (
    _annotation_preparation_exhaustion_error,
    _is_annotation_preparation_retry_exhausted,
    _is_terminal_result_payload,
    _workflow_conditions_require_annotation,
)


def _manifest_rc() -> HaiuRC:
    return cast(
        HaiuRC,
        SimpleNamespace(
            client=SimpleNamespace(
                base_url="https://provider.example/v1",
                embedding_base_url="https://embeddings.example/v1",
                api_key="configured",
                timeout_llm=30.0,
                max_retries=2,
                max_retries_openai=0,
            ),
            rag=SimpleNamespace(
                haiu_settings=SimpleNamespace(model_embed="qwen3-embedding-4b")
            ),
        ),
    )


def _environment_lock_payload(
    *, profile_name: str, rc: HaiuRC, branch: str
) -> dict[str, Any]:
    """Build a valid minimal publication environment lock for runner tests."""
    profile = provider_profile(profile_name)

    def endpoint_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    repository_record = {
        "commit": "a" * 40,
        "dependency_file_sha256": {"uv.lock": "b" * 64},
    }
    return {
        "schema_version": 1,
        "provider": {
            "profile": profile.manifest_entry(),
            "chat_endpoint_sha256": endpoint_hash(rc.client.base_url),
            "embedding_endpoint_sha256": endpoint_hash(
                str(rc.client.embedding_base_url or rc.client.base_url)
            ),
        },
        "dmw_ontology_identity": {"branch": branch, "collection": "ontologies"},
        "repositories": {
            "datamodel_workflow": repository_record,
            "opa": repository_record,
            "gta": repository_record,
            "haiu": repository_record,
        },
        "runtime": {
            "packages": {
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
                    run_experiment.APPROVED_RUNTIME_DISTRIBUTIONS.items()
                )
            }
        },
    }


def test_parser_imports_current_haiu_config_and_requires_explicit_branch() -> (
    None
):
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )

    assert args.branch == "experiment"


def test_parser_keeps_id_file_and_pair_catalogue_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(
            [
                "--login",
                "user",
                "--branch",
                "experiment",
                "--ontology-context-version",
                "1.5.8",
                "--ids-file",
                "ids.txt",
                "--input-catalog",
                "catalog.json",
            ]
        )


def test_pair_publication_protocol_supports_each_provider_full_matrix(
    tmp_path: Path,
) -> None:
    catalog, import_manifest = _pair_input_evidence(tmp_path)
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "pair_academiccloud",
            "--ontology-context-version",
            "1.15.0",
            "--input-catalog",
            str(catalog.path),
            "--dmw-input-manifest",
            str(import_manifest.path),
            "--provider-profile",
            "academiccloud-qwen36",
            "--publication-run",
            "--missing-id-policy",
            "fail",
        ]
    )

    run_experiment._validate_input_protocol(
        args=args,
        profile=provider_profile("academiccloud-qwen36"),
        input_catalog=catalog,
        dmw_input_manifest=import_manifest,
    )
    args.provider_profile = "lmstudio-qwen36-q6"
    run_experiment._validate_input_protocol(
        args=args,
        profile=provider_profile("lmstudio-qwen36-q6"),
        input_catalog=catalog,
        dmw_input_manifest=import_manifest,
    )

    args.conditions = ["workflow_rag", "haiu_rag_ontologizer"]
    with pytest.raises(SystemExit, match="all three conditions"):
        run_experiment._validate_input_protocol(
            args=args,
            profile=provider_profile("academiccloud-qwen36"),
            input_catalog=catalog,
            dmw_input_manifest=import_manifest,
        )


def test_pair_preflight_rejects_text_different_from_catalogue(
    tmp_path: Path,
) -> None:
    catalog, import_manifest = _pair_input_evidence(tmp_path)
    unit = catalog.records[0]
    client = SimpleNamespace(
        get_ontology_branches=lambda: [import_manifest.target_branch],
        get_regest_text=lambda _input_id: RegestText(
            regest_id=unit.input_unit_id,
            header=unit.header,
            subentries=("Different sublemma",),
        ),
    )

    with pytest.raises(SystemExit, match="differs from the frozen catalogue"):
        run_experiment._validate_pair_dmw_preflight(
            client=client,
            args=argparse.Namespace(branch="pair_academiccloud"),
            catalog=catalog,
            import_manifest=import_manifest,
            selected_ids=[unit.input_unit_id],
        )


def test_environment_lock_must_match_selected_runtime(tmp_path: Path) -> None:
    """Publication preflight must reject stale provider or branch evidence."""
    rc = _manifest_rc()
    path = tmp_path / "environment_lock.json"
    path.write_text(
        json.dumps(
            _environment_lock_payload(
                profile_name="academiccloud-qwen36",
                rc=rc,
                branch="publication-academiccloud",
            )
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(branch="publication-academiccloud")
    haiu_distribution = {"commit_id": "a" * 40}

    run_experiment._validate_environment_lock(
        path=path,
        args=args,
        profile=provider_profile("academiccloud-qwen36"),
        rc=rc,
        haiu_distribution=haiu_distribution,
    )

    args.branch = "different-branch"
    with pytest.raises(SystemExit, match="DMW branch differs"):
        run_experiment._validate_environment_lock(
            path=path,
            args=args,
            profile=provider_profile("academiccloud-qwen36"),
            rc=rc,
            haiu_distribution=haiu_distribution,
        )

    args.branch = "publication-academiccloud"
    with pytest.raises(SystemExit, match="does not match the imported"):
        run_experiment._validate_environment_lock(
            path=path,
            args=args,
            profile=provider_profile("academiccloud-qwen36"),
            rc=rc,
            haiu_distribution={"commit_id": "b" * 40},
        )


def test_pair_environment_lock_binds_harness_and_prepared_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, import_manifest = _pair_input_evidence(tmp_path)
    rc = _manifest_rc()
    payload = _environment_lock_payload(
        profile_name="academiccloud-qwen36",
        rc=rc,
        branch="pair_academiccloud",
    )
    payload["schema_version"] = 2
    payload["dmw_ontology_identity"]["collection"] = (
        "ontologies__pair_academiccloud"
    )
    payload["input_population"] = {
        "schema_version": 1,
        "unit_kind": "header_sublemma_pair",
        "file_sha256": catalog.file_sha256,
        "catalogue_content_sha256": catalog.content_sha256,
        "input_unit_count": len(catalog.records),
        "dmw_import_manifest_file_sha256": import_manifest.file_sha256,
        "dmw_import_manifest_content_sha256": import_manifest.content_sha256,
    }
    payload["dmw_data_identity"] = {
        "branch": "pair_academiccloud",
        "raw": "RG_raw_pair_academiccloud",
        "annotation": "annotations__pair_academiccloud",
        "ontology": "ontologies__pair_academiccloud",
        "ontology_context_version": "1.15.0",
    }
    payload["experiment_harness"] = {
        "commit": "c" * 40,
        "branch": "fix/haiu-paper-experiment",
        "worktree_clean": True,
    }
    path = tmp_path / "environment_lock_v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        run_experiment,
        "_experiment_harness_identity",
        lambda: {"commit": "c" * 40, "worktree_clean": True},
    )

    run_experiment._validate_environment_lock(
        path=path,
        args=argparse.Namespace(
            branch="pair_academiccloud",
            ontology_context_version="1.15.0",
        ),
        profile=provider_profile("academiccloud-qwen36"),
        rc=rc,
        haiu_distribution={"commit_id": "a" * 40},
        input_catalog=catalog,
        dmw_input_manifest=import_manifest,
    )


def test_complete_regest_run_rejects_pair_environment_lock(
    tmp_path: Path,
) -> None:
    path = tmp_path / "environment_lock_v2.json"
    path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

    with pytest.raises(SystemExit, match="Complete-regest.*schema_version 1"):
        run_experiment._validate_environment_lock(
            path=path,
            args=argparse.Namespace(),
            profile=provider_profile("academiccloud-qwen36"),
            rc=_manifest_rc(),
            haiu_distribution={"commit_id": "a" * 40},
        )


def test_parser_exposes_resume_and_retry_controls() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--resume",
            "--max-attempts",
            "5",
            "--retry-delay-seconds",
            "60",
        ]
    )

    assert args.resume is True
    assert args.max_attempts == 5
    assert args.retry_delay_seconds == 60.0
    assert args.annotation_max_attempts == 3
    assert args.progress_poll_seconds == 2.0


def test_parser_defaults_to_larger_generation_cap() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )

    assert args.max_output_tokens == 60_000


def test_output_cap_recovery_selects_only_unconstrained_fixed_cap_stops() -> (
    None
):
    fixed_cap_failure = {
        "output_truncated": True,
        "generation_budget": {
            "stage2": {
                "requested_max_output_tokens": 20_000,
                "effective_max_output_tokens": 20_000,
                "output_constrained": False,
                "output_truncated": True,
            }
        },
    }
    context_limited_failure = {
        "output_truncated": True,
        "generation_budget": {
            "stage2": {
                "requested_max_output_tokens": 20_000,
                "effective_max_output_tokens": 7_500,
                "output_constrained": True,
                "output_truncated": True,
            }
        },
    }

    assert retry_policy._is_output_cap_recovery_candidate(
        fixed_cap_failure,
        recovery_cap=20_000,
    )
    assert not retry_policy._is_output_cap_recovery_candidate(
        context_limited_failure,
        recovery_cap=20_000,
    )


def test_output_cap_recovery_requires_explicit_resume_amendment() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--output-cap-recovery-id",
            "output-cap-60000",
            "--rerun-output-truncated-at-cap",
            "20000",
        ]
    )

    with pytest.raises(SystemExit, match="requires --resume"):
        retry_policy._validate_output_cap_recovery_arguments(
            args=args,
            has_existing_results=True,
        )
    args.resume = True
    args.max_output_tokens = 20_000
    with pytest.raises(SystemExit, match="must exceed"):
        retry_policy._validate_output_cap_recovery_arguments(
            args=args,
            has_existing_results=True,
        )


def test_provider_timeout_recovery_selects_only_exhausted_cap_replays() -> None:
    timeout_replay = {
        "success": False,
        "non_retryable": False,
        "output_truncated": False,
        "failure_code": "ontology_generation_failed",
        "attempt": 3,
        "output_cap_recovery": {"amendment_id": "output-cap-60000"},
        "attempt_history": [
            {"error_message": "request timed out after 360 seconds"},
            {"error_message": "request timed out after 360 seconds"},
            {"error_message": "request timed out after 360 seconds"},
        ],
    }
    mixed_failure = {
        **timeout_replay,
        "attempt_history": [
            {"error_message": "request timed out after 360 seconds"},
            {"error_message": "validation failed"},
            {"error_message": "request timed out after 360 seconds"},
        ],
    }
    already_replayed_timeout = {
        **timeout_replay,
        "provider_timeout_recovery": {
            "amendment_id": "provider-timeout-60000",
        },
    }

    assert retry_policy._is_provider_timeout_recovery_candidate(
        timeout_replay,
        expected_output_cap_recovery_id="output-cap-60000",
        required_attempts=3,
    )
    assert not retry_policy._is_provider_timeout_recovery_candidate(
        mixed_failure,
        expected_output_cap_recovery_id="output-cap-60000",
        required_attempts=3,
    )
    assert not retry_policy._is_provider_timeout_recovery_candidate(
        already_replayed_timeout,
        expected_output_cap_recovery_id="output-cap-60000",
        required_attempts=3,
    )


def test_provider_timeout_recovery_requires_cap_recovery_chain() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--resume",
            "--provider-timeout-recovery-id",
            "provider-timeout-60000",
        ]
    )

    with pytest.raises(SystemExit, match="preceding --output-cap-recovery-id"):
        retry_policy._validate_provider_timeout_recovery_arguments(
            args=args,
            has_existing_results=True,
        )


def test_connection_recovery_selects_only_exhausted_transport_failures() -> (
    None
):
    connection_failure = {
        "success": False,
        "non_retryable": False,
        "output_truncated": False,
        "failure_code": "ontology_generation_failed",
        "attempt": 3,
        "attempt_history": [
            {"error_message": "Connection error"},
            {"error_message": "Connection error"},
            {"error_message": "Connection error"},
        ],
    }
    context_failure = {
        **connection_failure,
        "output_truncated": True,
    }
    already_replayed_connection = {
        **connection_failure,
        "connection_recovery": {"amendment_id": "connection-20260730"},
    }

    assert retry_policy._is_connection_recovery_candidate(
        connection_failure,
        required_attempts=3,
    )
    assert not retry_policy._is_connection_recovery_candidate(
        context_failure,
        required_attempts=3,
    )
    assert not retry_policy._is_connection_recovery_candidate(
        already_replayed_connection,
        required_attempts=3,
    )


def test_connection_recovery_requires_cap_recovery_chain() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--resume",
            "--connection-recovery-id",
            "connection-20260730",
        ]
    )

    with pytest.raises(SystemExit, match="preceding --output-cap-recovery-id"):
        retry_policy._validate_connection_recovery_arguments(
            args=args,
            has_existing_results=True,
        )


def test_local_runtime_recovery_selects_only_approved_failures() -> None:
    context_failure = {
        "success": False,
        "output_truncated": False,
        "error_message": (
            "HTTP 400: Number of tokens to keep from the initial prompt is "
            "greater than the context length"
        ),
    }
    stale_model_failure = {
        "success": False,
        "output_truncated": False,
        "annotation_preparation": {
            "error_message": 'Invalid model identifier "qwen3.6-27b-rtx"',
        },
    }
    http_502_failure = {
        "success": False,
        "output_truncated": False,
        "failure_code": "ontology_generation_failed",
        "attempt": 3,
        "attempt_history": [
            {
                "error_message": (
                    "Workflow failure: Failed to get initial ontology "
                    "modeling response."
                )
            }
            for _ in range(3)
        ],
    }
    length_failure = {
        **http_502_failure,
        "output_truncated": True,
    }
    already_replayed = {
        **context_failure,
        "local_runtime_recovery": {
            "amendment_id": "lmstudio-runtime-20260803",
        },
    }

    assert retry_policy._is_local_runtime_recovery_candidate(
        context_failure,
        required_attempts=3,
    )
    assert retry_policy._is_local_runtime_recovery_candidate(
        stale_model_failure,
        required_attempts=3,
    )
    assert retry_policy._is_local_runtime_recovery_candidate(
        http_502_failure,
        required_attempts=3,
    )
    assert not retry_policy._is_local_runtime_recovery_candidate(
        length_failure,
        required_attempts=3,
    )
    assert not retry_policy._is_local_runtime_recovery_candidate(
        already_replayed,
        required_attempts=3,
    )


def test_local_runtime_recovery_requires_cap_recovery_chain() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--resume",
            "--local-runtime-recovery-id",
            "lmstudio-runtime-20260803",
        ]
    )

    with pytest.raises(SystemExit, match="preceding --output-cap-recovery-id"):
        retry_policy._validate_local_runtime_recovery_arguments(
            args=args,
            has_existing_results=True,
        )


def test_recovery_metadata_is_attached_to_retry_checkpoints() -> None:
    key = ("workflow_rag", "11007477")
    payload: dict[str, object] = {}
    args = argparse.Namespace(
        output_cap_recovery_id="output-cap-60000",
        rerun_output_truncated_at_cap=20_000,
        max_output_tokens=60_000,
        max_attempts=3,
        provider_timeout_recovery_id="provider-timeout-60000",
        connection_recovery_id="connection-20260730",
        local_runtime_recovery_id="lmstudio-runtime-20260803",
    )
    output_cap_archive = {
        "canonical_raw_artifact_path": "superseded/output-cap/raw.json",
        "canonical_raw_sha256": "output-cap-sha",
    }
    timeout_archive = {
        "canonical_raw_artifact_path": "superseded/timeout/raw.json",
        "canonical_raw_sha256": "timeout-sha",
    }
    timeout_source = {
        "output_cap_recovery": {
            "amendment_id": "output-cap-60000",
            "superseded_raw_sha256": "output-cap-sha",
        }
    }
    connection_archive = {
        "canonical_raw_artifact_path": "superseded/connection/raw.json",
        "canonical_raw_sha256": "connection-sha",
    }
    connection_source = {
        "failure_code": "ontology_generation_failed",
        "attempt": 3,
        "error_message": (
            "Number of tokens to keep from the initial prompt is greater "
            "than the context length"
        ),
    }
    local_runtime_archive = {
        "canonical_raw_artifact_path": "superseded/local-runtime/raw.json",
        "canonical_raw_sha256": "local-runtime-sha",
    }
    local_runtime_source = connection_source
    annotation_attempt_archive = {
        "superseded_annotation_attempt_state_path": (
            "superseded/local-runtime/annotation_attempts/11007477.json"
        ),
    }

    retry_policy._attach_recovery_metadata(
        payload,
        key=key,
        args=args,
        output_cap_recovered_archives={key: output_cap_archive},
        timeout_recovered_archives={key: timeout_archive},
        timeout_recovery_sources={key: timeout_source},
        connection_recovered_archives={key: connection_archive},
        connection_recovery_sources={key: connection_source},
        local_runtime_recovered_archives={key: local_runtime_archive},
        local_runtime_recovery_sources={key: local_runtime_source},
        local_runtime_annotation_attempt_archives={
            key[1]: annotation_attempt_archive
        },
    )

    assert (
        payload["output_cap_recovery"] == timeout_source["output_cap_recovery"]
    )
    assert payload["provider_timeout_recovery"] == {
        "amendment_id": "provider-timeout-60000",
        "predecessor_output_cap_recovery_id": "output-cap-60000",
        "superseded_raw_artifact_path": "superseded/timeout/raw.json",
        "superseded_raw_sha256": "timeout-sha",
    }
    assert payload["connection_recovery"] == {
        "amendment_id": "connection-20260730",
        "predecessor_output_cap_recovery_id": "output-cap-60000",
        "original_failure_code": "ontology_generation_failed",
        "original_attempts": 3,
        "superseded_raw_artifact_path": "superseded/connection/raw.json",
        "superseded_raw_sha256": "connection-sha",
    }
    assert payload["local_runtime_recovery"] == {
        "amendment_id": "lmstudio-runtime-20260803",
        "original_reasons": ["context_admission_rejected"],
        "original_failure_code": "ontology_generation_failed",
        "original_attempts": 3,
        "corrected_model_id": "qwen/qwen3.6-27b",
        "verified_context_window_tokens": 262_144,
        "superseded_raw_artifact_path": "superseded/local-runtime/raw.json",
        "superseded_raw_sha256": "local-runtime-sha",
        "superseded_annotation_attempt_state": annotation_attempt_archive,
    }


def test_ordered_rows_follows_id_then_condition_order() -> None:
    rows_by_key = {
        ("second", "1"): {"value": "1-second"},
        ("first", "2"): {"value": "2-first"},
        ("first", "1"): {"value": "1-first"},
    }

    rows = _ordered_rows(
        ids=["1", "2"],
        conditions=("first", "second"),
        rows_by_key=rows_by_key,
    )

    assert [row["value"] for row in rows] == [
        "1-first",
        "1-second",
        "2-first",
    ]


def test_condition_order_rotates_each_three_condition_block() -> None:
    conditions = (
        "workflow_full_ontology",
        "workflow_rag",
        "haiu_rag_ontologizer",
    )

    assert [
        _condition_order_for_index(conditions=conditions, index=index)
        for index in range(3)
    ] == [
        conditions,
        ("workflow_rag", "haiu_rag_ontologizer", "workflow_full_ontology"),
        ("haiu_rag_ontologizer", "workflow_full_ontology", "workflow_rag"),
    ]


def test_annotation_failure_is_terminal_and_skips_completed_workflows() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )
    result = _annotation_preparation_failure_result(
        condition="workflow_rag",
        regest_id="1",
        model="qwen3.6-27b",
        error=FrozenAnnotationError("provider connection error"),
        args=args,
    )

    assert result.success is False
    assert result.payload["failure_code"] == "annotation_generation_failed"
    assert result.payload["non_retryable"] is True
    assert _is_terminal_result_payload(result.payload)
    assert not _workflow_conditions_require_annotation(
        regest_id="1",
        conditions=("workflow_full_ontology", "workflow_rag"),
        rows_by_key={
            ("workflow_full_ontology", "1"): {
                "success": True,
            },
            ("workflow_rag", "1"): result.payload,
        },
        max_attempts=args.max_attempts,
    )
    assert _workflow_conditions_require_annotation(
        regest_id="1",
        conditions=("workflow_full_ontology", "workflow_rag"),
        rows_by_key={
            ("workflow_full_ontology", "1"): {
                "success": True,
            },
        },
        max_attempts=args.max_attempts,
    )


def test_exhausted_annotation_checkpoint_is_not_replayed_on_resume() -> None:
    attempt_state = {
        "status": "failed",
        "attempt": 3,
        "attempt_history": [
            {"attempt": 2, "error_message": "first provider timeout"},
            {"attempt": 3, "error_message": "last provider timeout"},
        ],
    }

    assert _is_annotation_preparation_retry_exhausted(
        attempt_state,
        max_attempts=3,
    )
    assert not _is_annotation_preparation_retry_exhausted(
        {**attempt_state, "status": "running"},
        max_attempts=3,
    )

    error = _annotation_preparation_exhaustion_error(
        regest_id="1",
        attempt_state=attempt_state,
        max_attempts=3,
    )

    assert str(error) == (
        "Annotation preparation failed for 1 after 3 attempt(s): "
        "last provider timeout"
    )


def test_retry_exhaustion_skips_annotation_without_rewriting_evidence() -> None:
    exhausted = {
        "success": False,
        "non_retryable": False,
        "output_truncated": False,
        "attempt": 3,
    }

    assert retry_policy._is_retry_budget_exhausted(
        exhausted,
        max_attempts=3,
    )
    assert retry_policy._is_resume_complete_result(
        exhausted,
        max_attempts=3,
    )
    assert not _workflow_conditions_require_annotation(
        regest_id="1",
        conditions=("workflow_full_ontology", "workflow_rag"),
        rows_by_key={
            ("workflow_full_ontology", "1"): exhausted,
            ("workflow_rag", "1"): exhausted,
        },
        max_attempts=3,
    )
    assert _workflow_conditions_require_annotation(
        regest_id="1",
        conditions=("workflow_full_ontology", "workflow_rag"),
        rows_by_key={
            ("workflow_full_ontology", "1"): {
                **exhausted,
                "attempt": 2,
            },
        },
        max_attempts=3,
    )


def test_terminal_attempt_state_preserves_retry_exhaustion() -> None:
    payload = retry_policy._terminal_attempt_state_payload(
        condition="workflow_rag",
        regest_id="1",
        result={"success": False, "attempt": 3},
    )

    assert payload == {
        "condition": "workflow_rag",
        "regest_id": "1",
        "status": "failed",
        "attempt": 3,
        "success": False,
    }


def test_restored_result_excludes_all_derived_artifact_paths() -> None:
    restored = _experiment_result_from_row(
        {
            "condition": "workflow_rag",
            "regest_id": "1",
            "success": True,
            "raw_artifact_path": "raw/workflow_rag/1.json",
            "raw_ttl_artifact_path": "raw_ttl/workflow_rag/1.ttl",
            "raw_yaml_artifact_path": "raw_yaml/workflow_rag/1.yaml",
            "prompt_artifact_paths": {"stage1": "prompts/example.md"},
            "tbox": ":A a owl:Class .",
        }
    )

    assert restored.payload == {
        "condition": "workflow_rag",
        "regest_id": "1",
        "success": True,
        "tbox": ":A a owl:Class .",
    }


def test_run_manifest_captures_resume_sensitive_configuration() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--provider-profile",
            "academiccloud-qwen36",
        ]
    )

    manifest = _run_manifest(
        args=args,
        conditions=(
            "workflow_full_ontology",
            "workflow_rag",
            "haiu_rag_ontologizer",
        ),
        ids=["1", "2"],
        run_id="fixed",
        model="qwen3.6-27b",
        historian_input="exact prompt",
        annotation_guidelines="curated guideline",
        raw_regest_snapshot=None,
        rc=_manifest_rc(),
        workflow_model_provenance={
            "ontology": {"input_name": "qwen3.6-27b"},
            "annotation": {"input_name": "qwen3.6-27b"},
        },
        profile=provider_profile("academiccloud-qwen36"),
        provenance={"schema_version": 1, "inputs": {}},
        haiu_distribution={
            "version": "1.8.0",
            "distribution_archive_hash": "sha256=example",
        },
    )

    assert manifest["models"] == {
        "standalone_and_ontology": "qwen3.6-27b",
        "annotation": "qwen3.6-27b",
    }
    assert manifest["regest_ids"] == ["1", "2"]
    assert manifest["schema_version"] == 5
    assert manifest["haiu_distribution"]["version"] == "1.8.0"
    assert manifest["workflow"]["shared_frozen_annotation"] is True
    assert manifest["workflow"]["existing_data_policy"] == "reuse"
    assert manifest["workflow"]["require_existing_annotation"] is True
    assert (
        manifest["ontology"]["historian_input_sha256"]
        == "eed1d81b1a386e05e946a46581d3a07f3a1be21fb4ff482de024318f1fab19e9"
    )


def test_pair_run_manifest_uses_new_schema_without_changing_legacy_shape() -> (
    None
):
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "pair_academiccloud",
            "--ontology-context-version",
            "1.15.0",
        ]
    )
    input_population = {
        "unit_kind": "header_sublemma_pair",
        "input_unit_count": 480,
    }

    manifest = _run_manifest(
        args=args,
        conditions=tuple(run_experiment.DEFAULT_CONDITIONS),
        ids=["hsp-100-s01"],
        run_id="pair-run",
        model="qwen3.6-27b",
        historian_input="prompt",
        annotation_guidelines="guideline",
        raw_regest_snapshot=None,
        rc=_manifest_rc(),
        workflow_model_provenance={
            "ontology": {"input_name": "qwen3.6-27b"},
            "annotation": {"input_name": "qwen3.6-27b"},
        },
        profile=provider_profile("academiccloud-qwen36"),
        provenance={"schema_version": 1, "inputs": {}},
        haiu_distribution={"version": "1.8.0"},
        input_population=input_population,
    )

    assert manifest["schema_version"] == 6
    assert manifest["input_population"] == input_population


def test_selected_model_entry_keeps_effective_generation_settings() -> None:
    catalog = {
        "success": True,
        "use_case": "ontology",
        "models": [
            {
                "input_name": "qwen3.5-397b-a17b",
                "provider": "kisski",
                "provider_model_id": "qwen3.5-397b-a17b",
                "context_window_tokens": 262_144,
                "max_output_tokens": 81_920,
                "capability_source": "static",
                "generation_params": {"max_tokens": 20_000},
                "is_available": True,
            }
        ],
    }

    entry = _selected_model_entry(
        catalog,
        model_name="qwen3.5-397b-a17b",
    )

    assert entry["generation_params"] == {"max_tokens": 20_000}
    assert "is_available" not in entry


def test_publication_distribution_gate_accepts_hashed_wheel() -> None:
    run_experiment._require_published_haiu_distribution(
        {
            "version": "1.8.0",
            "editable": False,
            "vcs": None,
            "direct_url": (
                "https://github.com/HisQu/haiu/releases/download/v1.8.0/"
                "haiu-1.8.0-py3-none-any.whl"
            ),
            "distribution_archive_hash": "sha256=" + "a" * 64,
        }
    )


def test_publication_distribution_gate_rejects_editable_checkout() -> None:
    with pytest.raises(SystemExit, match="non-editable Haiu installation"):
        run_experiment._require_published_haiu_distribution(
            {
                "version": "1.8.0",
                "editable": True,
                "vcs": None,
                "direct_url": "file:///workspace/haiu",
                "distribution_archive_hash": None,
            }
        )


def test_publication_distribution_gate_accepts_approved_vcs_release() -> None:
    run_experiment._require_published_haiu_distribution(
        {
            "version": "1.8.0",
            "editable": False,
            "vcs": "git",
            "direct_url": "https://github.com/HisQu/haiu.git",
            "requested_revision": "v1.8.0",
            "commit_id": "a" * 40,
        }
    )


def test_publication_distribution_gate_rejects_incomplete_vcs_commit() -> None:
    with pytest.raises(SystemExit, match="approved Haiu Git release source"):
        run_experiment._require_published_haiu_distribution(
            {
                "version": "1.8.0",
                "editable": False,
                "vcs": "git",
                "direct_url": "https://github.com/HisQu/haiu.git",
                "requested_revision": "v1.8.0",
                "commit_id": "wrong-commit",
            }
        )


def test_retry_reuses_completed_workflow_state_and_records_attempts(
    monkeypatch,
) -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--max-attempts",
            "2",
            "--retry-delay-seconds",
            "0",
        ]
    )
    results = iter(
        (
            ExperimentResult(
                condition="workflow_full_ontology",
                regest_id="1",
                success=False,
                payload={
                    "duration_seconds": 3.0,
                    "error_message": "temporary failure",
                },
            ),
            ExperimentResult(
                condition="workflow_full_ontology",
                regest_id="1",
                success=True,
                payload={"duration_seconds": 5.0, "error_message": None},
            ),
        )
    )
    checkpoints: list[ExperimentResult] = []

    def fake_run_condition_once(**kwargs: Any) -> ExperimentResult:
        return next(results)

    monkeypatch.setattr(
        run_experiment,
        "_run_condition_once",
        fake_run_condition_once,
    )

    result = _run_condition_with_retries(
        args=args,
        client=cast(Any, object()),
        rc=cast(HaiuRC, SimpleNamespace()),
        regest_id="1",
        condition="workflow_full_ontology",
        run_id="run",
        model="model",
        historian_input="prompt",
        annotation_guidelines="guideline",
        frozen_regest=None,
        frozen_annotation=None,
        checkpoint_failed_attempt=checkpoints.append,
    )

    assert len(checkpoints) == 1
    assert checkpoints[0].payload["attempt"] == 1
    assert result.payload["attempt"] == 2
    assert result.payload["attempt_duration_seconds"] == 5.0
    assert result.payload["duration_seconds"] == 8.0
    assert result.payload["total_attempt_duration_seconds"] == 8.0
    assert result.payload["total_retry_delay_seconds"] == 0.0
    assert result.payload["attempt_history"] == [
        {
            "attempt": 1,
            "success": False,
            "duration_seconds": 3.0,
            "request_duration_seconds": None,
            "error_message": "temporary failure",
            "generation_budget": None,
            "output_constrained": None,
            "output_truncated": None,
            "publication_eligible": None,
        },
        {
            "attempt": 2,
            "success": True,
            "duration_seconds": 5.0,
            "request_duration_seconds": None,
            "error_message": None,
            "generation_budget": None,
            "output_constrained": None,
            "output_truncated": None,
            "publication_eligible": None,
        },
    ]


def test_resume_continues_attempt_numbers_and_cumulative_timing(
    monkeypatch,
) -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--max-attempts",
            "3",
            "--retry-delay-seconds",
            "0",
        ]
    )
    previous_result = {
        "condition": "workflow_rag",
        "regest_id": "1",
        "success": False,
        "attempt": 1,
        "attempt_history": [
            {
                "attempt": 1,
                "success": False,
                "duration_seconds": 4.5,
                "error_message": "worker failure",
            }
        ],
        "total_retry_delay_seconds": 2.0,
        "total_elapsed_seconds": 6.5,
    }

    def fake_run_condition_once(**kwargs: Any) -> ExperimentResult:
        return ExperimentResult(
            condition="workflow_rag",
            regest_id="1",
            success=True,
            payload={"duration_seconds": 5.0, "error_message": None},
        )

    monkeypatch.setattr(
        run_experiment,
        "_run_condition_once",
        fake_run_condition_once,
    )

    result = _run_condition_with_retries(
        args=args,
        client=cast(Any, object()),
        rc=cast(HaiuRC, SimpleNamespace()),
        regest_id="1",
        condition="workflow_rag",
        run_id="run",
        model="model",
        historian_input="prompt",
        annotation_guidelines="guideline",
        frozen_regest=None,
        frozen_annotation=None,
        previous_result=previous_result,
    )

    assert result.payload["attempt"] == 2
    assert result.payload["attempt_duration_seconds"] == 5.0
    assert result.payload["duration_seconds"] == 9.5
    assert result.payload["total_attempt_duration_seconds"] == 9.5
    assert result.payload["total_retry_delay_seconds"] == 2.0
    assert result.payload["total_elapsed_seconds"] >= 6.5
    assert result.payload["attempt_history"] == [
        previous_result["attempt_history"][0],
        {
            "attempt": 2,
            "success": True,
            "duration_seconds": 5.0,
            "request_duration_seconds": None,
            "error_message": None,
            "generation_budget": None,
            "output_constrained": None,
            "output_truncated": None,
            "publication_eligible": None,
        },
    ]


def test_non_retryable_context_capacity_outcome_is_not_retried(
    monkeypatch,
) -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )

    monkeypatch.setattr(
        run_experiment,
        "_run_condition_once",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    previous = {
        "condition": "workflow_full_ontology",
        "regest_id": "1",
        "success": False,
        "non_retryable": True,
        "failure_code": "model_context_window_exceeded",
    }

    result = _run_condition_with_retries(
        args=args,
        client=cast(Any, object()),
        rc=cast(HaiuRC, SimpleNamespace()),
        regest_id="1",
        condition="workflow_full_ontology",
        run_id="run",
        model="model",
        historian_input="prompt",
        annotation_guidelines="guideline",
        frozen_regest=None,
        frozen_annotation=None,
        previous_result=previous,
    )

    assert result.payload["failure_code"] == "model_context_window_exceeded"


def test_output_truncation_is_not_retried_when_adapter_omits_flag(
    monkeypatch,
) -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )
    calls = 0

    def truncated_result(**_kwargs: Any) -> ExperimentResult:
        nonlocal calls
        calls += 1
        return ExperimentResult(
            condition="haiu_rag_ontologizer",
            regest_id="1",
            success=False,
            payload={
                "duration_seconds": 1.0,
                "output_truncated": True,
                "error_message": "provider length limit",
            },
        )

    monkeypatch.setattr(
        run_experiment,
        "_run_condition_once",
        truncated_result,
    )

    result = _run_condition_with_retries(
        args=args,
        client=cast(Any, object()),
        rc=cast(HaiuRC, SimpleNamespace()),
        regest_id="1",
        condition="haiu_rag_ontologizer",
        run_id="run",
        model="model",
        historian_input="prompt",
        annotation_guidelines="guideline",
        frozen_regest=RegestText(regest_id="1", header="Header"),
        frozen_annotation=None,
    )

    assert calls == 1
    assert result.payload["non_retryable"] is True


def test_direct_condition_has_hard_wall_clock_timeout(monkeypatch) -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
            "--timeout-seconds",
            "0.02",
        ]
    )

    def slow_direct_condition(**_kwargs: Any) -> ExperimentResult:
        time.sleep(1)
        raise AssertionError("Wall-clock timeout did not interrupt sleep.")

    monkeypatch.setattr(
        run_experiment,
        "run_haiu_rag_condition",
        slow_direct_condition,
    )

    result = _run_condition_once(
        args=args,
        client=cast(Any, object()),
        rc=cast(HaiuRC, SimpleNamespace()),
        regest_id="1",
        condition="haiu_rag_ontologizer",
        run_id="run",
        model="model",
        historian_input="prompt",
        annotation_guidelines="guideline",
        frozen_regest=RegestText(regest_id="1", header="Header"),
        frozen_annotation=None,
    )

    assert result.success is False
    assert result.payload["failure_stage"] == "condition_wall_clock_timeout"
    assert result.payload["wall_clock_timeout_seconds"] == 0.02
    assert float(result.payload["duration_seconds"]) < 1


def test_workflow_config_can_reuse_state_on_resumed_failure() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )

    config = _workflow_config(
        args=args,
        condition="workflow_full_ontology",
        run_id="run",
        model="model",
        historian_input="prompt",
        frozen_annotation=None,
    )

    assert config.existing_data_policy == "reuse"


def test_workflow_config_requires_reuse_on_first_attempt() -> None:
    args = _build_parser().parse_args(
        [
            "--login",
            "user",
            "--branch",
            "experiment",
            "--ontology-context-version",
            "1.5.8",
        ]
    )

    config = _workflow_config(
        args=args,
        condition="workflow_rag",
        run_id="run",
        model="model",
        historian_input="prompt",
        frozen_annotation=None,
    )

    assert config.existing_data_policy == "reuse"
    assert config.require_existing_annotation is True


def _pair_input_evidence(tmp_path: Path):
    catalogue_path = TEMPLATE_INPUT_ROOT / "header_sublemma_input_catalog.json"
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
    storage_evidence = {
        "source_branch": {
            "branch_slug": spec.source_branch,
            "github_branch": spec.source_branch,
            "github_tag_scope": spec.source_branch,
            "latest_version": "1.15.0",
        },
        "target_branch": {
            "branch_slug": spec.target_branch,
            "branch_name": "Header--sublemma replication: pair_academiccloud",
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
    }
    path = tmp_path / "dmw_pair_import.json"
    write_manifest(
        path,
        build_import_manifest(
            catalog=catalog,
            spec=spec,
            storage_evidence=storage_evidence,
        ),
    )
    return catalog, load_dmw_pair_import_manifest(path, catalog=catalog)
