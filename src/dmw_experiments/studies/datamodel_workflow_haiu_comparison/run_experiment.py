#!/usr/bin/env python3
"""Run the Haiu/datamodel-workflow ontology comparison experiment.

Example usage:

DATAMODEL_PASSWORD='CHANGE_ME' .venv/bin/python \
  experiments/datamodel_workflow_haiu_comparison/run_experiment.py \
  --login CHANGE_ME \
  --base-url http://localhost:8000 \
  --branch experiment-branch \
  --run-id "manual-$(date -u +%Y%m%dT%H%M%SZ)" \
  --ontology-context-version 1.5.8 \
  --limit 5
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Iterator

import haiu
from haiu import HaiuRC
from haiu.config import HAIU_CONFIG
from haiu.llm_specs import llm_spec

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.artifacts import (
    ArtifactWriter,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.annotation_runner import (
    AnnotationPreparationConfig,
    FrozenAnnotation,
    FrozenAnnotationError,
    prepare_frozen_annotation,
    verify_frozen_annotation,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.datamodel_api import (
    DatamodelClient,
    WorkflowRequestConfig,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.direct_condition import (
    run_haiu_rag_condition,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.id_resolution import (
    MissingRegestIdsError,
    resolve_available_regest_ids,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.ids import (
    parse_regest_id_entries,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.input_catalog import (
    DmwPairImportManifest,
    HeaderSublemmaCatalog,
    PairInputCandidate,
    load_dmw_pair_import_manifest,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.models import (
    ExperimentResult,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.provider_profiles import (
    PROVIDER_PROFILES,
    ProviderProfile,
    provider_profile,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.workflow_runner import (
    run_workflow_condition,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.direct_runner import (
    DirectRunConfig,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.models import (
    RegestText,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.paths import (
    INPUT_ROOT,
    REPOSITORY_ROOT,
    STUDY_ROOT,
)

EXPERIMENT_ROOT = STUDY_ROOT
DEFAULT_INPUT_DIR = INPUT_ROOT
DEFAULT_LOCAL_IDS = DEFAULT_INPUT_DIR / "ablaesse_cp_ids.txt"
DEFAULT_PROMPT_FILE = DEFAULT_INPUT_DIR / "historian_ontology_user_input.md"
DEFAULT_ANNOTATION_GUIDELINES_FILE = (
    DEFAULT_INPUT_DIR / "annotation_guidelines.md"
)
DEFAULT_CONDITIONS = (
    "workflow_full_ontology",
    "workflow_rag",
    "haiu_rag_ontologizer",
)
PUBLISHED_HAIU_VERSION = "1.8.0"
APPROVED_HAIU_VCS_URL = "https://github.com/HisQu/haiu.git"
APPROVED_HAIU_VCS_REVISION = "v1.8.0"
APPROVED_RUNTIME_DISTRIBUTIONS = {
    "datamodel-workflow": {
        "version": "1.1.3",
        "url": "https://github.com/HisQu/datamodel-workflow.git",
        "revision": "v1.1.3",
        "repository": "datamodel_workflow",
    },
    "opa": {
        "version": "2.1.2",
        "url": "https://github.com/HisQu/OPA.git",
        "revision": "v2.1.2",
        "repository": "opa",
    },
    "gta": {
        "version": "0.2.4",
        "url": "https://github.com/HisQu/GTA.git",
        "revision": "v0.2.4",
        "repository": "gta",
    },
    "haiu": {
        "version": PUBLISHED_HAIU_VERSION,
        "url": APPROVED_HAIU_VCS_URL,
        "revision": APPROVED_HAIU_VCS_REVISION,
        "repository": "haiu",
    },
}
LOCAL_RUNTIME_RECOVERY_MODEL_ID = "qwen/qwen3.6-27b"
LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS = 262_144
LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR = (
    "number of tokens to keep from the initial prompt is greater than the "
    "context length"
)
LOCAL_RUNTIME_STALE_MODEL_ERROR = 'invalid model identifier "qwen3.6-27b-rtx"'
LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR = (
    "failed to get initial ontology modeling response."
)


class _ConditionWallClockTimeout(BaseException):
    """Interrupt a condition that exceeds the runner's hard time limit."""


def _load_runtime_environment(
    *,
    provider_environment_files: tuple[Path, ...],
) -> None:
    """Load explicit ignored runtime dotenv files in one place.

    Long-running services receive only file paths on their command line. This
    keeps provider and DMW credentials out of process arguments while retaining
    the dotenv precedence used by the published comparison runs.

    :param provider_environment_files: Ignored experiment-specific dotenv files.
    :return: ``None`` after populating the process environment.
    """
    from dotenv import load_dotenv

    for environment_file in provider_environment_files:
        if not environment_file.is_file():
            raise SystemExit(
                f"Provider environment file does not exist: {environment_file}"
            )
        load_dotenv(environment_file, override=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    :param argv: Optional argument vector.
    :return: Process exit code.
    """
    args = _build_parser().parse_args(argv)
    _load_runtime_environment(
        provider_environment_files=tuple(
            Path(path).expanduser() for path in args.env_file
        ),
    )
    profile = provider_profile(args.provider_profile)
    _validate_profile_model_overrides(args=args, profile=profile)
    input_catalog = _load_requested_input_catalog(args)
    dmw_input_manifest = _load_requested_dmw_input_manifest(
        args,
        input_catalog=input_catalog,
    )
    _validate_input_protocol(
        args=args,
        profile=profile,
        input_catalog=input_catalog,
        dmw_input_manifest=dmw_input_manifest,
    )
    if input_catalog is None:
        input_source_file = _resolve_ids_file(args.ids_file)
        candidates = parse_regest_id_entries(
            input_source_file,
            keep_duplicates=args.keep_duplicates,
        )
        input_lineage_by_id: dict[str, dict[str, int | str]] = {}
        input_population: dict[str, Any] | None = None
    else:
        input_source_file = input_catalog.path
        candidates = [
            PairInputCandidate(catalog_position=index, unit=unit)
            for index, unit in enumerate(input_catalog.records)
        ]
        input_lineage_by_id = {
            unit.input_unit_id: unit.lineage() for unit in input_catalog.records
        }
        input_population = input_catalog.manifest_entry()
    if not candidates:
        raise SystemExit(f"No experiment inputs found in {input_source_file}.")

    HAIU_CONFIG.bootstrap(
        env_files=tuple(Path(path).expanduser() for path in args.env_file),
        env_file_overrides_os_environ=False,
        load_dotenv_layers=True,
        storage=args.storage,
    )
    rc = HaiuRC()
    haiu_distribution = _installed_haiu_distribution_provenance()
    if args.publication_run:
        _require_published_haiu_distribution(haiu_distribution)
    model = profile.provider_generation_model
    if args.base_url_override:
        rc.client.base_url = args.base_url_override
    _configure_provider_profile(rc=rc, profile=profile)
    provenance_files = _provenance_files(args)
    if input_catalog is not None:
        assert dmw_input_manifest is not None
        provenance_files.update(
            {
                "input_catalog": input_catalog.path,
                "dmw_input_manifest": dmw_input_manifest.path,
            }
        )
    if args.publication_run:
        _validate_environment_lock(
            path=provenance_files["environment_lock"],
            args=args,
            profile=profile,
            rc=rc,
            haiu_distribution=haiu_distribution,
            input_catalog=input_catalog,
            dmw_input_manifest=dmw_input_manifest,
        )
    historian_input = _read_prompt(args.ontology_user_input_file)
    annotation_guidelines = _read_prompt(args.annotation_guidelines_file)
    selected_conditions = set(args.conditions)
    conditions = tuple(
        condition
        for condition in DEFAULT_CONDITIONS
        if condition in selected_conditions
    )
    run_id = args.run_id or _default_run_id()
    output_dir = Path(
        args.output_dir or REPOSITORY_ROOT / "output" / "runs" / run_id
    )
    writer = ArtifactWriter(output_dir)
    existing_rows = writer.load_existing_rows()
    if existing_rows and not args.resume:
        raise SystemExit(
            f"Output directory already contains {len(existing_rows)} result(s): "
            f"{output_dir}. Pass --resume to continue it."
        )
    _validate_output_cap_recovery_arguments(
        args=args,
        has_existing_results=bool(existing_rows),
    )
    _validate_provider_timeout_recovery_arguments(
        args=args,
        has_existing_results=bool(existing_rows),
    )
    _validate_connection_recovery_arguments(
        args=args,
        has_existing_results=bool(existing_rows),
    )
    _validate_local_runtime_recovery_arguments(
        args=args,
        has_existing_results=bool(existing_rows),
    )

    login = args.login or os.getenv("DATAMODEL_LOGIN", "")
    if not login:
        raise SystemExit(
            "Missing login. Set DATAMODEL_LOGIN in the ignored provider "
            "environment file."
        )
    password = args.password or os.getenv("DATAMODEL_PASSWORD", "")
    if not password:
        raise SystemExit(
            "Missing password. Pass --password or set DATAMODEL_PASSWORD."
        )

    print(f"Run ID: {run_id}")
    print(f"Candidate inputs: {len(candidates)} from {input_source_file}")
    print(f"Conditions: {', '.join(conditions)}")
    print(f"Output: {output_dir}")
    if existing_rows:
        print(f"Resume: recovered {len(existing_rows)} result(s)")
    workflow_conditions_selected = any(
        condition.startswith("workflow_") for condition in conditions
    )

    rows: list[dict] = []
    client = DatamodelClient(
        base_url=args.base_url,
        login=login,
        password=password,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        client.authenticate()
        try:
            id_selection = resolve_available_regest_ids(
                client=client,
                candidates=candidates,
                limit=args.limit,
                missing_id_policy=args.missing_id_policy,
            )
        except MissingRegestIdsError as exc:
            id_selection_path = writer.write_id_selection(
                exc.selection.as_dict(source_file=input_source_file)
            )
            print(f"ID selection: {id_selection_path}")
            raise SystemExit(str(exc)) from exc
        id_selection_path = writer.write_id_selection(
            id_selection.as_dict(source_file=input_source_file)
        )
        ids = id_selection.selected_ids
        print(
            f"Runnable IDs: {len(ids)} selected from "
            f"{len(id_selection.available)} available candidates"
        )
        if id_selection.skipped:
            print(
                f"Skipped missing IDs: {len(id_selection.skipped)} "
                f"(see {id_selection_path})"
            )
        else:
            print(f"ID selection: {id_selection_path}")
        if not ids:
            raise SystemExit(
                "No available regest IDs selected. "
                f"See preflight report at {id_selection_path}."
            )
        verified_pair_regests: dict[str, RegestText] = {}
        if input_catalog is not None:
            assert dmw_input_manifest is not None
            verified_pair_regests = _validate_pair_dmw_preflight(
                client=client,
                args=args,
                catalog=input_catalog,
                import_manifest=dmw_input_manifest,
                selected_ids=ids,
            )
        try:
            workflow_model_provenance = {
                "ontology": _selected_model_entry(
                    client.get_model_catalog(use_case="ontology"),
                    model_name=model,
                ),
                "annotation": _selected_model_entry(
                    client.get_model_catalog(use_case="ner"),
                    model_name=args.annotation_model or model,
                ),
            }
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        frozen_regests: dict[str, RegestText] = {}
        raw_regest_snapshot: dict[str, Any] | None = None
        if "haiu_rag_ontologizer" in conditions:
            frozen_fetcher = client.get_regest_text
            if input_catalog is not None:
                frozen_fetcher = _pair_regest_fetcher(
                    verified_regests=verified_pair_regests,
                )
            frozen_regests, raw_regest_snapshot = writer.ensure_frozen_regests(
                regest_ids=ids,
                fetcher=frozen_fetcher,
            )
        provenance_input_files: dict[str, Path] = {
            "historian_ontology_input": Path(args.ontology_user_input_file),
            "annotation_guidelines": Path(args.annotation_guidelines_file),
            **provenance_files,
        }
        if input_catalog is None:
            provenance_input_files["regest_ids"] = input_source_file
        provenance_metadata = {
            "provider_profile": profile.manifest_entry(),
            "haiu_distribution": haiu_distribution,
            "workflow_model_provenance": workflow_model_provenance,
            "raw_regest_snapshot": raw_regest_snapshot,
        }
        if input_population is not None:
            provenance_metadata["input_population"] = input_population
        amendment_path: Path | None = None
        provider_timeout_amendment_path: Path | None = None
        connection_recovery_amendment_path: Path | None = None
        local_runtime_recovery_amendment_path: Path | None = None
        base_manifest: dict[str, Any] | None = None
        try:
            if args.output_cap_recovery_id:
                writer.validate_frozen_provenance_inputs(
                    input_files=provenance_input_files,
                )
                base_manifest = writer.load_run_manifest()
                recovery_cap = args.rerun_output_truncated_at_cap
                assert recovery_cap is not None
                _validate_output_cap_recovery_base_manifest(
                    manifest=base_manifest,
                    args=args,
                    conditions=conditions,
                    ids=ids,
                    run_id=run_id,
                    model=model,
                    historian_input=historian_input,
                    annotation_guidelines=annotation_guidelines,
                    raw_regest_snapshot=raw_regest_snapshot,
                    rc=rc,
                    profile=profile,
                    haiu_distribution=haiu_distribution,
                    recovery_cap=recovery_cap,
                    input_population=input_population,
                )
                manifest_path = writer.ensure_run_manifest(
                    base_manifest,
                    has_existing_results=bool(existing_rows),
                )
                amendment_path = writer.ensure_run_amendment(
                    amendment_id=args.output_cap_recovery_id,
                    payload=_output_cap_recovery_amendment(
                        amendment_id=args.output_cap_recovery_id,
                        base_manifest_path=manifest_path,
                        base_manifest=base_manifest,
                        recovery_cap=recovery_cap,
                        replacement_cap=args.max_output_tokens,
                        workflow_model_provenance=workflow_model_provenance,
                    ),
                )
                if args.provider_timeout_recovery_id:
                    provider_timeout_amendment_path = (
                        writer.ensure_run_amendment(
                            amendment_id=args.provider_timeout_recovery_id,
                            payload=_provider_timeout_recovery_amendment(
                                amendment_id=(
                                    args.provider_timeout_recovery_id
                                ),
                                base_manifest_path=manifest_path,
                                base_manifest=base_manifest,
                                output_cap_recovery_id=(
                                    args.output_cap_recovery_id
                                ),
                                max_attempts=args.max_attempts,
                            ),
                        )
                    )
                if args.connection_recovery_id:
                    connection_recovery_amendment_path = (
                        writer.ensure_run_amendment(
                            amendment_id=args.connection_recovery_id,
                            payload=_connection_recovery_amendment(
                                amendment_id=args.connection_recovery_id,
                                base_manifest_path=manifest_path,
                                base_manifest=base_manifest,
                                output_cap_recovery_id=(
                                    args.output_cap_recovery_id
                                ),
                                max_attempts=args.max_attempts,
                            ),
                        )
                    )
                if args.local_runtime_recovery_id:
                    local_runtime_recovery_amendment_path = (
                        writer.ensure_run_amendment(
                            amendment_id=args.local_runtime_recovery_id,
                            payload=_local_runtime_recovery_amendment(
                                amendment_id=(args.local_runtime_recovery_id),
                                base_manifest_path=manifest_path,
                                base_manifest=base_manifest,
                                output_cap_recovery_id=(
                                    args.output_cap_recovery_id
                                ),
                                max_attempts=args.max_attempts,
                            ),
                        )
                    )
            else:
                provenance = writer.write_provenance(
                    input_files=provenance_input_files,
                    metadata=provenance_metadata,
                )
                manifest_path = writer.ensure_run_manifest(
                    _run_manifest(
                        args=args,
                        conditions=conditions,
                        ids=ids,
                        run_id=run_id,
                        model=model,
                        historian_input=historian_input,
                        annotation_guidelines=annotation_guidelines,
                        raw_regest_snapshot=raw_regest_snapshot,
                        rc=rc,
                        profile=profile,
                        provenance=provenance,
                        haiu_distribution=haiu_distribution,
                        workflow_model_provenance=workflow_model_provenance,
                        input_population=input_population,
                    ),
                    has_existing_results=bool(existing_rows),
                )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Run manifest: {manifest_path}")
        if amendment_path is not None:
            print(f"Run amendment: {amendment_path}")
        if provider_timeout_amendment_path is not None:
            print(
                f"Provider-timeout amendment: {provider_timeout_amendment_path}"
            )
        if connection_recovery_amendment_path is not None:
            print(
                "Connection-recovery amendment: "
                f"{connection_recovery_amendment_path}"
            )
        if local_runtime_recovery_amendment_path is not None:
            print(
                "Local-runtime recovery amendment: "
                f"{local_runtime_recovery_amendment_path}"
            )
        expected_keys = {
            (condition, regest_id)
            for regest_id in ids
            for condition in conditions
        }
        rows_by_key = {
            _row_key(row): row
            for row in existing_rows
            if _row_key(row) in expected_keys
        }
        unexpected_keys = {
            _row_key(row)
            for row in existing_rows
            if _row_key(row) not in expected_keys
        }
        if unexpected_keys:
            raise SystemExit(
                "Resume directory contains results outside the selected "
                f"condition/ID matrix: {sorted(unexpected_keys)}"
            )
        output_cap_recovered_archives: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        timeout_recovered_archives: dict[tuple[str, str], dict[str, Any]] = {}
        timeout_recovery_sources: dict[tuple[str, str], dict[str, Any]] = {}
        connection_recovered_archives: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        connection_recovery_sources: dict[tuple[str, str], dict[str, Any]] = {}
        local_runtime_recovered_archives: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        local_runtime_recovery_sources: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        local_runtime_annotation_attempt_archives: dict[
            str, dict[str, Any]
        ] = {}
        output_cap_recovery_keys = {
            key
            for key, row in rows_by_key.items()
            if _is_output_cap_recovery_candidate(
                row,
                recovery_cap=args.rerun_output_truncated_at_cap,
            )
        }
        if args.output_cap_recovery_id:
            for condition, regest_id in sorted(output_cap_recovery_keys):
                output_cap_recovered_archives[(condition, regest_id)] = (
                    writer.archive_result_for_amendment(
                        amendment_id=args.output_cap_recovery_id,
                        condition=condition,
                        regest_id=regest_id,
                    )
                )
                rows_by_key.pop((condition, regest_id))
            print(
                "Output-cap recovery: "
                f"queued {len(output_cap_recovery_keys)} terminal result(s) "
                "before "
                "remaining IDs"
            )
        timeout_recovery_keys = (
            {
                key
                for key, row in rows_by_key.items()
                if _is_provider_timeout_recovery_candidate(
                    row,
                    expected_output_cap_recovery_id=(
                        args.output_cap_recovery_id
                    ),
                    required_attempts=args.max_attempts,
                )
            }
            if args.provider_timeout_recovery_id
            else set()
        )
        if args.provider_timeout_recovery_id:
            for condition, regest_id in sorted(timeout_recovery_keys):
                timeout_recovery_sources[(condition, regest_id)] = rows_by_key[
                    (condition, regest_id)
                ]
                timeout_recovered_archives[(condition, regest_id)] = (
                    writer.archive_result_for_amendment(
                        amendment_id=args.provider_timeout_recovery_id,
                        condition=condition,
                        regest_id=regest_id,
                    )
                )
                rows_by_key.pop((condition, regest_id))
            print(
                "Provider-timeout recovery: "
                f"queued {len(timeout_recovery_keys)} exhausted replay "
                "result(s) before remaining IDs"
            )
        connection_recovery_keys = (
            {
                key
                for key, row in rows_by_key.items()
                if _is_connection_recovery_candidate(
                    row,
                    required_attempts=args.max_attempts,
                )
            }
            if args.connection_recovery_id
            else set()
        )
        if args.connection_recovery_id:
            for condition, regest_id in sorted(connection_recovery_keys):
                key = (condition, regest_id)
                connection_recovery_sources[key] = rows_by_key[key]
                connection_recovered_archives[key] = (
                    writer.archive_result_for_amendment(
                        amendment_id=args.connection_recovery_id,
                        condition=condition,
                        regest_id=regest_id,
                    )
                )
                rows_by_key.pop(key)
            print(
                "Connection recovery: "
                f"queued {len(connection_recovery_keys)} exhausted "
                "connection failure(s) before remaining IDs"
            )
        local_runtime_recovery_keys = (
            {
                key
                for key, row in rows_by_key.items()
                if _is_local_runtime_recovery_candidate(
                    row,
                    required_attempts=args.max_attempts,
                )
            }
            if args.local_runtime_recovery_id
            else set()
        )
        if args.local_runtime_recovery_id:
            for condition, regest_id in sorted(local_runtime_recovery_keys):
                key = (condition, regest_id)
                local_runtime_recovery_sources[key] = rows_by_key[key]
                local_runtime_recovered_archives[key] = (
                    writer.archive_result_for_amendment(
                        amendment_id=args.local_runtime_recovery_id,
                        condition=condition,
                        regest_id=regest_id,
                    )
                )
                rows_by_key.pop(key)
            for regest_id in sorted(
                {key[1] for key in local_runtime_recovery_keys}
            ):
                annotation_attempt_state = writer.load_annotation_attempt_state(
                    regest_id=regest_id
                )
                if writer.load_frozen_annotation(
                    regest_id=regest_id
                ) is None and _is_annotation_preparation_retry_exhausted(
                    annotation_attempt_state,
                    max_attempts=args.annotation_max_attempts,
                ):
                    archive = (
                        writer.archive_annotation_attempt_state_for_amendment(
                            amendment_id=args.local_runtime_recovery_id,
                            regest_id=regest_id,
                        )
                    )
                    if archive is not None:
                        local_runtime_annotation_attempt_archives[regest_id] = (
                            archive
                        )
            print(
                "Local-runtime recovery: "
                f"queued {len(local_runtime_recovery_keys)} terminal "
                "runtime failure(s) before remaining IDs; reset "
                f"{len(local_runtime_annotation_attempt_archives)} failed "
                "shared annotation checkpoint(s)"
            )
        rows = _ordered_rows(
            ids=ids,
            conditions=conditions,
            rows_by_key=rows_by_key,
        )

        priority_recovery_keys = (
            output_cap_recovery_keys
            | timeout_recovery_keys
            | connection_recovery_keys
            | local_runtime_recovery_keys
        )
        priority_indices = {
            index
            for index, regest_id in enumerate(ids)
            if any(
                (condition, regest_id) in priority_recovery_keys
                for condition in conditions
            )
        }
        execution_items = [
            (index, regest_id)
            for index, regest_id in enumerate(ids)
            if index in priority_indices
        ] + [
            (index, regest_id)
            for index, regest_id in enumerate(ids)
            if index not in priority_indices
        ]
        for index, regest_id in execution_items:
            input_lineage = input_lineage_by_id.get(regest_id)
            frozen_annotation: FrozenAnnotation | None = None
            frozen_annotation_paths: dict[str, str] | None = None
            annotation_preparation_error: FrozenAnnotationError | None = None
            condition_order = _condition_order_for_index(
                conditions=conditions,
                index=index,
            )
            if (
                workflow_conditions_selected
                and args.include_annotations
                and _workflow_conditions_require_annotation(
                    regest_id=regest_id,
                    conditions=conditions,
                    rows_by_key=rows_by_key,
                    max_attempts=args.max_attempts,
                )
            ):
                print(f"[annotation] prepare regest_id={regest_id}")
                preparation_workflow_config = _workflow_config(
                    args=args,
                    condition="workflow_full_ontology",
                    run_id=run_id,
                    model=model,
                    historian_input=historian_input,
                    frozen_annotation=None,
                )

                def checkpoint_annotation_preparation(
                    payload: dict[str, Any],
                ) -> None:
                    writer.write_annotation_attempt_state(
                        regest_id=regest_id,
                        payload=payload,
                    )

                existing_annotation = writer.load_frozen_annotation(
                    regest_id=regest_id
                )
                annotation_attempt_state = writer.load_annotation_attempt_state(
                    regest_id=regest_id
                )
                if (
                    existing_annotation is None
                    and _is_annotation_preparation_retry_exhausted(
                        annotation_attempt_state,
                        max_attempts=args.annotation_max_attempts,
                    )
                ):
                    assert annotation_attempt_state is not None
                    annotation_preparation_error = (
                        _annotation_preparation_exhaustion_error(
                            regest_id=regest_id,
                            attempt_state=annotation_attempt_state,
                            max_attempts=args.annotation_max_attempts,
                        )
                    )
                    print(
                        "[annotation-fail] "
                        f"regest_id={regest_id} "
                        f"error={annotation_preparation_error}"
                    )
                else:
                    try:
                        frozen_annotation = prepare_frozen_annotation(
                            client=client,
                            regest_id=regest_id,
                            workflow_config=preparation_workflow_config,
                            preparation_config=AnnotationPreparationConfig(
                                max_attempts=args.annotation_max_attempts,
                                retry_delay_seconds=args.retry_delay_seconds,
                                poll_interval_seconds=(
                                    args.progress_poll_seconds
                                ),
                                timeout_seconds=args.timeout_seconds,
                            ),
                            existing_snapshot=existing_annotation,
                            checkpoint=checkpoint_annotation_preparation,
                        )
                    except FrozenAnnotationError as exc:
                        annotation_preparation_error = exc
                        print(
                            f"[annotation-fail] "
                            f"regest_id={regest_id} error={exc}"
                        )
                    else:
                        frozen_annotation_paths = (
                            writer.write_frozen_annotation(
                                regest_id=regest_id,
                                payload=frozen_annotation.as_dict(),
                            )
                        )
                        print(
                            f"[annotation-ready] regest_id={regest_id} "
                            f"sha256={frozen_annotation.content_sha256}"
                        )
            for order_position, condition in enumerate(condition_order):
                key = (condition, regest_id)
                existing_row = rows_by_key.get(key)
                if existing_row and _is_resume_complete_result(
                    existing_row,
                    max_attempts=args.max_attempts,
                ):
                    if (
                        existing_row.get("output_truncated") is True
                        and existing_row.get("non_retryable") is not True
                    ):
                        existing_row = dict(existing_row)
                        existing_row["non_retryable"] = True
                        rows_by_key[key] = writer.write_result(
                            _experiment_result_from_row(existing_row)
                        )
                        writer.write_final_outputs(
                            _ordered_rows(
                                ids=ids,
                                conditions=conditions,
                                rows_by_key=rows_by_key,
                            )
                        )
                        rows = _ordered_rows(
                            ids=ids,
                            conditions=conditions,
                            rows_by_key=rows_by_key,
                        )
                    if _is_retry_budget_exhausted(
                        existing_row,
                        max_attempts=args.max_attempts,
                    ):
                        attempt_state = writer.load_attempt_state(
                            condition=condition,
                            regest_id=regest_id,
                        )
                        if (
                            attempt_state is None
                            or attempt_state.get("status") != "failed"
                        ):
                            writer.write_attempt_state(
                                condition=condition,
                                regest_id=regest_id,
                                payload=_terminal_attempt_state_payload(
                                    condition=condition,
                                    regest_id=regest_id,
                                    result=existing_row,
                                ),
                            )
                    status = "already completed"
                    if not bool(existing_row.get("success")):
                        status = (
                            "retry budget exhausted"
                            if _is_retry_budget_exhausted(
                                existing_row,
                                max_attempts=args.max_attempts,
                            )
                            else "terminal non-retryable failure"
                        )
                    print(
                        f"[skip] condition={condition} regest_id={regest_id} "
                        f"{status}"
                    )
                    continue
                if (
                    annotation_preparation_error is not None
                    and condition.startswith("workflow_")
                ):
                    result = _annotation_preparation_failure_result(
                        condition=condition,
                        regest_id=regest_id,
                        model=model,
                        error=annotation_preparation_error,
                        args=args,
                    )
                    result.payload.update(
                        {
                            "provider_profile": profile.manifest_entry(),
                            "condition_order": list(condition_order),
                            "condition_order_position": order_position,
                            "annotation_preparation": {
                                "status": "failed",
                                "max_attempts": args.annotation_max_attempts,
                                "error_message": str(
                                    annotation_preparation_error
                                ),
                                "timing_scope": (
                                    "annotation generation, review, and "
                                    "acceptance; excluded from ontology "
                                    "conditions"
                                ),
                            },
                        }
                    )
                    _attach_input_lineage(result.payload, input_lineage)
                    _attach_recovery_metadata(
                        result.payload,
                        key=key,
                        args=args,
                        output_cap_recovered_archives=(
                            output_cap_recovered_archives
                        ),
                        timeout_recovered_archives=timeout_recovered_archives,
                        timeout_recovery_sources=timeout_recovery_sources,
                        connection_recovered_archives=(
                            connection_recovered_archives
                        ),
                        connection_recovery_sources=(
                            connection_recovery_sources
                        ),
                        local_runtime_recovered_archives=(
                            local_runtime_recovered_archives
                        ),
                        local_runtime_recovery_sources=(
                            local_runtime_recovery_sources
                        ),
                        local_runtime_annotation_attempt_archives=(
                            local_runtime_annotation_attempt_archives
                        ),
                    )
                    rows_by_key[key] = writer.write_result(result)
                    rows = _ordered_rows(
                        ids=ids,
                        conditions=conditions,
                        rows_by_key=rows_by_key,
                    )
                    writer.write_final_outputs(rows)
                    writer.write_attempt_state(
                        condition=condition,
                        regest_id=regest_id,
                        payload={
                            "condition": condition,
                            "regest_id": regest_id,
                            "status": "annotation_failed",
                            "attempt": args.annotation_max_attempts,
                            "success": False,
                            "non_retryable": True,
                            "failure_code": "annotation_generation_failed",
                        },
                    )
                    print(
                        f"[ANNOTATION-FAIL] condition={condition} "
                        f"regest_id={regest_id}"
                    )
                    continue
                writer.write_attempt_state(
                    condition=condition,
                    regest_id=regest_id,
                    payload={
                        "condition": condition,
                        "regest_id": regest_id,
                        "status": "running",
                    },
                )
                print(f"[start] condition={condition} regest_id={regest_id}")

                def checkpoint_failed_attempt(
                    attempt_result: ExperimentResult,
                ) -> None:
                    _attach_input_lineage(
                        attempt_result.payload,
                        input_lineage,
                    )
                    _attach_recovery_metadata(
                        attempt_result.payload,
                        key=key,
                        args=args,
                        output_cap_recovered_archives=(
                            output_cap_recovered_archives
                        ),
                        timeout_recovered_archives=timeout_recovered_archives,
                        timeout_recovery_sources=timeout_recovery_sources,
                        connection_recovered_archives=(
                            connection_recovered_archives
                        ),
                        connection_recovery_sources=(
                            connection_recovery_sources
                        ),
                        local_runtime_recovered_archives=(
                            local_runtime_recovered_archives
                        ),
                        local_runtime_recovery_sources=(
                            local_runtime_recovery_sources
                        ),
                        local_runtime_annotation_attempt_archives=(
                            local_runtime_annotation_attempt_archives
                        ),
                    )
                    rows_by_key[key] = writer.write_result(attempt_result)
                    checkpoint_rows = _ordered_rows(
                        ids=ids,
                        conditions=conditions,
                        rows_by_key=rows_by_key,
                    )
                    writer.write_final_outputs(checkpoint_rows)
                    writer.write_attempt_state(
                        condition=condition,
                        regest_id=regest_id,
                        payload={
                            "condition": condition,
                            "regest_id": regest_id,
                            "status": "retry_pending",
                            "attempt": attempt_result.payload.get("attempt"),
                            "success": False,
                        },
                    )

                result = _run_condition_with_retries(
                    args=args,
                    client=client,
                    rc=rc,
                    regest_id=regest_id,
                    condition=condition,
                    run_id=run_id,
                    model=model,
                    historian_input=historian_input,
                    annotation_guidelines=annotation_guidelines,
                    frozen_regest=frozen_regests.get(regest_id),
                    frozen_annotation=frozen_annotation,
                    previous_result=existing_row,
                    checkpoint_failed_attempt=checkpoint_failed_attempt,
                )
                if frozen_annotation is not None and condition.startswith(
                    "workflow_"
                ):
                    result.payload["frozen_annotation_artifact_paths"] = (
                        frozen_annotation_paths
                    )
                result.payload.update(
                    {
                        "provider_profile": profile.manifest_entry(),
                        "condition_order": list(condition_order),
                        "condition_order_position": order_position,
                        "annotation_preparation": (
                            frozen_annotation.preparation
                            if frozen_annotation is not None
                            else None
                        ),
                    }
                )
                _attach_input_lineage(result.payload, input_lineage)
                _attach_recovery_metadata(
                    result.payload,
                    key=key,
                    args=args,
                    output_cap_recovered_archives=output_cap_recovered_archives,
                    timeout_recovered_archives=timeout_recovered_archives,
                    timeout_recovery_sources=timeout_recovery_sources,
                    connection_recovered_archives=connection_recovered_archives,
                    connection_recovery_sources=connection_recovery_sources,
                    local_runtime_recovered_archives=(
                        local_runtime_recovered_archives
                    ),
                    local_runtime_recovery_sources=local_runtime_recovery_sources,
                    local_runtime_annotation_attempt_archives=(
                        local_runtime_annotation_attempt_archives
                    ),
                )
                rows_by_key[key] = writer.write_result(result)
                rows = _ordered_rows(
                    ids=ids,
                    conditions=conditions,
                    rows_by_key=rows_by_key,
                )
                writer.write_final_outputs(rows)
                writer.write_attempt_state(
                    condition=condition,
                    regest_id=regest_id,
                    payload=_terminal_attempt_state_payload(
                        condition=condition,
                        regest_id=regest_id,
                        result=result.payload,
                    ),
                )
                status = "OK" if result.success else "FAIL"
                print(f"[{status}] condition={condition} regest_id={regest_id}")
    finally:
        client.close()

    output_paths = writer.write_final_outputs(rows)
    print("Completed experiment.")
    for label, path in output_paths.items():
        print(f"- {label}: {path}")
    # > Terminal model failures are measured observations. The process has
    # > completed its work once every scheduled cell has a durable row, even
    # > when one or more rows report an unsuccessful generation.
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare direct Haiu ontology generation with datamodel-workflow modes."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--login", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--ids-file", default="")
    input_group.add_argument(
        "--input-catalog",
        default="",
        help=(
            "Frozen header--sublemma catalogue. Pair publication runs require "
            "AcademicCloud and all three conditions."
        ),
    )
    parser.add_argument(
        "--dmw-input-manifest",
        default="",
        help=(
            "Import manifest written by prepare_header_sublemma_environment.py."
        ),
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--keep-duplicates", action="store_true")
    parser.add_argument(
        "--missing-id-policy",
        choices=("skip", "fail"),
        default="skip",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=DEFAULT_CONDITIONS,
        default=list(DEFAULT_CONDITIONS),
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--output-cap-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for a resumed replay of terminal "
            "output-cap failures. Requires --rerun-output-truncated-at-cap."
        ),
    )
    parser.add_argument(
        "--rerun-output-truncated-at-cap",
        type=int,
        default=None,
        help=(
            "Replay only terminal output-truncated observations whose stage "
            "used this requested and effective cap."
        ),
    )
    parser.add_argument(
        "--provider-timeout-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for replaying exhausted provider-timeout "
            "results that were already selected by --output-cap-recovery-id."
        ),
    )
    parser.add_argument(
        "--connection-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for replaying exhausted connection "
            "failures after the local provider becomes reachable again."
        ),
    )
    parser.add_argument(
        "--local-runtime-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for a corrected local model context, "
            "proxy mapping, or recorded HTTP 502 initial-response replay."
        ),
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--annotation-max-attempts", type=int, default=3)
    parser.add_argument("--progress-poll-seconds", type=float, default=2.0)
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--storage", default=None)
    parser.add_argument(
        "--provenance-file",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help=(
            "Additional frozen input, such as reference_ontology=... or "
            "environment_lock=.... Repeat for each file."
        ),
    )
    parser.add_argument(
        "--publication-run",
        action="store_true",
        help=(
            "Require reference_ontology, retrieval_workspace, and "
            "environment_lock provenance inputs before creating the run."
        ),
    )
    parser.add_argument(
        "--provider-profile",
        choices=tuple(PROVIDER_PROFILES),
        default="academiccloud-qwen36",
        help=(
            "Pinned Qwen 3.6 27B provider environment. The exact provider "
            "model identifier is selected by this profile."
        ),
    )
    parser.add_argument("--base-url-override", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-output-tokens", type=int, default=60_000)
    parser.add_argument(
        "--direct-max-tokens",
        dest="max_output_tokens",
        type=int,
        default=argparse.SUPPRESS,
        help=(
            "Deprecated alias for --max-output-tokens. The cap now applies "
            "to every ontology-generation condition."
        ),
    )
    parser.add_argument(
        "--output-safety-margin-tokens",
        type=int,
        default=4_096,
    )
    parser.add_argument(
        "--ontology-example-limit",
        type=int,
        default=1,
    )
    parser.add_argument("--direct-temperature", type=float, default=0.6)
    parser.add_argument("--direct-top-p", type=float, default=0.95)
    parser.add_argument("--direct-top-k", type=int, default=20)
    parser.add_argument("--direct-min-p", type=float, default=0.0)
    parser.add_argument("--direct-frequency-penalty", type=float, default=0.0)
    parser.add_argument("--direct-presence-penalty", type=float, default=0.0)
    parser.add_argument("--annotation-model", default="")
    parser.add_argument("--annotation-guideline-version", default="1.5.8")
    parser.add_argument("--annotation-min-version", default=None)
    parser.add_argument("--annotation-top-n", type=int, default=5)
    parser.add_argument("--annotation-example-limit", type=int, default=10)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--ontology-context-version", required=True)
    parser.add_argument("--ontology-min-example-version", default="1.0.0")
    parser.add_argument(
        "--ontology-user-input-file", default=str(DEFAULT_PROMPT_FILE)
    )
    parser.add_argument(
        "--annotation-guidelines-file",
        default=str(DEFAULT_ANNOTATION_GUIDELINES_FILE),
    )
    parser.add_argument(
        "--use-only-existing-ontology-terms", action="store_true"
    )
    parser.set_defaults(include_annotations=True)
    parser.add_argument(
        "--include-annotations", dest="include_annotations", action="store_true"
    )
    parser.add_argument(
        "--no-include-annotations",
        dest="include_annotations",
        action="store_false",
    )
    return parser


def _run_condition_with_retries(
    *,
    args: argparse.Namespace,
    client: DatamodelClient,
    rc: HaiuRC,
    regest_id: str,
    condition: str,
    run_id: str,
    model: str,
    historian_input: str,
    annotation_guidelines: str,
    frozen_regest: RegestText | None,
    frozen_annotation: FrozenAnnotation | None,
    previous_result: dict[str, Any] | None = None,
    checkpoint_failed_attempt: (
        Callable[[ExperimentResult], None] | None
    ) = None,
) -> ExperimentResult:
    attempts = max(1, args.max_attempts)
    if previous_result and _is_terminal_result_payload(previous_result):
        normalized_previous = dict(previous_result)
        if normalized_previous.get("output_truncated") is True:
            normalized_previous["non_retryable"] = True
        return _experiment_result_from_row(normalized_previous)
    result: ExperimentResult | None = None
    attempt_history = _recovered_attempt_history(previous_result)
    previous_attempt = max(
        (
            int(item["attempt"])
            for item in attempt_history
            if isinstance(item.get("attempt"), int)
        ),
        default=0,
    )
    total_retry_delay_seconds = _numeric_metadata(
        previous_result,
        "total_retry_delay_seconds",
    )
    previous_elapsed_seconds = _numeric_metadata(
        previous_result,
        "total_elapsed_seconds",
    )
    if previous_attempt >= attempts:
        assert previous_result is not None
        return _experiment_result_from_row(previous_result)

    all_attempts_started = time.perf_counter()
    for attempt in range(previous_attempt + 1, attempts + 1):
        if attempt > 1:
            print(
                f"[retry] condition={condition} regest_id={regest_id} "
                f"attempt={attempt}/{attempts}"
            )
        try:
            result = _run_condition_once(
                args=args,
                client=client,
                rc=rc,
                regest_id=regest_id,
                condition=condition,
                run_id=run_id,
                model=model,
                historian_input=historian_input,
                annotation_guidelines=annotation_guidelines,
                frozen_regest=frozen_regest,
                frozen_annotation=frozen_annotation,
            )
        except FrozenAnnotationError:
            raise
        except Exception as exc:
            result = _unexpected_failure_result(
                condition=condition,
                regest_id=regest_id,
                model=model,
                exc=exc,
                args=args,
            )
        if result.payload.get("output_truncated") is True:
            result.payload["non_retryable"] = True
        attempt_history.append(
            {
                "attempt": attempt,
                "success": result.success,
                "duration_seconds": result.payload.get("duration_seconds"),
                "request_duration_seconds": result.payload.get(
                    "request_duration_seconds"
                ),
                "error_message": result.payload.get("error_message"),
                "generation_budget": result.payload.get("generation_budget"),
                "output_constrained": result.payload.get("output_constrained"),
                "output_truncated": result.payload.get("output_truncated"),
                "publication_eligible": result.payload.get(
                    "publication_eligible"
                ),
            }
        )
        _update_attempt_metadata(
            result=result,
            attempt=attempt,
            attempts=attempts,
            attempt_history=attempt_history,
            total_retry_delay_seconds=total_retry_delay_seconds,
            all_attempts_started=all_attempts_started,
            previous_elapsed_seconds=previous_elapsed_seconds,
        )
        if (
            result.success
            or _is_terminal_result_payload(result.payload)
            or attempt == attempts
        ):
            return result
        if checkpoint_failed_attempt is not None:
            checkpoint_failed_attempt(result)
        error_message = " ".join(
            str(result.payload.get("error_message") or "unknown error").split()
        )
        print(
            f"[attempt-fail] condition={condition} regest_id={regest_id} "
            f"attempt={attempt}/{attempts} error={error_message[:500]}"
        )
        delay = max(0.0, args.retry_delay_seconds)
        print(
            f"[wait] condition={condition} regest_id={regest_id} "
            f"retry_in_seconds={delay:g}"
        )
        time.sleep(delay)
        total_retry_delay_seconds += delay
    if result is None:
        raise RuntimeError("Condition retry loop produced no result.")
    return result


def _is_terminal_result_payload(payload: dict[str, Any]) -> bool:
    """Return whether a result is complete or must never be retried.

    :param payload: Persisted or in-memory condition result fields.
    :return: Whether the runner must preserve the result without another call.
    """
    return (
        bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
    )


def _is_retry_budget_exhausted(
    payload: dict[str, Any],
    *,
    max_attempts: int,
) -> bool:
    """Return whether a preserved failure has used its normal retry budget.

    The result remains an observed provider outcome even when it is not marked
    ``non_retryable``. A future replay must select and archive it through an
    explicit recovery amendment rather than falling through a normal resume.

    :param payload: Persisted condition result fields.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether no ordinary retry attempt remains.
    """
    attempt = payload.get("attempt")
    return isinstance(attempt, int) and attempt >= max(1, max_attempts)


def _terminal_attempt_state_payload(
    *,
    condition: str,
    regest_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a terminal checkpoint from authoritative result metadata.

    A process can stop after preserving a final retry attempt but before its
    lightweight checkpoint is updated. On resume, this payload repairs only
    that stale checkpoint; it never changes the observed raw result.

    :param condition: Stable experiment condition.
    :param regest_id: Datamodel regest identifier.
    :param result: Persisted terminal result metadata.
    :return: Terminal checkpoint payload for the condition and regest pair.
    """
    success = bool(result.get("success"))
    return {
        "condition": condition,
        "regest_id": regest_id,
        "status": "completed" if success else "failed",
        "attempt": result.get("attempt"),
        "success": success,
    }


def _is_resume_complete_result(
    payload: dict[str, Any],
    *,
    max_attempts: int,
) -> bool:
    """Return whether a resumed runner must preserve an existing row.

    :param payload: Persisted condition result fields.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether the row is terminal or has exhausted ordinary retries.
    """
    return _is_terminal_result_payload(payload) or _is_retry_budget_exhausted(
        payload,
        max_attempts=max_attempts,
    )


def _is_annotation_preparation_retry_exhausted(
    attempt_state: dict[str, Any] | None,
    *,
    max_attempts: int,
) -> bool:
    """Return whether a shared annotation already exhausted normal retries.

    Ontology rows do not yet exist when annotation preparation fails. The
    dedicated checkpoint must therefore be honored on resume, or every process
    restart silently grants the prerequisite another full retry budget.

    :param attempt_state: Durable annotation preparation checkpoint.
    :param max_attempts: Annotation retry budget of the resumed run.
    :return: Whether the checkpoint is a terminal exhausted failure.
    """
    if not isinstance(attempt_state, dict):
        return False
    attempt = attempt_state.get("attempt")
    return (
        attempt_state.get("status") == "failed"
        and isinstance(attempt, int)
        and attempt >= max(1, max_attempts)
    )


def _annotation_preparation_exhaustion_error(
    *,
    regest_id: str,
    attempt_state: dict[str, Any],
    max_attempts: int,
) -> FrozenAnnotationError:
    """Restore a stable terminal error from a shared-annotation checkpoint.

    :param regest_id: Datamodel regest identifier.
    :param attempt_state: Exhausted durable annotation checkpoint.
    :param max_attempts: Annotation retry budget of the resumed run.
    :return: Error preserving the final observed preparation failure.
    """
    attempt_history = attempt_state.get("attempt_history")
    last_error = "Annotation preparation exhausted its retry budget."
    if isinstance(attempt_history, list):
        for item in reversed(attempt_history):
            if not isinstance(item, dict):
                continue
            error_message = item.get("error_message")
            if isinstance(error_message, str) and error_message:
                last_error = error_message
                break
    return FrozenAnnotationError(
        f"Annotation preparation failed for {regest_id} after "
        f"{max(1, max_attempts)} attempt(s): {last_error}"
    )


def _workflow_conditions_require_annotation(
    *,
    regest_id: str,
    conditions: tuple[str, ...],
    rows_by_key: dict[tuple[str, str], dict[str, Any]],
    max_attempts: int,
) -> bool:
    """Return whether an unfinished workflow condition needs its shared input.

    Completed, terminal, and retry-exhausted workflow rows retain their
    original immutable annotation evidence. A resume must not contact the
    annotation provider for those rows again, because that spends provider
    capacity without changing a pending ontology observation.

    :param regest_id: Candidate regest under consideration.
    :param conditions: Conditions selected for the current run.
    :param rows_by_key: Durable raw observations keyed by condition and ID.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether at least one workflow condition still requires an
        annotation preparation attempt.
    """
    return any(
        condition.startswith("workflow_")
        and not _is_resume_complete_result(
            rows_by_key.get((condition, regest_id), {}),
            max_attempts=max_attempts,
        )
        for condition in conditions
    )


def _is_output_cap_recovery_candidate(
    payload: dict[str, Any],
    *,
    recovery_cap: int | None,
) -> bool:
    """Identify a terminal length stop caused by one fixed output cap.

    A predictive context budget can also end in a provider length stop, but
    that is an observed capacity outcome rather than a fair replay candidate.
    The recovery protocol therefore requires the failed stage to have used the
    exact configured cap without a context-derived reduction.

    :param payload: Persisted condition result fields.
    :param recovery_cap: Original configured cap selected for recovery.
    :return: Whether this exact terminal result may be replayed by amendment.
    """
    if recovery_cap is None or payload.get("output_truncated") is not True:
        return False
    budgets = payload.get("generation_budget")
    if not isinstance(budgets, dict):
        return False
    for stage in budgets.values():
        if not isinstance(stage, dict):
            continue
        if (
            stage.get("output_truncated") is True
            and stage.get("requested_max_output_tokens") == recovery_cap
            and stage.get("effective_max_output_tokens") == recovery_cap
            and stage.get("output_constrained") is False
        ):
            return True
    return False


def _attach_input_lineage(
    payload: dict[str, Any],
    lineage: dict[str, int | str] | None,
) -> None:
    """Attach pair-source metadata without changing legacy result rows.

    :param payload: Condition result before artifact serialization.
    :param lineage: Pair catalogue identity, or ``None`` for complete regesta.
    :return: ``None``.
    """
    if lineage is not None:
        payload["input_lineage"] = dict(lineage)


def _attach_recovery_metadata(
    payload: dict[str, Any],
    *,
    key: tuple[str, str],
    args: argparse.Namespace,
    output_cap_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    timeout_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    timeout_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    connection_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    connection_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    local_runtime_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    local_runtime_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    local_runtime_annotation_attempt_archives: dict[str, dict[str, Any]],
) -> None:
    """Attach recovery evidence before every durable result checkpoint.

    :param payload: Mutable result metadata that will be persisted.
    :param key: Condition and regest identity of this result.
    :param args: Parsed recovery controls.
    :param output_cap_recovered_archives: Archives created for fixed-cap rows.
    :param timeout_recovered_archives: Archives created for timeout replays.
    :param timeout_recovery_sources: Pre-replay rows used to preserve cap
        recovery provenance.
    :param connection_recovered_archives: Archives created for exhausted
        connection failures.
    :param connection_recovery_sources: Pre-replay connection-failure rows.
    :param local_runtime_recovered_archives: Archives created for local runtime
        configuration and availability failures.
    :param local_runtime_recovery_sources: Pre-replay local runtime failure
        rows used to classify the immutable amendment.
    :param local_runtime_annotation_attempt_archives: Failed shared annotation
        checkpoints reset only for the local-runtime amendment.
    :return: None.
    """
    output_cap_archive_record = output_cap_recovered_archives.get(key)
    if output_cap_archive_record is not None:
        payload["output_cap_recovery"] = {
            "amendment_id": args.output_cap_recovery_id,
            "original_max_output_tokens": args.rerun_output_truncated_at_cap,
            "replacement_max_output_tokens": args.max_output_tokens,
            "superseded_raw_artifact_path": output_cap_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": output_cap_archive_record[
                "canonical_raw_sha256"
            ],
        }
    timeout_archive_record = timeout_recovered_archives.get(key)
    if timeout_archive_record is not None:
        source = timeout_recovery_sources[key]
        output_cap_recovery = source.get("output_cap_recovery")
        if isinstance(output_cap_recovery, dict):
            payload["output_cap_recovery"] = output_cap_recovery
        payload["provider_timeout_recovery"] = {
            "amendment_id": args.provider_timeout_recovery_id,
            "predecessor_output_cap_recovery_id": args.output_cap_recovery_id,
            "superseded_raw_artifact_path": timeout_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": timeout_archive_record[
                "canonical_raw_sha256"
            ],
        }
    connection_archive_record = connection_recovered_archives.get(key)
    if connection_archive_record is not None:
        source = connection_recovery_sources[key]
        payload["connection_recovery"] = {
            "amendment_id": args.connection_recovery_id,
            "predecessor_output_cap_recovery_id": args.output_cap_recovery_id,
            "original_failure_code": source.get("failure_code"),
            "original_attempts": source.get("attempt"),
            "superseded_raw_artifact_path": connection_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": connection_archive_record[
                "canonical_raw_sha256"
            ],
        }
    local_runtime_archive_record = local_runtime_recovered_archives.get(key)
    if local_runtime_archive_record is not None:
        source = local_runtime_recovery_sources[key]
        local_runtime_recovery = {
            "amendment_id": args.local_runtime_recovery_id,
            "original_reasons": sorted(
                _local_runtime_recovery_reasons(
                    source,
                    required_attempts=args.max_attempts,
                )
            ),
            "original_failure_code": source.get("failure_code"),
            "original_attempts": source.get("attempt"),
            "corrected_model_id": LOCAL_RUNTIME_RECOVERY_MODEL_ID,
            "verified_context_window_tokens": (
                LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS
            ),
            "superseded_raw_artifact_path": local_runtime_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": local_runtime_archive_record[
                "canonical_raw_sha256"
            ],
        }
        annotation_archive = local_runtime_annotation_attempt_archives.get(
            key[1]
        )
        if annotation_archive is not None:
            local_runtime_recovery["superseded_annotation_attempt_state"] = (
                annotation_archive
            )
        payload["local_runtime_recovery"] = local_runtime_recovery


def _is_provider_timeout_recovery_candidate(
    payload: dict[str, Any],
    *,
    expected_output_cap_recovery_id: str,
    required_attempts: int,
) -> bool:
    """Select only unreplayed exhausted timeouts from one cap amendment.

    :param payload: Persisted condition result fields.
    :param expected_output_cap_recovery_id: Cap amendment that selected the
        original fixed-cap failure.
    :param required_attempts: Attempts the failed replay exhausted.
    :return: Whether the preserved result may receive its one timeout replay.
    """
    if (
        not expected_output_cap_recovery_id
        or bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
        or payload.get("failure_code") != "ontology_generation_failed"
        or payload.get("attempt") != required_attempts
        or isinstance(payload.get("provider_timeout_recovery"), dict)
    ):
        return False
    output_cap_recovery = payload.get("output_cap_recovery")
    if not isinstance(output_cap_recovery, dict):
        return False
    if (
        output_cap_recovery.get("amendment_id")
        != expected_output_cap_recovery_id
    ):
        return False
    attempt_history = payload.get("attempt_history")
    if (
        not isinstance(attempt_history, list)
        or len(attempt_history) < required_attempts
    ):
        return False
    return all(
        isinstance(item, dict)
        and "timed out" in str(item.get("error_message") or "").lower()
        for item in attempt_history[-required_attempts:]
    )


def _is_connection_recovery_candidate(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> bool:
    """Select only unreplayed exhausted transport failures.

    :param payload: Persisted condition result fields.
    :param required_attempts: Attempts the failed observation exhausted.
    :return: Whether the row may receive its one connection recovery replay.
    """
    if (
        bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
        or payload.get("failure_code") != "ontology_generation_failed"
        or payload.get("attempt") != required_attempts
        or isinstance(payload.get("connection_recovery"), dict)
    ):
        return False
    attempt_history = payload.get("attempt_history")
    if (
        not isinstance(attempt_history, list)
        or len(attempt_history) < required_attempts
    ):
        return False
    return all(
        isinstance(item, dict)
        and "connection error" in str(item.get("error_message") or "").lower()
        for item in attempt_history[-required_attempts:]
    )


def _is_local_runtime_recovery_candidate(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> bool:
    """Select only unreplayed local runtime configuration failures.

    The selection deliberately excludes output-truncated observations. Those
    rows reached a valid context-derived generation budget and remain
    experimental capacity outcomes even when the local model is reloaded.

    :param payload: Persisted condition result fields.
    :param required_attempts: Retry budget that terminal availability failures
        must have exhausted.
    :return: Whether the row may receive the one approved local replay.
    """
    if (
        bool(payload.get("success"))
        or payload.get("output_truncated") is True
        or isinstance(payload.get("local_runtime_recovery"), dict)
    ):
        return False
    return bool(
        _local_runtime_recovery_reasons(
            payload,
            required_attempts=required_attempts,
        )
    )


def _local_runtime_recovery_reasons(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> frozenset[str]:
    """Classify the exact local failures permitted by one amendment.

    :param payload: Persisted condition result fields.
    :param required_attempts: Retry budget for an initial-response outage.
    :return: Stable reason labels supporting the selected replay.
    """
    messages = tuple(_failure_messages(payload))
    reasons: set[str] = set()
    if any(
        LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR in message for message in messages
    ):
        reasons.add("context_admission_rejected")
    if any(LOCAL_RUNTIME_STALE_MODEL_ERROR in message for message in messages):
        reasons.add("stale_proxy_model_identifier")
    attempt_history = payload.get("attempt_history")
    if (
        payload.get("failure_code") == "ontology_generation_failed"
        and payload.get("attempt") == required_attempts
        and isinstance(attempt_history, list)
        and len(attempt_history) >= required_attempts
        and all(
            isinstance(item, dict)
            and LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR
            in str(item.get("error_message") or "").lower()
            for item in attempt_history[-required_attempts:]
        )
    ):
        reasons.add("http_502_initial_response_unavailable")
    return frozenset(reasons)


def _failure_messages(payload: dict[str, Any]) -> Iterator[str]:
    """Yield nested error strings without inspecting prompt or model output.

    :param payload: JSON-like persisted result whose failure fields are read.
    :return: Lowercase failure-message strings.
    """
    for key, value in payload.items():
        normalized_key = key.lower()
        if isinstance(value, str) and (
            "error" in normalized_key or normalized_key in {"message", "reason"}
        ):
            yield value.lower()
        elif isinstance(value, dict):
            yield from _failure_messages(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _failure_messages(item)


def _validate_output_cap_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Reject ambiguous or unsafe output-cap recovery invocations.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If recovery controls do not describe a valid amendment.
    """
    has_recovery_id = bool(args.output_cap_recovery_id)
    has_recovery_cap = args.rerun_output_truncated_at_cap is not None
    if has_recovery_id != has_recovery_cap:
        raise SystemExit(
            "--output-cap-recovery-id and "
            "--rerun-output-truncated-at-cap must be used together."
        )
    if not has_recovery_id:
        return
    recovery_cap = args.rerun_output_truncated_at_cap
    assert recovery_cap is not None
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Output-cap recovery requires --resume and existing raw results."
        )
    if recovery_cap <= 0:
        raise SystemExit("--rerun-output-truncated-at-cap must be positive.")
    if args.max_output_tokens <= recovery_cap:
        raise SystemExit(
            "--max-output-tokens must exceed the recovered output cap."
        )


def _validate_provider_timeout_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require a provider-timeout replay to extend an output-cap amendment.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the replay lacks its immutable recovery chain.
    """
    if not args.provider_timeout_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Provider-timeout recovery requires --resume and existing raw "
            "results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Provider-timeout recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _validate_connection_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require an auditable replay of exhausted connection failures.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the replay lacks its immutable recovery chain.
    """
    if not args.connection_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Connection recovery requires --resume and existing raw results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Connection recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _validate_local_runtime_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require an auditable replay after a corrected local runtime.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the recovery lacks its immutable amendment chain.
    """
    if not args.local_runtime_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Local-runtime recovery requires --resume and existing raw results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Local-runtime recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _update_attempt_metadata(
    *,
    result: ExperimentResult,
    attempt: int,
    attempts: int,
    attempt_history: list[dict[str, Any]],
    total_retry_delay_seconds: float,
    all_attempts_started: float,
    previous_elapsed_seconds: float,
) -> None:
    """Attach retry accounting to the current checkpoint.

    :param result: Current condition result.
    :param attempt: Current one-based attempt number.
    :param attempts: Maximum attempts for this process.
    :param attempt_history: Compact outcomes observed so far.
    :param total_retry_delay_seconds: Completed retry delay.
    :param all_attempts_started: Monotonic start time for the retry loop.
    :param previous_elapsed_seconds: Active elapsed time from earlier processes.
    """
    attempt_duration_seconds = result.payload.get("duration_seconds")
    total_attempt_duration_seconds = round(
        sum(
            float(item["duration_seconds"])
            for item in attempt_history
            if isinstance(item.get("duration_seconds"), int | float)
        ),
        3,
    )
    result.payload.update(
        {
            "attempt": attempt,
            "max_attempts": attempts,
            "attempt_history": attempt_history,
            "attempt_duration_seconds": attempt_duration_seconds,
            "duration_seconds": total_attempt_duration_seconds,
            "duration_measure": (
                "cumulative condition-attempt time excluding runner backoff"
            ),
            "total_attempt_duration_seconds": total_attempt_duration_seconds,
            "ontology_stage_total_attempt_duration_seconds": (
                total_attempt_duration_seconds
            ),
            "total_retry_delay_seconds": round(
                total_retry_delay_seconds,
                3,
            ),
            "total_elapsed_seconds": round(
                previous_elapsed_seconds
                + time.perf_counter()
                - all_attempts_started,
                3,
            ),
        }
    )
    if result.condition.startswith("workflow_") and len(attempt_history) > 1:
        result.payload["ontology_provider_usage_complete"] = False
        result.payload["ontology_provider_usage_scope"] = (
            "final attempt only; failed-attempt provider usage is unavailable"
        )


def _recovered_attempt_history(
    previous_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Copy durable attempt records from an earlier runner process.

    :param previous_result: Raw checkpoint recovered during resume.
    :return: Independent attempt records safe to extend.
    """
    if previous_result is None:
        return []

    raw_history = previous_result.get("attempt_history")
    history = (
        [dict(item) for item in raw_history if isinstance(item, dict)]
        if isinstance(raw_history, list)
        else []
    )
    previous_attempt = previous_result.get("attempt")
    known_attempts = {
        item.get("attempt")
        for item in history
        if isinstance(item.get("attempt"), int)
    }
    if (
        isinstance(previous_attempt, int)
        and previous_attempt > 0
        and previous_attempt not in known_attempts
    ):
        history.append(
            {
                "attempt": previous_attempt,
                "success": bool(previous_result.get("success")),
                "duration_seconds": previous_result.get(
                    "attempt_duration_seconds",
                    previous_result.get("duration_seconds"),
                ),
                "request_duration_seconds": previous_result.get(
                    "request_duration_seconds"
                ),
                "error_message": previous_result.get("error_message"),
            }
        )
    return history


def _numeric_metadata(
    previous_result: dict[str, Any] | None,
    key: str,
) -> float:
    """Read a non-negative numeric checkpoint field.

    :param previous_result: Raw checkpoint recovered during resume.
    :param key: Field to read.
    :return: Non-negative numeric value, or zero when absent.
    """
    value = (previous_result or {}).get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(0.0, float(value))
    return 0.0


def _experiment_result_from_row(row: dict[str, Any]) -> ExperimentResult:
    """Restore a result without persisting normalized artifact-path fields.

    :param row: Recovered normalized or raw row.
    :return: Experiment result suitable for another atomic write.
    """
    payload = {
        key: value
        for key, value in row.items()
        if key
        not in {
            "raw_artifact_path",
            "raw_ttl_artifact_path",
            "raw_yaml_artifact_path",
            "retrieved_ttl_artifact_path",
            "retrieved_yaml_artifact_path",
            "retrieval_snapshot_fidelity",
            "retrieval_sidecars_complete",
            "prompt_artifact_paths",
        }
    }
    return ExperimentResult(
        condition=str(payload.get("condition") or ""),
        regest_id=str(payload.get("regest_id") or ""),
        success=bool(payload.get("success")),
        payload=payload,
    )


def _run_condition_once(
    *,
    args: argparse.Namespace,
    client: DatamodelClient,
    rc: HaiuRC,
    regest_id: str,
    condition: str,
    run_id: str,
    model: str,
    historian_input: str,
    annotation_guidelines: str,
    frozen_regest: RegestText | None,
    frozen_annotation: FrozenAnnotation | None,
) -> ExperimentResult:
    if condition == "haiu_rag_ontologizer":
        condition_started = time.perf_counter()
        try:
            with _condition_wall_clock_timeout(args.timeout_seconds):
                if frozen_regest is None:
                    raise ValueError(
                        "The standalone condition requires the frozen raw "
                        f"regest snapshot for {regest_id}."
                    )
                return run_haiu_rag_condition(
                    regest=frozen_regest,
                    config=DirectRunConfig(
                        model=model,
                        historian_input=historian_input,
                        annotation_guidelines=annotation_guidelines,
                        max_tokens=args.max_output_tokens,
                        temperature=args.direct_temperature,
                        top_p=args.direct_top_p,
                        top_k=args.direct_top_k,
                        min_p=args.direct_min_p,
                        frequency_penalty=args.direct_frequency_penalty,
                        presence_penalty=args.direct_presence_penalty,
                        allow_text_interpretation=False,
                        output_safety_margin_tokens=(
                            args.output_safety_margin_tokens
                        ),
                        require_exact_prompt_tokens=args.publication_run,
                        require_finish_reason=args.publication_run,
                    ),
                    rc=rc,
                )
        except _ConditionWallClockTimeout:
            return _direct_condition_timeout_result(
                regest_id=regest_id,
                model=model,
                timeout_seconds=args.timeout_seconds,
                duration_seconds=time.perf_counter() - condition_started,
                args=args,
            )
    if args.include_annotations:
        if frozen_annotation is None:
            raise FrozenAnnotationError(
                f"Workflow condition {condition} has no frozen annotation."
            )
        verify_frozen_annotation(
            client=client,
            frozen=frozen_annotation,
        )
    condition_started = time.perf_counter()
    try:
        with _condition_wall_clock_timeout(args.timeout_seconds):
            return run_workflow_condition(
                client=client,
                regest_id=regest_id,
                condition=condition,
                config=_workflow_config(
                    args=args,
                    condition=condition,
                    run_id=run_id,
                    model=model,
                    historian_input=historian_input,
                    frozen_annotation=frozen_annotation,
                ),
            )
    except _ConditionWallClockTimeout:
        return _workflow_condition_timeout_result(
            condition=condition,
            regest_id=regest_id,
            model=model,
            timeout_seconds=args.timeout_seconds,
            duration_seconds=time.perf_counter() - condition_started,
            args=args,
        )


@contextmanager
def _condition_wall_clock_timeout(
    timeout_seconds: float,
) -> Iterator[None]:
    """Interrupt synchronous direct work after a total wall-clock limit.

    OpenAI-compatible transport timeouts measure periods of network inactivity,
    so provider heartbeats can keep a stalled request alive indefinitely. The
    runner is a POSIX main-thread CLI, where ``ITIMER_REAL`` provides a hard
    boundary that also interrupts a blocking socket read.

    :param timeout_seconds: Maximum elapsed seconds for the condition.
    :return: Context that raises when the elapsed limit is reached.
    """
    if timeout_seconds <= 0:
        raise ValueError("Condition wall-clock timeout must be positive.")
    if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        raise RuntimeError(
            "Direct condition wall-clock timeouts require POSIX signals."
        )

    def raise_timeout(_signum: int, _frame: FrameType | None) -> None:
        raise _ConditionWallClockTimeout

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.signal(signal.SIGALRM, raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            remaining = max(
                0.000_001,
                previous_timer[0] - (time.monotonic() - started),
            )
            signal.setitimer(
                signal.ITIMER_REAL,
                remaining,
                previous_timer[1],
            )


def _direct_condition_timeout_result(
    *,
    regest_id: str,
    model: str,
    timeout_seconds: float,
    duration_seconds: float,
    args: argparse.Namespace,
) -> ExperimentResult:
    """Record a direct condition stopped by the runner's hard deadline.

    :param regest_id: Datamodel regest identifier.
    :param model: Direct-generation model.
    :param timeout_seconds: Configured total wall-clock limit.
    :param duration_seconds: Observed elapsed time before interruption.
    :return: Failed result eligible for the experiment's outer retry policy.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return ExperimentResult(
        condition="haiu_rag_ontologizer",
        regest_id=regest_id,
        success=False,
        payload={
            "condition": "haiu_rag_ontologizer",
            "regest_id": regest_id,
            "success": False,
            "started_at": timestamp,
            "finished_at": timestamp,
            "duration_seconds": round(duration_seconds, 3),
            "model": model,
            "generation_budget": _unattempted_generation_budget(
                model=model,
                args=args,
            ),
            "output_constrained": False,
            "output_truncated": False,
            "publication_eligible": False,
            "failure_stage": "condition_wall_clock_timeout",
            "wall_clock_timeout_seconds": timeout_seconds,
            "error_message": (
                "Standalone Haiu-RAG condition exceeded the runner wall-clock timeout "
                f"of {timeout_seconds:g} seconds."
            ),
            "turtle_syntax_valid": None,
        },
    )


def _workflow_condition_timeout_result(
    *,
    condition: str,
    regest_id: str,
    model: str,
    timeout_seconds: float,
    duration_seconds: float,
    args: argparse.Namespace,
) -> ExperimentResult:
    """Record a workflow condition stopped by the runner's hard deadline.

    :param condition: Workflow condition that exceeded the deadline.
    :param regest_id: Datamodel regest identifier.
    :param model: Ontology model used by the condition.
    :param timeout_seconds: Configured total wall-clock limit.
    :param duration_seconds: Observed elapsed time before interruption.
    :return: Failed result eligible for the normal retry policy.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return ExperimentResult(
        condition=condition,
        regest_id=regest_id,
        success=False,
        payload={
            "condition": condition,
            "regest_id": regest_id,
            "success": False,
            "started_at": timestamp,
            "finished_at": timestamp,
            "duration_seconds": round(duration_seconds, 3),
            "model": model,
            "generation_budget": _unattempted_generation_budget(
                model=model,
                args=args,
            ),
            "output_constrained": False,
            "output_truncated": False,
            "publication_eligible": False,
            "failure_stage": "condition_wall_clock_timeout",
            "wall_clock_timeout_seconds": timeout_seconds,
            "error_message": (
                "Workflow condition exceeded the runner wall-clock timeout "
                f"of {timeout_seconds:g} seconds."
            ),
            "turtle_syntax_valid": None,
        },
    )


def _annotation_preparation_failure_result(
    *,
    condition: str,
    regest_id: str,
    model: str,
    error: FrozenAnnotationError,
    args: argparse.Namespace,
) -> ExperimentResult:
    """Record an exhausted shared-annotation failure for one DMW condition.

    The annotation is a prerequisite shared by both workflow conditions. Once
    its configured retry budget is exhausted, both conditions receive durable
    terminal rows while an independent standalone condition may continue.

    :param condition: Workflow condition blocked by the missing annotation.
    :param regest_id: Datamodel regest identifier.
    :param model: Ontology-generation model selected for the run.
    :param error: Exhausted annotation preparation error.
    :param args: Parsed runner settings used for stable budget metadata.
    :return: Terminal failed result with no ontology-provider invocation.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return ExperimentResult(
        condition=condition,
        regest_id=regest_id,
        success=False,
        payload={
            "condition": condition,
            "regest_id": regest_id,
            "success": False,
            "started_at": timestamp,
            "finished_at": timestamp,
            "duration_seconds": 0.0,
            "model": model,
            "generation_budget": _unattempted_generation_budget(
                model=model,
                args=args,
            ),
            "output_constrained": False,
            "output_truncated": False,
            "non_retryable": True,
            "publication_eligible": False,
            "failure_stage": "annotation_preparation",
            "failure_code": "annotation_generation_failed",
            "error_message": str(error),
            "turtle_syntax_valid": None,
        },
    )


def _unexpected_failure_result(
    *,
    condition: str,
    regest_id: str,
    model: str,
    exc: Exception,
    args: argparse.Namespace,
) -> ExperimentResult:
    timestamp = datetime.now(timezone.utc).isoformat()
    return ExperimentResult(
        condition=condition,
        regest_id=regest_id,
        success=False,
        payload={
            "condition": condition,
            "regest_id": regest_id,
            "success": False,
            "started_at": timestamp,
            "finished_at": timestamp,
            "duration_seconds": 0.0,
            "model": model,
            "generation_budget": _unattempted_generation_budget(
                model=model,
                args=args,
            ),
            "output_constrained": False,
            "output_truncated": False,
            "publication_eligible": False,
            "error_message": f"{type(exc).__name__}: {exc}",
            "turtle_syntax_valid": None,
        },
    )


def _unattempted_generation_budget(
    *,
    model: str,
    args: argparse.Namespace,
) -> dict[str, dict[str, object]]:
    """Build stable budget records when no provider stage was reached.

    :param model: Provider model alias.
    :param args: Parsed experiment configuration.
    :return: Stage-keyed unattempted budget records.
    """
    try:
        context_window_tokens = llm_spec(model).context_token_limit
    except ValueError:
        context_window_tokens = None
    record: dict[str, object] = {
        "requested_max_output_tokens": args.max_output_tokens,
        "predicted_max_output_tokens": None,
        "effective_max_output_tokens": None,
        "measured_prompt_tokens": None,
        "prompt_token_source": None,
        "provider_prompt_tokens": None,
        "context_window_tokens": context_window_tokens,
        "safety_margin_tokens": args.output_safety_margin_tokens,
        "output_constrained": None,
        "finish_reason": None,
        "output_truncated": None,
        "adjustments": [],
        "tokenizer_repo": None,
        "tokenizer_revision": None,
        "attempted": False,
    }
    return {
        "stage1": dict(record),
        "stage2": dict(record),
    }


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("condition") or ""), str(row.get("regest_id") or "")


def _ordered_rows(
    *,
    ids: list[str],
    conditions: tuple[str, ...],
    rows_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        rows_by_key[(condition, regest_id)]
        for regest_id in ids
        for condition in conditions
        if (condition, regest_id) in rows_by_key
    ]


def _run_manifest(
    *,
    args: argparse.Namespace,
    conditions: tuple[str, ...],
    ids: list[str],
    run_id: str,
    model: str,
    historian_input: str,
    annotation_guidelines: str,
    raw_regest_snapshot: dict[str, Any] | None,
    rc: HaiuRC,
    workflow_model_provenance: dict[str, dict[str, Any]],
    profile: ProviderProfile,
    provenance: dict[str, Any],
    haiu_distribution: dict[str, Any],
    input_population: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the immutable identity used to guard resumed observations.

    :param args: Parsed command-line configuration.
    :param conditions: Conditions in execution order.
    :param ids: Selected regest IDs in execution order.
    :param run_id: Stable experiment identifier.
    :param model: Resolved ontology and direct-condition model.
    :param historian_input: Exact ontology prompt supplied by the historian.
    :param annotation_guidelines: Exact curated annotation guideline input.
    :param raw_regest_snapshot: Frozen standalone raw-input snapshot metadata.
    :param rc: Resolved Haiu runtime configuration.
    :param workflow_model_provenance: Effective DMW model catalog entries.
    :param profile: Pinned chat and embedding provider profile.
    :param provenance: Frozen input and environment snapshot manifest.
    :param haiu_distribution: Imported Haiu package and distribution identity.
    :param input_population: Optional pair catalogue identity and lineage.
    :return: JSON-friendly identity without credentials or private host data.
    """
    annotation_model = model
    direct_spec = llm_spec(model).with_sampling(
        max_tokens=args.max_output_tokens,
        temperature=args.direct_temperature,
        top_p=args.direct_top_p,
        top_k=args.direct_top_k,
        min_p=args.direct_min_p,
        frequency_penalty=args.direct_frequency_penalty,
        presence_penalty=args.direct_presence_penalty,
    )
    manifest = {
        "schema_version": 5,
        "run_id": run_id,
        "conditions": list(conditions),
        "regest_ids": ids,
        "models": {
            "standalone_and_ontology": model,
            "annotation": annotation_model,
        },
        "provider_profile": profile.manifest_entry(),
        "haiu_distribution": haiu_distribution,
        "provenance": provenance,
        "raw_regest_snapshot": raw_regest_snapshot,
        "direct_generation": {
            "sampling": direct_spec.to_kws_flattened(),
            "max_output_tokens": args.max_output_tokens,
            "output_safety_margin_tokens": (args.output_safety_margin_tokens),
            "require_exact_prompt_tokens": args.publication_run,
            "require_finish_reason": args.publication_run,
            "provider_endpoint_sha256": hashlib.sha256(
                rc.client.base_url.encode("utf-8")
            ).hexdigest(),
            "embedding_endpoint_sha256": hashlib.sha256(
                str(rc.client.embedding_base_url or rc.client.base_url).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "provider_credential_configured": bool(rc.client.api_key),
            "provider_timeout_seconds": rc.client.timeout_llm,
            "provider_attempts": rc.client.max_retries,
            "openai_sdk_retries": rc.client.max_retries_openai,
        },
        "annotation": {
            "guideline_version": args.annotation_guideline_version,
            "min_version": args.annotation_min_version,
            "top_n": args.annotation_top_n,
            "example_limit": args.annotation_example_limit,
            "preparation_protocol": (
                "generate_or_review_accept_freeze_before_ontology"
            ),
            "max_attempts_per_process": args.annotation_max_attempts,
            "provider_usage_complete": False,
            "guideline_sha256": hashlib.sha256(
                annotation_guidelines.encode("utf-8")
            ).hexdigest(),
        },
        "ontology": {
            "context_version": args.ontology_context_version,
            "min_example_version": args.ontology_min_example_version,
            "example_limit": args.ontology_example_limit,
            "max_output_tokens": args.max_output_tokens,
            "output_safety_margin_tokens": (args.output_safety_margin_tokens),
            "require_exact_prompt_tokens": args.publication_run,
            "require_finish_reason": args.publication_run,
            "historian_input_sha256": hashlib.sha256(
                historian_input.encode("utf-8")
            ).hexdigest(),
            "embedding_model": rc.rag.haiu_settings.model_embed,
            "include_annotations": args.include_annotations,
            "use_only_existing_ontology_terms": (
                args.use_only_existing_ontology_terms
            ),
            "allow_text_interpretation": False,
        },
        "workflow": {
            "branch": args.branch,
            "existing_data_policy": "reuse",
            "require_existing_annotation": True,
            "shared_frozen_annotation": any(
                condition.startswith("workflow_") for condition in conditions
            )
            and args.include_annotations,
            "primary_duration_measure": (
                "cumulative ontology-stage attempt time excluding runner backoff"
            ),
            "model_provenance": workflow_model_provenance,
        },
    }
    if input_population is not None:
        manifest["schema_version"] = 6
        manifest["input_population"] = input_population
    return manifest


def _validate_output_cap_recovery_base_manifest(
    *,
    manifest: dict[str, Any],
    args: argparse.Namespace,
    conditions: tuple[str, ...],
    ids: list[str],
    run_id: str,
    model: str,
    historian_input: str,
    annotation_guidelines: str,
    raw_regest_snapshot: dict[str, Any] | None,
    rc: HaiuRC,
    profile: ProviderProfile,
    haiu_distribution: dict[str, Any],
    recovery_cap: int,
    input_population: dict[str, Any] | None = None,
) -> None:
    """Prove that a cap amendment changes no baseline experiment setting.

    :param manifest: Existing immutable run identity.
    :param args: Requested resumed command configuration.
    :param conditions: Canonical experiment conditions.
    :param ids: Frozen regest population.
    :param run_id: Existing stable run identifier.
    :param model: Pinned ontology model.
    :param historian_input: Exact frozen ontology instruction.
    :param annotation_guidelines: Exact frozen annotation guideline.
    :param raw_regest_snapshot: Frozen standalone-input evidence.
    :param rc: Resolved Haiu runtime configuration.
    :param profile: Pinned provider profile.
    :param haiu_distribution: Current installed Haiu identity.
    :param recovery_cap: Original output cap recorded by the base run.
    :param input_population: Optional pair catalogue identity and lineage.
    :return: None.
    :raises ValueError: If any baseline setting differs from the base run.
    """
    provenance = manifest.get("provenance")
    workflow = manifest.get("workflow")
    if not isinstance(provenance, dict) or not isinstance(workflow, dict):
        raise ValueError(
            "Output-cap recovery requires a complete base run manifest."
        )
    workflow_model_provenance = workflow.get("model_provenance")
    if not isinstance(workflow_model_provenance, dict):
        raise ValueError(
            "Output-cap recovery base manifest has no workflow model "
            "provenance."
        )
    baseline_args = argparse.Namespace(**vars(args))
    baseline_args.max_output_tokens = recovery_cap
    expected = _run_manifest(
        args=baseline_args,
        conditions=conditions,
        ids=ids,
        run_id=run_id,
        model=model,
        historian_input=historian_input,
        annotation_guidelines=annotation_guidelines,
        raw_regest_snapshot=raw_regest_snapshot,
        rc=rc,
        profile=profile,
        provenance=provenance,
        haiu_distribution=haiu_distribution,
        workflow_model_provenance=workflow_model_provenance,
        input_population=input_population,
    )
    if manifest != expected:
        raise ValueError(
            "Output-cap recovery may only change the configured output cap; "
            "the requested command differs from the immutable base run."
        )


def _output_cap_recovery_amendment(
    *,
    amendment_id: str,
    base_manifest_path: Path,
    base_manifest: dict[str, Any],
    recovery_cap: int,
    replacement_cap: int,
    workflow_model_provenance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Describe the explicit replay protocol for fixed-cap length failures.

    :param amendment_id: Stable recovery protocol identifier.
    :param base_manifest_path: Immutable original run-manifest path.
    :param base_manifest: Parsed original run-manifest payload.
    :param recovery_cap: Cap that selected terminal replay candidates.
    :param replacement_cap: Larger cap applied to replayed and future rows.
    :param workflow_model_provenance: DMW catalog observed after the cap change.
    :return: Portable amendment evidence with no credentials or endpoints.
    """
    base_manifest_bytes = json.dumps(
        base_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "amendment_id": amendment_id,
        "kind": "output_cap_recovery",
        "base_run_manifest_path": base_manifest_path.name,
        "base_run_manifest_sha256": hashlib.sha256(
            base_manifest_bytes
        ).hexdigest(),
        "selection": {
            "terminal_output_truncated": True,
            "stage_requested_max_output_tokens": recovery_cap,
            "stage_effective_max_output_tokens": recovery_cap,
            "stage_output_constrained": False,
        },
        "recovery": {
            "original_max_output_tokens": recovery_cap,
            "replacement_max_output_tokens": replacement_cap,
            "priority": "replay selected regests before untouched IDs",
            "original_evidence": "archived under superseded/<amendment_id>/",
            "context_window_policy": (
                "predictively constrained and context-window outcomes remain "
                "terminal"
            ),
        },
        "workflow_model_provenance_after_cap_change": (
            workflow_model_provenance
        ),
    }


def _provider_timeout_recovery_amendment(
    *,
    amendment_id: str,
    base_manifest_path: Path,
    base_manifest: dict[str, Any],
    output_cap_recovery_id: str,
    max_attempts: int,
) -> dict[str, Any]:
    """Describe one auditable replay after provider timeouts.

    :param amendment_id: Stable timeout-replay amendment name.
    :param base_manifest_path: Immutable original run-manifest path.
    :param base_manifest: Parsed original run-manifest payload.
    :param output_cap_recovery_id: Preceding cap amendment that selected the
        fixed-cap result.
    :param max_attempts: Timeout attempts that a selected replay exhausted.
    :return: Portable amendment evidence with no credentials or endpoints.
    """
    base_manifest_bytes = json.dumps(
        base_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "amendment_id": amendment_id,
        "kind": "provider_timeout_recovery",
        "base_run_manifest_path": base_manifest_path.name,
        "base_run_manifest_sha256": hashlib.sha256(
            base_manifest_bytes
        ).hexdigest(),
        "depends_on_amendment": output_cap_recovery_id,
        "selection": {
            "predecessor_output_cap_recovery_id": output_cap_recovery_id,
            "success": False,
            "failure_code": "ontology_generation_failed",
            "output_truncated": False,
            "attempts_exhausted": max_attempts,
            "all_attempt_errors_include": "timed out",
        },
        "recovery": {
            "priority": "replay selected provider timeouts before remaining IDs",
            "original_evidence": "archived under superseded/<amendment_id>/",
            "context_window_policy": (
                "predictively constrained and context-window outcomes remain "
                "terminal"
            ),
        },
    }


def _connection_recovery_amendment(
    *,
    amendment_id: str,
    base_manifest_path: Path,
    base_manifest: dict[str, Any],
    output_cap_recovery_id: str,
    max_attempts: int,
) -> dict[str, Any]:
    """Describe one auditable replay after local transport unavailability.

    :param amendment_id: Stable connection-replay amendment name.
    :param base_manifest_path: Immutable original run-manifest path.
    :param base_manifest: Parsed original run-manifest payload.
    :param output_cap_recovery_id: Earlier amendment that fixed the output cap.
    :param max_attempts: Connection attempts that a selected row exhausted.
    :return: Portable amendment evidence with no credentials or endpoints.
    """
    base_manifest_bytes = json.dumps(
        base_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "amendment_id": amendment_id,
        "kind": "connection_recovery",
        "base_run_manifest_path": base_manifest_path.name,
        "base_run_manifest_sha256": hashlib.sha256(
            base_manifest_bytes
        ).hexdigest(),
        "depends_on_amendment": output_cap_recovery_id,
        "selection": {
            "success": False,
            "failure_code": "ontology_generation_failed",
            "output_truncated": False,
            "attempts_exhausted": max_attempts,
            "all_attempt_errors_include": "connection error",
            "exclude_existing_connection_recovery": True,
        },
        "recovery": {
            "priority": (
                "replay selected connection failures before remaining IDs"
            ),
            "original_evidence": "archived under superseded/<amendment_id>/",
            "context_window_policy": (
                "predictively constrained and context-window outcomes remain "
                "terminal"
            ),
        },
    }


def _local_runtime_recovery_amendment(
    *,
    amendment_id: str,
    base_manifest_path: Path,
    base_manifest: dict[str, Any],
    output_cap_recovery_id: str,
    max_attempts: int,
) -> dict[str, Any]:
    """Describe one replay after a verified local LM Studio correction.

    :param amendment_id: Stable local-runtime recovery protocol identifier.
    :param base_manifest_path: Immutable original run-manifest path.
    :param base_manifest: Parsed original run-manifest payload.
    :param output_cap_recovery_id: Earlier amendment anchoring the immutable
        resumed run configuration.
    :param max_attempts: Exhausted attempt count for HTTP 502 replays.
    :return: Portable amendment evidence with no credentials or endpoints.
    """
    base_manifest_bytes = json.dumps(
        base_manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "amendment_id": amendment_id,
        "kind": "local_runtime_recovery",
        "base_run_manifest_path": base_manifest_path.name,
        "base_run_manifest_sha256": hashlib.sha256(
            base_manifest_bytes
        ).hexdigest(),
        "depends_on_amendment": output_cap_recovery_id,
        "selection": {
            "success": False,
            "output_truncated": False,
            "any_failure_message_includes": [
                LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR,
                LOCAL_RUNTIME_STALE_MODEL_ERROR,
            ],
            "or_terminal_initial_response_failure": {
                "failure_code": "ontology_generation_failed",
                "attempts_exhausted": max_attempts,
                "all_attempt_errors_include": (
                    LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR
                ),
                "backend_observation": "HTTP 502 Bad Gateway",
            },
            "exclude_existing_local_runtime_recovery": True,
        },
        "recovery": {
            "priority": "replay selected runtime failures before remaining IDs",
            "original_evidence": "archived under superseded/<amendment_id>/",
            "corrected_model_id": LOCAL_RUNTIME_RECOVERY_MODEL_ID,
            "verified_context_window_tokens": (
                LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS
            ),
            "annotation_retry_state": (
                "archive and reset only exhausted failed shared annotation "
                "checkpoints without a frozen annotation"
            ),
            "context_window_policy": (
                "predictively constrained and context-window outcomes remain "
                "terminal"
            ),
        },
    }


def _selected_model_entry(
    catalog: dict[str, Any],
    *,
    model_name: str,
) -> dict[str, Any]:
    """Return stable DMW provenance for one required model.

    :param catalog: Response from DMW's model catalog.
    :param model_name: Exact configured model handle.
    :return: Non-secret capability and generation settings.
    :raises ValueError: If the configured model is not available.
    """
    models = catalog.get("models")
    if not isinstance(models, list):
        raise ValueError("DMW model catalog does not contain a model list.")
    for entry in models:
        if (
            isinstance(entry, dict)
            and str(entry.get("input_name") or "") == model_name
        ):
            return {
                key: entry.get(key)
                for key in (
                    "input_name",
                    "provider",
                    "provider_model_id",
                    "context_window_tokens",
                    "max_output_tokens",
                    "capability_source",
                    "generation_params",
                )
            }
    use_case = str(catalog.get("use_case") or "requested")
    raise ValueError(
        f"Model '{model_name}' is unavailable in DMW's {use_case} catalog."
    )


def _load_requested_input_catalog(
    args: argparse.Namespace,
) -> HeaderSublemmaCatalog | None:
    """Load the optional pair catalogue selected on the command line.

    :param args: Parsed runner arguments.
    :return: Verified pair catalogue, or ``None`` for legacy ID-file mode.
    :raises SystemExit: If the selected catalogue is invalid.
    """
    if not args.input_catalog:
        return None
    try:
        return load_header_sublemma_catalog(Path(args.input_catalog))
    except ValueError as exc:
        raise SystemExit(f"Cannot load --input-catalog: {exc}") from exc


def _load_requested_dmw_input_manifest(
    args: argparse.Namespace,
    *,
    input_catalog: HeaderSublemmaCatalog | None,
) -> DmwPairImportManifest | None:
    """Load DMW import evidence only when pair mode is selected.

    :param args: Parsed runner arguments.
    :param input_catalog: Optional verified pair population.
    :return: Verified DMW import evidence, or ``None`` for legacy mode.
    :raises SystemExit: If pair evidence is missing, misplaced, or invalid.
    """
    if input_catalog is None:
        if args.dmw_input_manifest:
            raise SystemExit(
                "--dmw-input-manifest is valid only with --input-catalog."
            )
        return None
    if not args.dmw_input_manifest:
        raise SystemExit(
            "--input-catalog requires --dmw-input-manifest from the isolated "
            "DMW preparation command."
        )
    try:
        return load_dmw_pair_import_manifest(
            Path(args.dmw_input_manifest),
            catalog=input_catalog,
        )
    except ValueError as exc:
        raise SystemExit(f"Cannot load --dmw-input-manifest: {exc}") from exc


def _validate_input_protocol(
    *,
    args: argparse.Namespace,
    profile: ProviderProfile,
    input_catalog: HeaderSublemmaCatalog | None,
    dmw_input_manifest: DmwPairImportManifest | None,
) -> None:
    """Enforce the preregistered boundary for pair publication runs.

    :param args: Parsed runner arguments.
    :param profile: Selected provider profile.
    :param input_catalog: Optional pair population.
    :param dmw_input_manifest: Optional prepared DMW identity.
    :return: ``None`` after validation.
    :raises SystemExit: If pair mode would deviate from the planned protocol.
    """
    if input_catalog is None:
        return
    if dmw_input_manifest is None:
        raise SystemExit("Pair input mode has no verified DMW import manifest.")
    if args.keep_duplicates:
        raise SystemExit("Pair input mode does not support --keep-duplicates.")
    target_branch = dmw_input_manifest.target_branch.get("branch_slug")
    if target_branch != args.branch:
        raise SystemExit(
            "DMW pair import manifest branch differs from --branch."
        )
    if (
        dmw_input_manifest.ontology_context_version
        != args.ontology_context_version
    ):
        raise SystemExit(
            "DMW pair import manifest ontology version differs from "
            "--ontology-context-version."
        )
    if not args.publication_run:
        return
    if profile.name != "academiccloud-qwen36":
        raise SystemExit(
            "Publication header--sublemma replication is AcademicCloud-only."
        )
    if set(args.conditions) != set(DEFAULT_CONDITIONS):
        raise SystemExit(
            "Publication header--sublemma replication requires all three "
            "conditions."
        )
    if args.missing_id_policy != "fail":
        raise SystemExit(
            "Publication header--sublemma replication requires "
            "--missing-id-policy fail."
        )


def _validate_pair_dmw_preflight(
    *,
    client: DatamodelClient,
    args: argparse.Namespace,
    catalog: HeaderSublemmaCatalog,
    import_manifest: DmwPairImportManifest,
    selected_ids: list[str],
) -> dict[str, RegestText]:
    """Prove that live DMW serves the prepared branch and exact pair texts.

    :param client: Authenticated DMW client.
    :param args: Parsed runner arguments.
    :param catalog: Frozen pair population.
    :param import_manifest: Prepared storage evidence.
    :param selected_ids: Inputs selected for this run or smoke run.
    :return: Exact verified texts keyed by synthetic ID.
    :raises SystemExit: If the live service differs from frozen preparation.
    """
    expected_branch = import_manifest.target_branch
    branch_records = client.get_ontology_branches()
    matching_branches = [
        branch
        for branch in branch_records
        if branch.get("branch_slug") == args.branch
    ]
    if len(matching_branches) != 1:
        raise SystemExit(
            f"Live DMW does not expose exactly one branch named {args.branch!r}."
        )
    live_branch = matching_branches[0]
    branch_fields = (
        "branch_slug",
        "branch_name",
        "github_branch",
        "github_tag_scope",
        "annotation_collection",
        "ontology_collection",
        "latest_version",
        "status",
        "creator_id",
    )
    if any(
        live_branch.get(field) != expected_branch.get(field)
        for field in branch_fields
    ):
        raise SystemExit(
            "Live DMW branch identity differs from the pair import manifest."
        )

    records_by_id = catalog.by_id
    verified: dict[str, RegestText] = {}
    for input_unit_id in selected_ids:
        unit = records_by_id.get(input_unit_id)
        if unit is None:
            raise SystemExit(
                f"Selected pair input is absent from its catalogue: {input_unit_id}."
            )
        expected = unit.as_regest_text()
        observed = client.get_regest_text(input_unit_id)
        if observed != expected:
            raise SystemExit(
                "Live DMW pair text differs from the frozen catalogue: "
                f"{input_unit_id}."
            )
        verified[input_unit_id] = expected
    return verified


def _pair_regest_fetcher(
    *,
    verified_regests: dict[str, RegestText],
) -> Callable[[str], RegestText]:
    """Build a local-only fetcher for already verified pair input text.

    :param verified_regests: Preflight catalogue texts keyed by synthetic ID.
    :return: Fetch function accepted by :class:`ArtifactWriter`.
    """

    def fetch(input_unit_id: str) -> RegestText:
        try:
            return verified_regests[input_unit_id]
        except KeyError as exc:
            raise ValueError(
                f"Pair input was not verified before freezing: {input_unit_id}."
            ) from exc

    return fetch


def _validate_profile_model_overrides(
    *, args: argparse.Namespace, profile: ProviderProfile
) -> None:
    """Reject ad-hoc model overrides that would break the matched protocol.

    :param args: Parsed command-line options.
    :param profile: Pinned provider model mapping.
    :return: None.
    :raises SystemExit: If an override disagrees with the selected profile.
    """
    requested = [
        ("--model", args.model),
        ("--annotation-model", args.annotation_model),
    ]
    mismatches = [
        flag
        for flag, value in requested
        if value and value != profile.provider_generation_model
    ]
    if mismatches:
        raise SystemExit(
            "The publication protocol pins every generation role to "
            f"'{profile.provider_generation_model}' via "
            f"--provider-profile {profile.name}; do not override "
            + ", ".join(mismatches)
            + "."
        )
    if args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive.")
    if args.output_safety_margin_tokens < 0:
        raise SystemExit("--output-safety-margin-tokens cannot be negative.")
    if args.ontology_example_limit < 0:
        raise SystemExit("--ontology-example-limit cannot be negative.")


def _configure_provider_profile(
    *, rc: HaiuRC, profile: ProviderProfile
) -> None:
    """Apply and validate the protocol's chat/embedding model split.

    :param rc: Resolved Haiu runtime configuration.
    :param profile: Pinned generation provider profile.
    :return: None.
    :raises SystemExit: If retrieval would stop using AcademicCloud Qwen embeds.
    """
    if rc.rag.haiu_settings.model_embed != "qwen3-embedding-4b":
        raise SystemExit(
            "The publication protocol requires "
            "HAIU_MODEL_EMBED=qwen3-embedding-4b; got "
            f"'{rc.rag.haiu_settings.model_embed}'."
        )
    rc.client.model_embed = "qwen3-embedding-4b"
    rc.client.model_llm = profile.provider_generation_model
    rc.rag.haiu_settings.model_llm = profile.provider_generation_model


def _installed_haiu_distribution_provenance() -> dict[str, Any]:
    """Describe the Haiu distribution imported by this runner process.

    The publication runner records both the package location used by Python and
    the installed distribution metadata.  A lock file alone cannot prove that
    a live process did not import an editable checkout.

    :return: Non-secret imported-package and installed-distribution evidence.
    :raises SystemExit: If Python cannot resolve an installed Haiu distribution.
    """
    try:
        distribution = importlib_metadata.distribution("haiu")
    except importlib_metadata.PackageNotFoundError as exc:
        raise SystemExit(
            "The experiment process has no installed haiu distribution. "
            "Install the published release before running it."
        ) from exc

    direct_url: dict[str, Any] = {}
    raw_direct_url = distribution.read_text("direct_url.json")
    if raw_direct_url:
        try:
            parsed_direct_url = json.loads(raw_direct_url)
        except json.JSONDecodeError:
            parsed_direct_url = None
        if isinstance(parsed_direct_url, dict):
            direct_url = parsed_direct_url
    record = distribution.read_text("RECORD") or ""
    archive_info = direct_url.get("archive_info")
    archive_info = archive_info if isinstance(archive_info, dict) else {}
    dir_info = direct_url.get("dir_info")
    dir_info = dir_info if isinstance(dir_info, dict) else {}
    vcs_info = direct_url.get("vcs_info")
    vcs_info = vcs_info if isinstance(vcs_info, dict) else {}
    package_path = Path(haiu.__file__ or "").resolve()
    return {
        "distribution_name": distribution.metadata["Name"],
        "version": distribution.version,
        "imported_package_path": str(package_path),
        "distribution_root": str(
            Path(str(distribution.locate_file("."))).resolve()
        ),
        "distribution_record_sha256": hashlib.sha256(
            record.encode("utf-8")
        ).hexdigest(),
        "direct_url": direct_url.get("url"),
        "distribution_archive_hash": archive_info.get("hash"),
        "editable": bool(dir_info.get("editable")),
        "vcs": vcs_info.get("vcs"),
        "requested_revision": vcs_info.get("requested_revision"),
        "commit_id": vcs_info.get("commit_id"),
    }


def _require_published_haiu_distribution(provenance: dict[str, Any]) -> None:
    """Reject a clean-run environment outside the frozen Haiu release source.

    :param provenance: Installed-distribution evidence from this process.
    :return: None.
    :raises SystemExit: If the package is editable, has an unapproved VCS
        identity, has the wrong version, or lacks a recorded archive hash.
    """
    if provenance.get("version") != PUBLISHED_HAIU_VERSION:
        raise SystemExit(
            "--publication-run requires haiu=="
            f"{PUBLISHED_HAIU_VERSION}; imported {provenance.get('version')!r}."
        )
    if provenance.get("editable"):
        raise SystemExit(
            "--publication-run requires a non-editable Haiu installation."
        )
    if provenance.get("vcs"):
        if (
            provenance.get("vcs") == "git"
            and provenance.get("direct_url") == APPROVED_HAIU_VCS_URL
            and provenance.get("requested_revision")
            == APPROVED_HAIU_VCS_REVISION
            and _is_git_commit_id(provenance.get("commit_id"))
        ):
            return
        raise SystemExit(
            "--publication-run requires the approved Haiu Git release source "
            f"{APPROVED_HAIU_VCS_REVISION} resolved to a full Git commit."
        )
    direct_url = provenance.get("direct_url")
    archive_hash = provenance.get("distribution_archive_hash")
    if not (
        isinstance(direct_url, str)
        and direct_url.startswith("https://")
        and direct_url.endswith(".whl")
        and isinstance(archive_hash, str)
        and archive_hash.startswith("sha256=")
    ):
        raise SystemExit(
            "--publication-run requires a hash-recorded HTTPS wheel or the "
            "approved Haiu Git release installation."
        )


def _condition_order_for_index(
    *, conditions: tuple[str, ...], index: int
) -> tuple[str, ...]:
    """Rotate the three publication conditions deterministically per regest.

    :param conditions: Canonical condition registry order.
    :param index: Zero-based position in the frozen available-ID list.
    :return: Per-regest execution order.
    """
    if not conditions:
        return ()
    offset = index % len(conditions)
    return conditions[offset:] + conditions[:offset]


def _provenance_files(args: argparse.Namespace) -> dict[str, Path]:
    """Parse extra immutable inputs requested for one experiment run.

    :param args: Parsed command-line options.
    :return: Stable label-to-path mapping for artifact freezing.
    :raises SystemExit: If labels are malformed, duplicate, or incomplete.
    """
    files: dict[str, Path] = {}
    for entry in args.provenance_file:
        label, separator, raw_path = entry.partition("=")
        normalized_label = label.strip()
        if not separator or not normalized_label or not raw_path.strip():
            raise SystemExit(
                "--provenance-file values must use NAME=PATH syntax."
            )
        if normalized_label in files:
            raise SystemExit(f"Duplicate provenance label: {normalized_label}.")
        files[normalized_label] = Path(raw_path.strip()).expanduser()
    if args.publication_run:
        required = {
            "reference_ontology",
            "retrieval_workspace",
            "environment_lock",
        }
        missing = sorted(required - set(files))
        if missing:
            raise SystemExit(
                "--publication-run requires --provenance-file entries for "
                + ", ".join(missing)
                + "."
            )
    return files


def _validate_environment_lock(
    *,
    path: Path,
    args: argparse.Namespace,
    profile: ProviderProfile,
    rc: HaiuRC,
    haiu_distribution: dict[str, Any],
    input_catalog: HeaderSublemmaCatalog | None = None,
    dmw_input_manifest: DmwPairImportManifest | None = None,
) -> None:
    """Confirm a publication snapshot matches the selected live configuration.

    The environment lock does not configure a run.  It proves the frozen
    DMW/OPA/Haiu stack and provider environment that the command is about to
    use.  This check rejects a stale or mismatched snapshot before any DMW
    request can create an annotation or ontology observation.

    :param path: Captured non-secret environment-lock JSON document.
    :param args: Parsed runner arguments with the selected DMW branch.
    :param profile: Pinned generation and embedding provider profile.
    :param rc: Resolved Haiu client configuration after profile application.
    :param haiu_distribution: Actual imported Haiu distribution provenance.
    :param input_catalog: Optional pair population for schema-v2 locks.
    :param dmw_input_manifest: Optional prepared pair storage evidence.
    :return: None.
    :raises SystemExit: If the document is malformed or differs from the
        selected publication configuration.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Cannot read environment_lock: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit("environment_lock is not valid JSON.") from exc
    schema_version = (
        payload.get("schema_version") if isinstance(payload, dict) else None
    )
    if schema_version not in {1, 2}:
        raise SystemExit("environment_lock must use schema_version 1 or 2.")
    pair_mode = input_catalog is not None
    if pair_mode and schema_version != 2:
        raise SystemExit(
            "Header--sublemma publication runs require environment_lock "
            "schema_version 2."
        )
    if not pair_mode and schema_version != 1:
        raise SystemExit(
            "Complete-regest publication runs require environment_lock "
            "schema_version 1."
        )
    if pair_mode != (dmw_input_manifest is not None):
        raise SystemExit("Pair environment-lock validation is incomplete.")

    provider = payload.get("provider")
    if not isinstance(provider, dict):
        raise SystemExit("environment_lock does not contain provider evidence.")
    if provider.get("profile") != profile.manifest_entry():
        raise SystemExit(
            "environment_lock provider profile differs from --provider-profile."
        )
    endpoint_hashes = {
        "chat_endpoint_sha256": hashlib.sha256(
            rc.client.base_url.encode("utf-8")
        ).hexdigest(),
        "embedding_endpoint_sha256": hashlib.sha256(
            str(rc.client.embedding_base_url or rc.client.base_url).encode(
                "utf-8"
            )
        ).hexdigest(),
    }
    for field, expected in endpoint_hashes.items():
        if provider.get(field) != expected:
            raise SystemExit(
                "environment_lock endpoint identity differs from the resolved "
                f"provider configuration ({field})."
            )

    ontology_identity = payload.get("dmw_ontology_identity")
    if not isinstance(ontology_identity, dict):
        raise SystemExit(
            "environment_lock does not contain DMW ontology branch evidence."
        )
    if ontology_identity.get("branch") != args.branch:
        raise SystemExit(
            "environment_lock DMW branch differs from the requested --branch."
        )
    if (
        not isinstance(ontology_identity.get("collection"), str)
        or not str(ontology_identity["collection"]).strip()
    ):
        raise SystemExit(
            "environment_lock does not identify the DMW collection."
        )

    repositories = payload.get("repositories")
    if not isinstance(repositories, dict):
        raise SystemExit(
            "environment_lock does not contain repository evidence."
        )
    for name in ("datamodel_workflow", "opa", "gta", "haiu"):
        record = repositories.get(name)
        if not isinstance(record, dict):
            raise SystemExit(
                f"environment_lock has no {name} repository record."
            )
        if not isinstance(record.get("commit"), str) or not record["commit"]:
            raise SystemExit(
                f"environment_lock {name} repository record has no commit."
            )
        lock_hashes = record.get("dependency_file_sha256")
        if not isinstance(lock_hashes, dict) or not lock_hashes:
            raise SystemExit(
                f"environment_lock {name} repository record has no lock hashes."
            )

    packages = (
        payload.get("runtime", {})
        if isinstance(payload.get("runtime"), dict)
        else {}
    ).get("packages")
    if not isinstance(packages, dict):
        raise SystemExit(
            "environment_lock does not contain installed packages."
        )
    for distribution_name, expected in APPROVED_RUNTIME_DISTRIBUTIONS.items():
        package = packages.get(distribution_name)
        source = package.get("source") if isinstance(package, dict) else None
        repository = repositories.get(str(expected["repository"]))
        if (
            not isinstance(package, dict)
            or not isinstance(source, dict)
            or not isinstance(repository, dict)
            or package.get("version") != expected["version"]
            or source.get("editable")
            or source.get("vcs") != "git"
            or source.get("url") != expected["url"]
            or source.get("requested_revision") != expected["revision"]
            or not _is_git_commit_id(source.get("commit_id"))
            or source.get("commit_id") != repository.get("commit")
        ):
            raise SystemExit(
                "environment_lock does not prove the approved, non-editable, "
                f"commit-matched {distribution_name} release."
            )

    haiu_package = packages.get("haiu")
    haiu_source = (
        haiu_package.get("source") if isinstance(haiu_package, dict) else None
    )
    if not isinstance(haiu_package, dict) or not isinstance(haiu_source, dict):
        raise SystemExit(
            "environment_lock does not prove the approved Haiu release."
        )
    locked_commit = haiu_source.get("commit_id")
    if (
        haiu_package.get("version") != PUBLISHED_HAIU_VERSION
        or haiu_source.get("editable")
        or haiu_source.get("vcs") != "git"
        or haiu_source.get("url") != APPROVED_HAIU_VCS_URL
        or haiu_source.get("requested_revision") != APPROVED_HAIU_VCS_REVISION
        or not _is_git_commit_id(locked_commit)
        or locked_commit != haiu_distribution.get("commit_id")
    ):
        raise SystemExit(
            "environment_lock does not match the imported approved Haiu release."
        )

    if not pair_mode:
        return
    assert input_catalog is not None
    assert dmw_input_manifest is not None
    expected_input_population = {
        "schema_version": 1,
        "unit_kind": "header_sublemma_pair",
        "file_sha256": input_catalog.file_sha256,
        "catalogue_content_sha256": input_catalog.content_sha256,
        "input_unit_count": len(input_catalog.records),
        "dmw_import_manifest_file_sha256": dmw_input_manifest.file_sha256,
        "dmw_import_manifest_content_sha256": (
            dmw_input_manifest.content_sha256
        ),
    }
    if payload.get("input_population") != expected_input_population:
        raise SystemExit(
            "environment_lock does not match the pair catalogue and import "
            "manifest."
        )
    collections = dmw_input_manifest.collections
    expected_data_identity = {
        "branch": args.branch,
        "raw": collections["raw"],
        "annotation": collections["annotation"],
        "ontology": collections["ontology"],
        "ontology_context_version": args.ontology_context_version,
    }
    if payload.get("dmw_data_identity") != expected_data_identity:
        raise SystemExit(
            "environment_lock does not match the prepared pair DMW identity."
        )
    harness = payload.get("experiment_harness")
    live_harness = _experiment_harness_identity()
    if (
        not isinstance(harness, dict)
        or harness.get("commit") != live_harness["commit"]
        or harness.get("worktree_clean") is not True
    ):
        raise SystemExit(
            "environment_lock does not match the clean experiment harness "
            "commit."
        )


def _experiment_harness_identity() -> dict[str, str | bool]:
    """Return the commit of the clean checkout running this experiment.

    :return: Commit and cleanliness evidence without local path information.
    :raises SystemExit: If Git inspection fails or tracked state is dirty.
    """
    repository_root = REPOSITORY_ROOT
    commands = {
        "commit": ["git", "rev-parse", "HEAD"],
        "status": ["git", "status", "--porcelain"],
    }
    outputs: dict[str, str] = {}
    for label, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise SystemExit(f"Cannot inspect experiment harness Git {label}.")
        outputs[label] = completed.stdout.strip()
    if outputs["status"]:
        raise SystemExit(
            "Experiment harness has uncommitted changes; capture and run from "
            "the same clean commit."
        )
    return {"commit": outputs["commit"], "worktree_clean": True}


def _is_git_commit_id(value: object) -> bool:
    """Return whether one value is a full lowercase Git object identifier.

    :param value: Candidate value from installed-distribution provenance.
    :return: Whether the value is a 40-character hexadecimal Git commit ID.
    """
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{40}", value) is not None
    )


def _resolve_ids_file(raw_path: str) -> Path:
    if raw_path:
        path = Path(raw_path).expanduser()
        return path if path.is_absolute() else path.resolve()
    if DEFAULT_LOCAL_IDS.exists():
        return DEFAULT_LOCAL_IDS
    raise SystemExit(
        f"No ids file found. Pass --ids-file or create {DEFAULT_LOCAL_IDS}."
    )


def _read_prompt(raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    return path.read_text(encoding="utf-8").strip()


def _workflow_config(
    *,
    args: argparse.Namespace,
    condition: str,
    run_id: str,
    model: str,
    historian_input: str,
    frozen_annotation: FrozenAnnotation | None,
) -> WorkflowRequestConfig:
    suffix = "full" if condition == "workflow_full_ontology" else "rag"
    context_mode = (
        "full_ontology" if condition == "workflow_full_ontology" else "rag"
    )
    annotation_model = model
    return WorkflowRequestConfig(
        branch=args.branch,
        annotation_model=annotation_model,
        annotation_guideline_version=args.annotation_guideline_version,
        annotation_min_version=args.annotation_min_version,
        annotation_top_n=args.annotation_top_n,
        annotation_example_limit=args.annotation_example_limit,
        ontology_record_version=f"exp-haiu-compare-{run_id}-{suffix}",
        ontology_context_version=args.ontology_context_version,
        ontology_user_input=historian_input,
        ontology_min_example_version=args.ontology_min_example_version,
        ontology_model_name=model,
        ontology_context_mode=context_mode,
        ontology_example_limit=args.ontology_example_limit,
        max_output_tokens=args.max_output_tokens,
        output_safety_margin_tokens=args.output_safety_margin_tokens,
        require_exact_prompt_tokens=args.publication_run,
        require_finish_reason=args.publication_run,
        include_annotations=args.include_annotations,
        use_only_existing_ontology_terms=args.use_only_existing_ontology_terms,
        allow_text_interpretation=False,
        existing_data_policy="reuse",
        require_existing_annotation=args.include_annotations,
        frozen_annotation_sha256=(
            frozen_annotation.content_sha256
            if frozen_annotation is not None
            else None
        ),
    )


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
