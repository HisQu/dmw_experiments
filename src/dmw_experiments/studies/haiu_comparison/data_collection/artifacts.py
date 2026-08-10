"""Artifact writing for ontology comparison outputs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import haiu.utils as haiu_utils

from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ARTIFACT_SCHEMA_VERSION,
    ExecutionArtifactLayout,
    compatibility_prompt_key,
    portable_name,
)
from dmw_experiments.studies.haiu_comparison.model.artifact_records import (
    ArtifactReference,
    CellResultRecord,
    load_upstream_payload,
    verify_artifact_references,
)
from dmw_experiments.studies.haiu_comparison.data_collection.measurements import (
    summarize_rows,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    ExperimentResult,
)
from dmw_experiments.studies.haiu_comparison.model.traces import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    CONDITIONS,
)

RETRIEVAL_CONDITIONS = frozenset({"workflow_rag", "haiu_rag_ontologizer"})
RawDocumentPaths = dict[str, Any]

# > Full provider responses and prompts are authoritative raw evidence on disk.
# > Keeping a second copy in every runner-resume row exhausts local memory as a
# > publication matrix grows, while scalar metrics and artifact paths are all
# > the runner needs to resume safely.
NORMALIZED_ROW_OMITTED_FIELDS = frozenset(
    {
        "raw_response",
        "generation_attempts",
        "ontology_context",
        "prompts",
        "raw_ttl_output",
        "raw_stage1_output",
        "explanation",
        "tbox",
        "abox",
    }
)


class ArtifactWriter:
    """Write one execution's evidence into navigable per-unit bundles.

    :param output_dir: Top-level ``raw-<execution>`` directory.
    """

    def __init__(self, output_dir: Path) -> None:
        self.layout = ExecutionArtifactLayout(output_dir)
        self.layout.prepare()
        self.output_dir = self.layout.output
        self.execution_name = self.layout.execution
        self.run_root = self.layout.run_root
        self.path_root = self.run_root
        self.intermediate_dirs = {
            condition: self.layout.intermediate_condition(condition)
            for condition in CONDITIONS
        }
        self.result_dirs = {
            condition: self.layout.result_condition(condition)
            for condition in CONDITIONS
        }
        self.normalized_dir = self.run_root / "analysis" / "intermediate"
        self.diagnostics_dir = self.run_root / "analysis" / "diagnostics"
        self.environment_dir = self.run_root / "environment"
        self.amendment_dir = self.layout.amendments
        self.superseded_dir = self.layout.superseded
        self.provenance_dir = self.layout.provenance
        for path in (
            self.normalized_dir,
            self.diagnostics_dir,
            self.environment_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def write_provenance(
        self,
        *,
        input_files: dict[str, Path],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy frozen non-secret inputs and record their portable hashes.

        :param input_files: Stable labels and source files to snapshot.
        :param metadata: Non-secret environment and provider provenance.
        :return: Snapshot manifest written under ``provenance/``.
        :raises ValueError: If a resumed run's snapshot would change.
        """
        frozen_inputs: dict[str, dict[str, str]] = {}
        for label, source in sorted(input_files.items()):
            if not source.is_file():
                raise ValueError(f"Provenance input does not exist: {label}")
            suffix = source.suffix or ".bin"
            target = self.provenance_dir / f"{portable_name(label)}{suffix}"
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if target.exists() and target.read_bytes() != content:
                raise ValueError(
                    "Run provenance differs from the existing frozen input: "
                    f"{target.name}"
                )
            if not target.exists():
                _write_bytes_atomic(target, content)
            frozen_inputs[label] = {
                "path": target.relative_to(self.path_root).as_posix(),
                "sha256": digest,
            }
        payload = {"schema_version": 1, "inputs": frozen_inputs, **metadata}
        path = self.provenance_dir / "manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                raise ValueError(
                    "Run provenance manifest differs from request."
                )
        else:
            _write_text_atomic(
                path,
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            )
        return payload

    def validate_frozen_provenance_inputs(
        self,
        *,
        input_files: dict[str, Path],
    ) -> None:
        """Verify that an amendment still uses the original frozen inputs.

        :param input_files: Stable labels and source files supplied to the
            resumed command.
        :return: None.
        :raises ValueError: If a required frozen input is missing or differs.
        """
        manifest_path = self.provenance_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(
                "Cannot amend a run without its provenance manifest."
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inputs = manifest.get("inputs")
        if not isinstance(inputs, dict):
            raise ValueError("Run provenance manifest has no input records.")
        if set(inputs) != set(input_files):
            raise ValueError(
                "Amendment provenance inputs differ from the frozen run."
            )
        for label, source in sorted(input_files.items()):
            if not source.is_file():
                raise ValueError(f"Provenance input does not exist: {label}")
            record = inputs[label]
            if not isinstance(record, dict):
                raise ValueError(
                    f"Run provenance input record is invalid: {label}"
                )
            expected_path = record.get("path")
            expected_digest = record.get("sha256")
            if not isinstance(expected_path, str) or not isinstance(
                expected_digest, str
            ):
                raise ValueError(
                    f"Run provenance input record is invalid: {label}"
                )
            frozen_path = self.path_root / expected_path
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if (
                digest != expected_digest
                or not frozen_path.is_file()
                or frozen_path.read_bytes() != content
            ):
                raise ValueError(
                    "Amendment provenance differs from the frozen input: "
                    f"{label}"
                )

    def ensure_frozen_regests(
        self,
        *,
        regest_ids: list[str],
        fetcher: Callable[[str], RegestText],
    ) -> tuple[dict[str, RegestText], dict[str, Any]]:
        """Freeze raw regest inputs before standalone condition execution.

        The standalone condition reads these local copies and therefore does
        not call DMW while it retrieves or generates. Existing snapshots are
        verified and reused rather than fetched again on resume.

        :param regest_ids: Ordered selected DMW identifiers.
        :param fetcher: Preflight function that returns one raw regest.
        :return: Regests keyed by ID plus their portable snapshot manifest.
        :raises ValueError: If an existing snapshot is malformed or differs
            from the requested frozen population.
        """
        snapshot_dir = self.provenance_dir / "raw-regests"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        records: dict[str, dict[str, str]] = {}
        regests: dict[str, RegestText] = {}
        for regest_id in regest_ids:
            path = snapshot_dir / f"{portable_name(regest_id)}.json"
            if path.is_file():
                regest = _frozen_regest_from_payload(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            else:
                fetched = fetcher(regest_id)
                if not isinstance(fetched, RegestText):
                    raise ValueError(
                        "Raw-regest preflight did not return RegestText for "
                        f"{regest_id}."
                    )
                if fetched.regest_id != regest_id:
                    raise ValueError(
                        "Raw-regest preflight returned a different ID: "
                        f"expected {regest_id}, received {fetched.regest_id}."
                    )
                regest = fetched
                _write_text_atomic(
                    path,
                    json.dumps(
                        _frozen_regest_payload(regest),
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
            regests[regest_id] = regest
            records[regest_id] = {
                "path": path.relative_to(self.path_root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        manifest = {
            "schema_version": 1,
            "source": "preflight_frozen_raw_regest_snapshot",
            "records": records,
        }
        manifest_path = snapshot_dir / "manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing != manifest:
                raise ValueError(
                    "Frozen raw-regest snapshot differs from the requested "
                    "publication population."
                )
        else:
            _write_text_atomic(
                manifest_path,
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
        return regests, {
            "path": manifest_path.relative_to(self.path_root).as_posix(),
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "count": len(regests),
        }

    def write_result(
        self,
        result: ExperimentResult,
        *,
        terminal: bool = True,
    ) -> dict[str, Any]:
        """Write one attempt bundle and optionally its terminal result.

        A retryable failed attempt is complete evidence but not a terminal
        matrix cell. Callers therefore pass ``terminal=False`` from the retry
        checkpoint and write the final attempt with the default value.

        :param result: Condition result for one completed attempt.
        :param terminal: Whether this attempt terminates the matrix cell.
        :return: Compact legacy-compatible row used by runner checkpoints.
        """
        source_payload = dict(result.payload)
        source_payload.setdefault("condition", result.condition)
        source_payload.setdefault("regest_id", result.regest_id)
        source_payload.setdefault("success", result.success)
        if source_payload["condition"] != result.condition:
            raise ValueError("Result condition differs from its payload.")
        if source_payload["regest_id"] != result.regest_id:
            raise ValueError("Result input-unit ID differs from its payload.")
        if bool(source_payload["success"]) != result.success:
            raise ValueError("Result success flag differs from its payload.")
        raw_json = json.dumps(
            source_payload, indent=2, ensure_ascii=False, default=str
        ).encode("utf-8")
        payload = json.loads(raw_json.decode("utf-8"))
        return self._write_payload(
            payload=payload,
            condition=result.condition,
            regest_id=result.regest_id,
            source_json=raw_json,
            terminal=terminal,
        )

    def _write_payload(
        self,
        *,
        payload: dict[str, Any],
        condition: str,
        regest_id: str,
        source_json: bytes,
        terminal: bool,
    ) -> dict[str, Any]:
        """Materialize one already-serialized result without field loss.

        :param payload: Parsed complete source payload.
        :param condition: Stable condition owner.
        :param regest_id: Stable input-unit identifier.
        :param source_json: Exact JSON bytes retained under gzip.
        :param terminal: Whether to expose a terminal result bundle.
        :return: Compact runner and analysis row.
        """
        attempt_number = _positive_attempt_number(payload)
        self._write_retained_attempt_history(
            condition=condition,
            regest_id=regest_id,
            current_attempt=attempt_number,
            payload=payload,
        )
        failed = not bool(payload.get("success"))
        attempt_dir = self.layout.attempt(
            condition,
            regest_id,
            attempt_number,
            failed=failed,
        )
        conflicting_attempt = self.layout.attempt(
            condition,
            regest_id,
            attempt_number,
            failed=not failed,
        )
        if conflicting_attempt.exists():
            raise ValueError(
                "Attempt outcome differs from existing evidence: "
                f"{conflicting_attempt.relative_to(self.path_root)}"
            )
        attempt_dir.mkdir(parents=True, exist_ok=True)
        artifacts, raw_document_paths, prompt_paths = (
            self._write_attempt_documents(
                condition=condition,
                regest_id=regest_id,
                attempt_dir=attempt_dir,
                payload=payload,
                source_json=source_json,
                terminal=terminal,
            )
        )
        record = CellResultRecord.from_payload(
            payload=payload,
            condition=condition,
            unit_id=regest_id,
            artifacts=artifacts,
        ).as_dict()
        metadata_path = attempt_dir / "metadata.json"
        _write_json_atomic(
            metadata_path,
            {**record, "record_type": "haiu_comparison_attempt"},
        )
        if terminal:
            result_path = self.layout.result_record(condition, regest_id)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(result_path, record)
            raw_path = result_path
        else:
            raw_path = metadata_path
        return self._normalized_row(
            payload=payload,
            condition=condition,
            regest_id=regest_id,
            raw_path=raw_path,
            raw_document_paths=raw_document_paths,
            prompt_paths=prompt_paths,
        )

    def _write_retained_attempt_history(
        self,
        *,
        condition: str,
        regest_id: str,
        current_attempt: int,
        payload: dict[str, Any],
    ) -> None:
        """Expose every available pre-current attempt as a named directory.

        Schema-v2 overwrote its temporary result when a retry succeeded, but
        retained scalar attempt summaries in the final payload. A migration
        cannot reconstruct absent prompts or responses, so this method writes
        exactly the surviving summary and states that limitation. Native
        schema-v3 collection has already written the complete failed bundle;
        an existing directory is therefore left unchanged.

        :param condition: Scientific condition that owns the attempt.
        :param regest_id: Input-unit identifier.
        :param current_attempt: Attempt represented by the complete payload.
        :param payload: Complete current result with optional attempt history.
        :return: ``None`` after every retained earlier attempt is visible.
        :raises ValueError: If the history declares an invalid or conflicting
            attempt identity.
        """
        history = payload.get("attempt_history")
        if not isinstance(history, list):
            return
        for summary in history:
            if not isinstance(summary, dict):
                raise ValueError("Attempt history entries must be objects.")
            number = summary.get("attempt")
            if not isinstance(number, int) or number < 1:
                raise ValueError(
                    "Attempt history has an invalid attempt number."
                )
            if number >= current_attempt:
                continue
            failed = not bool(summary.get("success"))
            attempt_dir = self.layout.attempt(
                condition,
                regest_id,
                number,
                failed=failed,
            )
            conflicting = self.layout.attempt(
                condition,
                regest_id,
                number,
                failed=not failed,
            )
            if conflicting.exists():
                raise ValueError(
                    "Attempt history differs from existing evidence: "
                    f"{conflicting.relative_to(self.path_root)}"
                )
            metadata = attempt_dir / "metadata.json"
            if metadata.is_file():
                continue
            record = {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "record_type": "haiu_comparison_legacy_attempt_summary",
                "identity": {
                    "condition": condition,
                    "regest_id": regest_id,
                },
                "outcome": {
                    "success": bool(summary.get("success")),
                },
                "attempts": {
                    "attempt": number,
                    "legacy_attempt_history": deepcopy(summary),
                },
                "artifacts": {
                    "upstream_result": {
                        "status": "unavailable",
                        "reason": (
                            "Schema v2 retained only this scalar attempt "
                            "summary after a later retry replaced the result."
                        ),
                    }
                },
            }
            _write_json_atomic(metadata, record)

    def load_existing_rows(self) -> list[dict[str, Any]]:
        """Rebuild normalized rows from authoritative per-result artifacts.

        The raw artifact is written before aggregate checkpoints. Reading it
        directly recovers a result when a process stopped between those two
        writes.

        :return: Normalized rows recovered from the run directory.
        """
        rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for condition, result_path in self.layout.iter_result_records():
            row = self._row_from_v3_result(
                result_path=result_path,
                condition=condition,
            )
            rows_by_key[(condition, str(row["regest_id"]))] = row
        for condition, raw_path in self.layout.iter_legacy_result_records():
            legacy_id = raw_path.stem
            key = (condition, legacy_id)
            if key in rows_by_key:
                continue
            rows_by_key[key] = self._row_from_legacy_result(
                raw_path=raw_path,
                condition=condition,
            )
        rows = list(rows_by_key.values())
        return rows

    def _row_from_v3_result(
        self,
        *,
        result_path: Path,
        condition: str,
    ) -> dict[str, Any]:
        """Rebuild a compact row from one schema-v3 terminal record.

        :param result_path: Canonical nested ``result.json``.
        :param condition: Condition encoded by the owning directory.
        :return: Compact row with portable evidence paths.
        """
        record = _load_json_object(result_path)
        if record.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported result schema in {result_path}: "
                f"{record.get('schema_version')!r}"
            )
        verify_artifact_references(record, run_root=self.path_root)
        payload = load_upstream_payload(record, run_root=self.path_root)
        regest_id = str(payload.get("regest_id") or result_path.parent.name)
        recorded_condition = str(payload.get("condition") or condition)
        if recorded_condition != condition:
            raise ValueError(
                "Result condition differs from its directory: "
                f"{result_path.relative_to(self.path_root)}"
            )
        raw_document_paths, prompt_paths = _paths_from_v3_record(record)
        return self._normalized_row(
            payload=payload,
            condition=condition,
            regest_id=regest_id,
            raw_path=result_path,
            raw_document_paths=raw_document_paths,
            prompt_paths=prompt_paths,
        )

    def _row_from_legacy_result(
        self,
        *,
        raw_path: Path,
        condition: str,
    ) -> dict[str, Any]:
        """Rebuild one compact row from a terminal observation.

        :param raw_path: Authoritative result JSON path.
        :param condition: Condition owning the result directory.
        :return: Compact normalized row.
        """
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"Raw result is not a JSON object: "
                f"{raw_path.relative_to(self.path_root)}"
            )
        recorded_condition = str(payload.get("condition") or condition)
        if recorded_condition != condition:
            raise ValueError(
                f"Result condition differs from its directory: {raw_path.name}."
            )
        regest_id = str(payload.get("regest_id") or raw_path.stem)
        safe_id = portable_name(regest_id)
        raw_document_paths = self._write_legacy_raw_documents(
            condition=condition,
            safe_id=safe_id,
            payload=payload,
        )
        return self._normalized_row(
            payload=payload,
            condition=condition,
            regest_id=regest_id,
            raw_path=raw_path,
            raw_document_paths=raw_document_paths,
            prompt_paths=self._existing_prompt_paths(
                condition=condition,
                safe_id=safe_id,
            ),
        )

    def materialize_existing_raw_documents(self) -> dict[str, int]:
        """Convert legacy flat results into schema-v3 per-unit bundles.

        Source files remain untouched. Full in-place migration moves them only
        after the new bundles pass independent verification.

        :return: Counts of written derived documents and unavailable Stage-1
            captures.
        """
        counts = {
            "result": 0,
            "ttl": 0,
            "stage1": 0,
            "stage1_unavailable": 0,
            "retrieved_metadata": 0,
            "retrieved_ttl": 0,
        }
        for condition, raw_path in self.layout.iter_legacy_result_records():
            source_json = raw_path.read_bytes()
            payload = json.loads(source_json.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Raw result is not a JSON object: "
                    f"{raw_path.relative_to(self.path_root)}"
                )
            regest_id = str(payload.get("regest_id") or raw_path.stem)
            row = self._write_payload(
                payload=payload,
                condition=condition,
                regest_id=regest_id,
                source_json=source_json,
                terminal=True,
            )
            counts["result"] += 1
            counts["ttl"] += int(bool(row.get("raw_ttl_artifact_path")))
            counts["stage1"] += int(bool(row.get("raw_stage1_artifact_path")))
            counts["stage1_unavailable"] += int(
                not bool(row.get("raw_stage1_artifact_path"))
            )
            counts["retrieved_metadata"] += int(
                bool(row.get("retrieved_yaml_artifact_path"))
            )
            counts["retrieved_ttl"] += int(
                bool(row.get("retrieved_ttl_artifact_path"))
            )
        return counts

    def write_final_outputs(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Path]:
        """Write final JSONL, CSV, and summary files.

        :param rows: Compact rows containing scalar analysis metadata and paths
            to the authoritative raw evidence.
        :return: Output path mapping.
        """
        prefix = self.execution_name
        jsonl_path = self.normalized_dir / f"{prefix}-results.jsonl"
        csv_path = self.normalized_dir / f"{prefix}-results.csv"
        summary_path = (
            self.normalized_dir / f"{prefix}-summary_by_condition.json"
        )
        _write_text_atomic(
            jsonl_path,
            "".join(
                json.dumps(row, ensure_ascii=False, default=str) + "\n"
                for row in rows
            ),
        )
        csv_temp_path = csv_path.with_name(f".{csv_path.name}.tmp")
        _write_csv(csv_temp_path, rows)
        csv_temp_path.replace(csv_path)
        _write_text_atomic(
            summary_path,
            json.dumps(
                summarize_rows(rows), indent=2, ensure_ascii=False, default=str
            ),
        )
        return {
            "jsonl": jsonl_path,
            "csv": csv_path,
            "summary": summary_path,
        }

    def _normalized_row(
        self,
        *,
        payload: dict[str, Any],
        condition: str,
        regest_id: str,
        raw_path: Path,
        raw_document_paths: RawDocumentPaths,
        prompt_paths: dict[str, str],
    ) -> dict[str, Any]:
        """Build the compact runner checkpoint for one raw observation.

        The raw JSON and its prompt, response, and retrieval sidecars retain
        complete provider evidence. This row deliberately keeps only the
        fields needed for retry classification, aggregate analysis, and
        artifact navigation, so a resumed long-running matrix does not retain
        every multi-megabyte provider response in memory.

        :param payload: Complete durable result payload.
        :param condition: Stable condition name for the result.
        :param regest_id: Stable regest identifier for the result.
        :param raw_path: Authoritative raw JSON path.
        :param raw_document_paths: Paths written from complete raw content.
        :param prompt_paths: Paths written from complete prompt content.
        :return: Compact normalized row with portable artifact paths.
        """
        row = {
            key: value
            for key, value in payload.items()
            if key not in NORMALIZED_ROW_OMITTED_FIELDS
        }
        row["condition"] = condition
        row["regest_id"] = regest_id
        row["raw_artifact_path"] = raw_path.relative_to(
            self.path_root
        ).as_posix()
        row["raw_ttl_artifact_path"] = raw_document_paths.get("ttl")
        row["raw_stage1_artifact_path"] = raw_document_paths.get("stage1")
        row["raw_stage1_metadata_artifact_path"] = raw_document_paths.get(
            "stage1_metadata"
        )
        row["attempt_ttl_artifact_paths"] = raw_document_paths.get(
            "attempt_ttl"
        )
        row["raw_yaml_artifact_path"] = raw_document_paths.get("yaml")
        row["retrieved_ttl_artifact_path"] = raw_document_paths.get(
            "retrieved_ttl"
        )
        row["retrieved_yaml_artifact_path"] = raw_document_paths.get(
            "retrieved_yaml"
        )
        row["retrieval_snapshot_fidelity"] = raw_document_paths.get(
            "retrieval_snapshot_fidelity"
        )
        row["retrieval_sidecars_complete"] = raw_document_paths.get(
            "retrieval_sidecars_complete"
        )
        row["prompt_artifact_paths"] = prompt_paths
        annotation_path = (
            self.layout.annotation_unit(regest_id) / "annotation.json"
        )
        if annotation_path.is_file():
            row["frozen_annotation_artifact_paths"] = {
                "json": annotation_path.relative_to(self.path_root).as_posix()
            }
        return row

    def write_id_selection(self, payload: dict[str, Any]) -> Path:
        """Write the preflight ID selection report.

        :param payload: JSON-friendly ID selection report.
        :return: Written artifact path.
        """
        path = self.diagnostics_dir / f"{self.execution_name}-id-selection.json"
        _write_text_atomic(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return path

    def load_frozen_annotation(
        self,
        *,
        regest_id: str,
    ) -> dict[str, Any] | None:
        """Load one durable annotation snapshot when it exists.

        :param regest_id: Datamodel regest identifier.
        :return: Parsed snapshot, or ``None`` before preparation succeeds.
        """
        path = self.layout.annotation_unit(regest_id) / "annotation.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Frozen annotation is not an object: {path.name}")
        return payload

    def write_frozen_annotation(
        self,
        *,
        regest_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """Persist the exact accepted annotation once as canonical JSON.

        :param regest_id: Datamodel regest identifier.
        :param payload: Portable raw annotation and preparation provenance.
        :return: Run-relative canonical annotation path.
        """
        annotation_dir = self.layout.annotation_unit(regest_id)
        annotation_dir.mkdir(parents=True, exist_ok=True)
        json_path = annotation_dir / "annotation.json"
        _write_json_atomic(json_path, payload)
        return {
            "json": json_path.relative_to(self.path_root).as_posix(),
        }

    def write_annotation_attempt_state(
        self,
        *,
        regest_id: str,
        payload: dict[str, Any],
    ) -> Path:
        """Checkpoint annotation preparation independently from ontology rows.

        :param regest_id: Datamodel regest identifier.
        :param payload: JSON-friendly retry state.
        :return: Written attempt-state path.
        """
        path = self.layout.annotation_unit(regest_id) / "attempts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, payload)
        return path

    def load_annotation_attempt_state(
        self,
        *,
        regest_id: str,
    ) -> dict[str, Any] | None:
        """Load the durable retry state for one shared annotation.

        This state distinguishes an interrupted preparation from one that has
        exhausted its configured retry budget before workflow rows exist.

        :param regest_id: Datamodel regest identifier.
        :return: Parsed attempt state, or ``None`` when preparation never ran.
        :raises ValueError: If the durable state is not a JSON object.
        """
        path = self.layout.annotation_unit(regest_id) / "attempts.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"Annotation attempt state is not an object: {path.name}"
            )
        return payload

    def archive_annotation_attempt_state_for_amendment(
        self,
        *,
        amendment_id: str,
        regest_id: str,
    ) -> dict[str, Any] | None:
        """Preserve and clear one failed shared-annotation retry state.

        A narrowly approved runtime recovery can make an exhausted annotation
        preparation retryable again. The original state is copied into the
        amendment namespace before the active checkpoint is removed, so the
        resumed workflow can prepare the immutable input afresh without
        losing the failure evidence.

        :param amendment_id: Stable amendment namespace owning the archive.
        :param regest_id: Datamodel regest identifier whose retry state is
            being reset.
        :return: Archive record, or ``None`` when no active state exists.
        :raises ValueError: If an existing archive disagrees with the active
            durable state.
        """
        safe_id = portable_name(regest_id)
        source = self.layout.annotation_unit(regest_id) / "attempts.json"
        archive_root = self.superseded_dir / amendment_id
        index_path = archive_root / "annotation_attempt_archive_index.json"
        key = safe_id
        index = (
            json.loads(index_path.read_text(encoding="utf-8"))
            if index_path.exists()
            else {"schema_version": 1, "records": {}}
        )
        records = index.get("records")
        if not isinstance(records, dict):
            raise ValueError(
                "Annotation-attempt amendment archive index has invalid "
                "records."
            )
        existing = records.get(key)
        if isinstance(existing, dict):
            if source.is_file():
                source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
                if (
                    existing.get("canonical_annotation_attempt_sha256")
                    != source_digest
                ):
                    raise ValueError(
                        "Annotation retry state changed after its amendment "
                        f"archive was created: {safe_id}"
                    )
                source.unlink()
            return existing
        if not source.is_file():
            return None

        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target = archive_root / source.relative_to(self.path_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        record = {
            "regest_id": regest_id,
            "canonical_annotation_attempt_sha256": source_digest,
            "superseded_annotation_attempt_state_path": target.relative_to(
                self.path_root
            ).as_posix(),
        }
        records[key] = record
        archive_root.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(
            index_path,
            json.dumps(index, indent=2, ensure_ascii=False, default=str),
        )
        source.unlink()
        return record

    def has_attempt_state(self, *, condition: str, regest_id: str) -> bool:
        """Report whether a condition/ID pair started in an earlier process.

        :param condition: Stable experiment condition.
        :param regest_id: Datamodel regest identifier.
        :return: Whether an attempt-state artifact exists.
        """
        return self._attempt_state_path(
            condition=condition,
            regest_id=regest_id,
        ).exists()

    def load_attempt_state(
        self,
        *,
        condition: str,
        regest_id: str,
    ) -> dict[str, Any] | None:
        """Load the durable checkpoint for one condition and regest pair.

        :param condition: Stable experiment condition.
        :param regest_id: Datamodel regest identifier.
        :return: Parsed checkpoint, or ``None`` when the pair never started.
        :raises ValueError: If the durable checkpoint is not a JSON object.
        """
        path = self._attempt_state_path(
            condition=condition,
            regest_id=regest_id,
        )
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Attempt state is not an object: {path.name}")
        return payload

    def write_attempt_state(
        self,
        *,
        condition: str,
        regest_id: str,
        payload: dict[str, Any],
    ) -> Path:
        """Checkpoint lightweight execution state for crash recovery.

        :param condition: Stable experiment condition.
        :param regest_id: Datamodel regest identifier.
        :param payload: JSON-friendly state without credentials.
        :return: Written attempt-state path.
        """
        path = self._attempt_state_path(
            condition=condition,
            regest_id=regest_id,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return path

    def ensure_run_manifest(
        self,
        payload: dict[str, Any],
        *,
        has_existing_results: bool,
    ) -> Path:
        """Create the immutable run identity or validate its exact match.

        A resumed run must not merge observations produced with different
        models, inputs, or workflow settings.

        :param payload: Complete JSON-friendly run identity.
        :param has_existing_results: Whether authoritative raw results exist.
        :return: Manifest artifact path.
        """
        path = self.layout.manifest
        record = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "record_type": "haiu_comparison_execution_manifest",
            "run": payload,
        }
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_run = (
                existing.get("run") if isinstance(existing, dict) else None
            )
            if existing_run != payload:
                raise ValueError(
                    "Run manifest differs from the requested experiment "
                    "configuration."
                )
            return path
        if has_existing_results:
            raise ValueError(
                "Cannot safely resume raw results without a run manifest."
            )
        _write_json_atomic(path, record)
        return path

    def load_run_manifest(self) -> dict[str, Any]:
        """Load the immutable base identity required for an amendment.

        :return: Parsed run-manifest payload.
        :raises ValueError: If no valid immutable base identity exists.
        """
        path = self.layout.manifest
        if not path.is_file():
            raise ValueError("Cannot amend a run without its run manifest.")
        record = json.loads(path.read_text(encoding="utf-8"))
        payload = record.get("run") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            raise ValueError("Run manifest is not a JSON object.")
        return payload

    def ensure_run_amendment(
        self,
        *,
        amendment_id: str,
        payload: dict[str, Any],
    ) -> Path:
        """Freeze one explicit, repeatable amendment to a run identity.

        The immutable base manifest continues to define the original run.
        Amendments are reserved for deliberate, documented recovery protocols
        that must not silently rewrite that identity.

        :param amendment_id: Stable portable name for this recovery protocol.
        :param payload: Complete JSON-friendly amendment evidence.
        :return: Immutable amendment path.
        :raises ValueError: If the identifier is unsafe or evidence differs.
        """
        safe_id = portable_name(amendment_id)
        if not amendment_id or safe_id != amendment_id:
            raise ValueError(
                "Run amendment ID must be a non-empty portable filename."
            )
        path = self.amendment_dir / f"{safe_id}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                raise ValueError(
                    "Run amendment differs from the requested recovery "
                    "configuration."
                )
            return path
        _write_text_atomic(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return path

    def archive_result_for_amendment(
        self,
        *,
        amendment_id: str,
        condition: str,
        regest_id: str,
    ) -> dict[str, Any]:
        """Copy canonical evidence before an amendment replaces one result.

        :param amendment_id: Stable amendment namespace owning the archive.
        :param condition: Condition whose canonical result will be replaced.
        :param regest_id: Regest identifier whose evidence must survive.
        :return: Relative archive paths and source content digest.
        :raises ValueError: If no canonical raw result exists or a prior archive
            does not match the source evidence.
        """
        safe_id = portable_name(regest_id)
        archive_root = self.superseded_dir / amendment_id
        index_path = archive_root / "archive_index.json"
        key = f"{condition}/{safe_id}"
        raw_path = self.layout.result_record(condition, regest_id)
        if not raw_path.is_file():
            raise ValueError(
                "Cannot archive an amendment result without canonical raw "
                f"evidence: {raw_path.relative_to(self.path_root)}"
            )
        source_digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        index = (
            json.loads(index_path.read_text(encoding="utf-8"))
            if index_path.exists()
            else {"schema_version": 1, "records": {}}
        )
        records = index.get("records")
        if not isinstance(records, dict):
            raise ValueError("Amendment archive index has invalid records.")
        existing = records.get(key)
        if isinstance(existing, dict):
            if existing.get("canonical_raw_sha256") != source_digest:
                raise ValueError(
                    "Canonical result changed after its amendment archive was "
                    f"created: {key}"
                )
            return existing
        source_paths = self._result_artifact_paths(
            condition=condition,
            safe_id=safe_id,
        )
        archived_paths: list[str] = []
        for source in source_paths:
            relative_path = source.relative_to(self.path_root)
            target = archive_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            archived_paths.append(target.relative_to(self.path_root).as_posix())
        record = {
            "condition": condition,
            "regest_id": regest_id,
            "canonical_raw_sha256": source_digest,
            "archived_paths": archived_paths,
            "canonical_raw_artifact_path": (
                archive_root / raw_path.relative_to(self.path_root)
            )
            .relative_to(self.path_root)
            .as_posix(),
        }
        records[key] = record
        archive_root.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(
            index_path,
            json.dumps(index, indent=2, ensure_ascii=False, default=str),
        )
        return record

    def _result_artifact_paths(
        self,
        *,
        condition: str,
        safe_id: str,
    ) -> list[Path]:
        """List canonical and derived evidence associated with one result.

        :param condition: Condition-specific artifact namespace.
        :param safe_id: Portable regest identifier.
        :return: Existing result artifacts in deterministic relative order.
        """
        result_unit = self.layout.result_unit(condition, safe_id)
        intermediate_unit = self.layout.intermediate_unit(condition, safe_id)
        return sorted(
            {
                artifact
                for directory in (result_unit, intermediate_unit)
                if directory.is_dir()
                for artifact in directory.rglob("*")
                if artifact.is_file()
            }
        )

    def _write_attempt_documents(
        self,
        *,
        condition: str,
        regest_id: str,
        attempt_dir: Path,
        payload: dict[str, Any],
        source_json: bytes,
        terminal: bool,
    ) -> tuple[dict[str, Any], RawDocumentPaths, dict[str, str]]:
        """Write exact evidence for one attempt and return its index data.

        :param condition: Stable scientific condition identifier.
        :param regest_id: Stable input-unit identifier.
        :param attempt_dir: Outcome-labelled attempt directory.
        :param payload: Complete result payload.
        :param source_json: Exact serialized payload retained losslessly.
        :param terminal: Whether this attempt terminates its matrix cell.
        :return: Nested artifact references, compatibility paths, and prompt
            paths.
        """
        artifacts: dict[str, Any] = {}
        raw_paths: RawDocumentPaths = {
            "stage1_metadata": (attempt_dir / "metadata.json")
            .relative_to(self.path_root)
            .as_posix(),
            "yaml": None,
        }

        upstream_path = attempt_dir / "upstream-result.json.gz"
        _write_bytes_atomic(upstream_path, gzip.compress(source_json, mtime=0))
        artifacts["upstream_result"] = ArtifactReference.from_path(
            upstream_path,
            run_root=self.path_root,
            media_type="application/json",
            content_encoding="gzip",
            uncompressed=source_json,
        ).as_dict()

        annotation_path = (
            self.layout.annotation_unit(regest_id) / "annotation.json"
        )
        if annotation_path.is_file():
            artifacts["shared_annotation"] = ArtifactReference.from_path(
                annotation_path,
                run_root=self.path_root,
                media_type="application/json",
            ).as_dict()

        prompt_references, prompt_paths = self._write_attempt_prompts(
            condition=condition,
            regest_id=regest_id,
            attempt_dir=attempt_dir,
            prompts=payload.get("prompts"),
        )
        if prompt_references:
            artifacts["prompts"] = prompt_references

        response_dir = attempt_dir / "responses"
        stage1_capture = _stage1_response_capture(payload)
        if stage1_capture["output"] is None:
            legacy_stage1 = self._legacy_stage1_response(
                condition=condition,
                regest_id=regest_id,
            )
            if legacy_stage1 is not None:
                stage1_capture = {
                    "status": "captured",
                    "source": "legacy_stage1_sidecar",
                    "output": legacy_stage1,
                    "reason": None,
                }
        raw_paths["stage1_capture_status"] = stage1_capture["status"]
        stage1_output = stage1_capture["output"]
        if stage1_output is not None:
            stage1_path = response_dir / "stage-1.md"
            _write_text_atomic(stage1_path, stage1_output)
            stage1_reference = ArtifactReference.from_path(
                stage1_path,
                run_root=self.path_root,
                media_type="text/markdown",
            ).as_dict()
            stage1_reference["source"] = stage1_capture["source"]
            artifacts["stage1_response"] = stage1_reference
            raw_paths["stage1"] = stage1_reference["path"]
        else:
            artifacts["stage1_response"] = {
                "status": "unavailable",
                "source": stage1_capture["source"],
                "reason": stage1_capture["reason"],
            }

        turtle_text = _raw_turtle_text(payload)
        if not turtle_text:
            legacy_turtle = (
                self.result_dirs[condition] / f"{portable_name(regest_id)}.ttl"
            )
            if legacy_turtle.is_file():
                turtle_text = legacy_turtle.read_text(encoding="utf-8")
        if turtle_text:
            stage2_path = response_dir / "stage-2.raw.txt"
            _write_text_atomic(stage2_path, turtle_text)
            stage2_reference = ArtifactReference.from_path(
                stage2_path,
                run_root=self.path_root,
                media_type="text/plain",
            ).as_dict()
            artifacts["stage2_response"] = stage2_reference
            raw_paths["ttl"] = stage2_reference["path"]
            raw_paths["attempt_ttl"] = {
                f"attempt_{_positive_attempt_number(payload)}": (
                    stage2_reference["path"]
                )
            }
            if terminal:
                ontology_path = self.layout.ontology(condition, regest_id)
                ontology_path.parent.mkdir(parents=True, exist_ok=True)
                _replace_hardlink(stage2_path, ontology_path)
                artifacts["ontology"] = ArtifactReference.from_path(
                    ontology_path,
                    run_root=self.path_root,
                    media_type="text/turtle",
                ).as_dict()
        else:
            artifacts["stage2_response"] = {
                "status": "unavailable",
                "reason": "No exact raw Stage-2 response was retained.",
            }
            raw_paths["attempt_ttl"] = {}
            if terminal:
                ontology_path = self.layout.ontology(condition, regest_id)
                if ontology_path.exists():
                    ontology_path.unlink()

        retrieval_artifacts, retrieval_paths = self._write_attempt_retrieval(
            condition=condition,
            regest_id=regest_id,
            attempt_dir=attempt_dir,
            payload=payload,
        )
        if retrieval_artifacts:
            artifacts["retrieval"] = retrieval_artifacts
        raw_paths.update(retrieval_paths)
        return artifacts, raw_paths, prompt_paths

    def _write_attempt_prompts(
        self,
        *,
        condition: str,
        regest_id: str,
        attempt_dir: Path,
        prompts: Any,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Write one clearly named file per model prompt.

        :param condition: Stable scientific condition identifier.
        :param regest_id: Stable input-unit identifier.
        :param attempt_dir: Attempt that owns the prompts.
        :param prompts: Stage/role mapping supplied by a condition adapter.
        :return: Artifact references and legacy-compatible path mapping.
        """
        if not isinstance(prompts, dict):
            prompts = {}
        prompt_dir = attempt_dir / "prompts"
        references: dict[str, Any] = {}
        paths: dict[str, str] = {}
        for stage, bundle in prompts.items():
            if not isinstance(bundle, dict):
                continue
            stage_label = _readable_stage_label(str(stage))
            legacy_stage_label = portable_name(str(stage))
            for role in ("system", "user"):
                content = bundle.get(role)
                if not isinstance(content, str) or not content:
                    continue
                artifact_path = prompt_dir / f"{stage_label}-{role}.md"
                _write_text_atomic(artifact_path, content)
                reference = ArtifactReference.from_path(
                    artifact_path,
                    run_root=self.path_root,
                    media_type="text/markdown",
                ).as_dict()
                references[f"{stage_label}-{role}"] = reference
                paths[f"{legacy_stage_label}_{role}"] = reference["path"]
        legacy_prefix = f"{portable_name(regest_id)}_"
        for source in sorted(
            self.intermediate_dirs[condition].glob(f"{legacy_prefix}*.md")
        ):
            legacy_label = source.stem.removeprefix(legacy_prefix)
            stage, separator, role = legacy_label.rpartition("_")
            if not separator or role not in {"system", "user"}:
                continue
            stage_label = _readable_stage_label(stage)
            artifact_label = f"{stage_label}-{role}"
            if artifact_label in references:
                continue
            artifact_path = prompt_dir / f"{artifact_label}.md"
            _write_text_atomic(
                artifact_path,
                source.read_text(encoding="utf-8"),
            )
            reference = ArtifactReference.from_path(
                artifact_path,
                run_root=self.path_root,
                media_type="text/markdown",
            ).as_dict()
            reference["source"] = "legacy_prompt_sidecar"
            references[artifact_label] = reference
            paths[legacy_label] = reference["path"]
        return references, paths

    def _write_attempt_retrieval(
        self,
        *,
        condition: str,
        regest_id: str,
        attempt_dir: Path,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], RawDocumentPaths]:
        """Write native retrieval evidence below the attempt that used it.

        :param condition: Stable scientific condition identifier.
        :param regest_id: Stable input-unit identifier.
        :param attempt_dir: Attempt that owns the retrieval.
        :param payload: Complete result payload.
        :return: Artifact references and legacy-compatible path mapping.
        """
        if condition not in RETRIEVAL_CONDITIONS:
            return {}, {}
        retrieval = _retrieval_artifact_payload(payload)
        if retrieval is None:
            retrieval = self._legacy_retrieval_artifact(
                condition=condition,
                regest_id=regest_id,
            )
        if retrieval is None:
            return {
                "status": "unavailable",
            }, {"retrieval_sidecars_complete": False}
        turtle_text, snapshot, fidelity = retrieval
        retrieval_dir = attempt_dir / "retrieval"
        ttl_path = retrieval_dir / "context.ttl"
        metadata_path = retrieval_dir / "metadata.json"
        ttl_relative = ttl_path.relative_to(self.path_root).as_posix()
        metadata_relative = metadata_path.relative_to(self.path_root).as_posix()
        portable_snapshot = _portable_retrieval_snapshot_v3(
            snapshot,
            payload=payload,
            turtle_text=turtle_text,
            fidelity=fidelity,
            ttl_relative=ttl_relative,
            metadata_relative=metadata_relative,
        )
        _write_text_atomic(ttl_path, turtle_text)
        _write_json_atomic(metadata_path, portable_snapshot)
        references = {
            "context": ArtifactReference.from_path(
                ttl_path,
                run_root=self.path_root,
                media_type="text/turtle",
            ).as_dict(),
            "metadata": ArtifactReference.from_path(
                metadata_path,
                run_root=self.path_root,
                media_type="application/json",
            ).as_dict(),
            "snapshot_fidelity": fidelity,
        }
        return references, {
            "retrieved_ttl": ttl_relative,
            "retrieved_yaml": metadata_relative,
            "retrieval_snapshot_fidelity": fidelity,
            "retrieval_sidecars_complete": True,
        }

    def _legacy_stage1_response(
        self, *, condition: str, regest_id: str
    ) -> str | None:
        """Read an exact pre-v3 Stage-1 sidecar when one survives.

        :param condition: Stable scientific condition identifier.
        :param regest_id: Stable input-unit identifier.
        :return: Exact response text or ``None``.
        """
        safe_id = portable_name(regest_id)
        candidates = sorted(
            self.intermediate_dirs[condition].glob(f"{safe_id}.*.md")
        )
        return (
            candidates[-1].read_text(encoding="utf-8") if candidates else None
        )

    def _legacy_retrieval_artifact(
        self, *, condition: str, regest_id: str
    ) -> tuple[str, dict[str, Any], str] | None:
        """Read an exact native retrieval pair from pre-v3 sidecars.

        :param condition: Stable retrieval condition identifier.
        :param regest_id: Stable input-unit identifier.
        :return: Turtle, metadata, and fidelity when both files survive.
        """
        safe_id = portable_name(regest_id)
        root = self.intermediate_dirs[condition]
        turtle_path = root / f"{safe_id}.retrieved.ttl"
        metadata_path = root / f"{safe_id}.retrieved.yaml"
        if not turtle_path.is_file() or not metadata_path.is_file():
            return None
        metadata = haiu_utils.load_yaml(metadata_path)
        if not isinstance(metadata, dict):
            raise ValueError(
                f"Legacy retrieval metadata is malformed: {metadata_path.name}"
            )
        fidelity = str(metadata.get("snapshot_fidelity") or "legacy_sidecar")
        return turtle_path.read_text(encoding="utf-8"), metadata, fidelity

    def _write_legacy_raw_documents(
        self,
        *,
        condition: str,
        safe_id: str,
        payload: dict[str, Any],
    ) -> RawDocumentPaths:
        """Locate existing pre-v3 sidecars without modifying their evidence.

        :param condition: Stable scientific condition identifier.
        :param safe_id: Portable input-unit identifier.
        :param payload: Complete legacy result payload.
        :return: Available legacy paths for resume compatibility.
        """
        result_dir = self.result_dirs[condition]
        intermediate_dir = self.intermediate_dirs[condition]
        written: RawDocumentPaths = {
            "stage1_capture_status": _stage1_response_capture(payload)[
                "status"
            ],
            "attempt_ttl": {},
        }
        candidates = {
            "yaml": result_dir / f"{safe_id}.yaml",
            "ttl": result_dir / f"{safe_id}.ttl",
            "stage1_metadata": intermediate_dir / f"{safe_id}.json",
            "retrieved_ttl": intermediate_dir / f"{safe_id}.retrieved.ttl",
            "retrieved_yaml": intermediate_dir / f"{safe_id}.retrieved.yaml",
        }
        for label, candidate in candidates.items():
            if candidate.is_file():
                written[label] = candidate.relative_to(
                    self.path_root
                ).as_posix()
        stage1_candidates = sorted(intermediate_dir.glob(f"{safe_id}.*.md"))
        if stage1_candidates:
            written["stage1"] = (
                stage1_candidates[-1].relative_to(self.path_root).as_posix()
            )
        attempt_paths = sorted(result_dir.glob(f"{safe_id}.attempt-*.ttl"))
        written["attempt_ttl"] = {
            path.stem.removeprefix(f"{safe_id}.").replace("-", "_"): (
                path.relative_to(self.path_root).as_posix()
            )
            for path in attempt_paths
        }
        written["retrieval_sidecars_complete"] = all(
            label in written for label in ("retrieved_ttl", "retrieved_yaml")
        )
        return written

    def _existing_prompt_paths(
        self, *, condition: str, safe_id: str
    ) -> dict[str, str]:
        """Locate prompt sidecars belonging to one pre-v3 result.

        :param condition: Stable scientific condition identifier.
        :param safe_id: Portable input-unit identifier.
        :return: Legacy prompt labels and run-relative paths.
        """
        condition_prompt_dir = self.intermediate_dirs[condition]
        prefix = f"{safe_id}_"
        written: dict[str, str] = {}
        for prompt_path in sorted(condition_prompt_dir.glob(f"{safe_id}_*.md")):
            label = prompt_path.stem.removeprefix(prefix)
            written[label] = prompt_path.relative_to(self.path_root).as_posix()
        return written

    def _attempt_state_path(self, *, condition: str, regest_id: str) -> Path:
        return self.layout.checkpoint(condition, regest_id)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _csv_value(value: Any) -> Any:
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _positive_attempt_number(payload: dict[str, Any]) -> int:
    """Read a valid one-based attempt number, defaulting legacy rows to one.

    :param payload: Complete result payload.
    :return: Positive attempt number.
    """
    value = payload.get("attempt")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def _readable_stage_label(value: str) -> str:
    """Normalize provider-specific stage keys for obvious filenames.

    :param value: Source stage key such as ``workflow_stage1``.
    :return: Stable label such as ``stage-1``.
    """
    normalized = value.removeprefix("workflow_").replace("_", "-")
    if normalized in {"stage1", "stage-1"}:
        return "stage-1"
    if normalized in {"stage2", "stage-2"}:
        return "stage-2"
    return portable_name(normalized).replace("_", "-")


def _paths_from_v3_record(
    record: dict[str, Any],
) -> tuple[RawDocumentPaths, dict[str, str]]:
    """Recover compatibility paths from one nested terminal record.

    :param record: Parsed schema-v3 terminal record.
    :return: Raw-document and prompt path mappings.
    """
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Schema-v3 record has no artifact index.")
    upstream = artifacts.get("upstream_result")
    upstream_path = _artifact_path(upstream)
    metadata_path = (
        str(Path(upstream_path).with_name("metadata.json"))
        if upstream_path is not None
        else None
    )
    stage1 = artifacts.get("stage1_response")
    stage2 = artifacts.get("stage2_response")
    stage1_path = _artifact_path(stage1)
    stage2_path = _artifact_path(stage2)
    stage1_status = (
        str(stage1.get("status") or "unavailable")
        if isinstance(stage1, dict)
        else "unavailable"
    )
    if stage1_path is not None:
        stage1_status = "captured"
    attempts = record.get("attempts")
    attempt_number = (
        attempts.get("attempt") if isinstance(attempts, dict) else None
    )
    attempt_label = (
        str(attempt_number)
        if isinstance(attempt_number, int) and attempt_number > 0
        else "1"
    )
    raw_paths: RawDocumentPaths = {
        "yaml": None,
        "stage1": stage1_path,
        "stage1_metadata": metadata_path,
        "stage1_capture_status": stage1_status,
        "ttl": stage2_path,
        "attempt_ttl": (
            {f"attempt_{attempt_label}": stage2_path}
            if stage2_path is not None
            else {}
        ),
    }
    retrieval = artifacts.get("retrieval")
    if isinstance(retrieval, dict):
        raw_paths.update(
            {
                "retrieved_ttl": _artifact_path(retrieval.get("context")),
                "retrieved_yaml": _artifact_path(retrieval.get("metadata")),
                "retrieval_snapshot_fidelity": retrieval.get(
                    "snapshot_fidelity"
                ),
                "retrieval_sidecars_complete": bool(
                    _artifact_path(retrieval.get("context"))
                    and _artifact_path(retrieval.get("metadata"))
                ),
            }
        )
    prompts = artifacts.get("prompts")
    prompt_paths: dict[str, str] = {}
    if isinstance(prompts, dict):
        for label, reference in prompts.items():
            artifact_path = _artifact_path(reference)
            if artifact_path is not None:
                prompt_paths[compatibility_prompt_key(str(label))] = (
                    artifact_path
                )
    return raw_paths, prompt_paths


def _artifact_path(value: Any) -> str | None:
    """Read a portable path from an optional artifact reference.

    :param value: Candidate artifact-reference mapping.
    :return: Non-empty path or ``None``.
    """
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    return path if isinstance(path, str) and path else None


def _frozen_regest_payload(regest: RegestText) -> dict[str, Any]:
    """Serialize one direct-condition input with a content digest.

    :param regest: Raw regest copied during preflight.
    :return: Portable JSON artifact payload.
    """
    content = {
        "regest_id": regest.regest_id,
        "header": regest.header,
        "subentries": list(regest.subentries),
    }
    content_json = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "source": "preflight_frozen_raw_regest_snapshot",
        **content,
        "content_sha256": hashlib.sha256(
            content_json.encode("utf-8")
        ).hexdigest(),
    }


def _frozen_regest_from_payload(payload: Any) -> RegestText:
    """Validate and restore one frozen direct-condition raw regest.

    :param payload: Decoded frozen raw-regest JSON artifact.
    :return: Exact prompt input used by the standalone condition.
    :raises ValueError: If a snapshot cannot prove its content integrity.
    """
    if not isinstance(payload, dict):
        raise ValueError("Frozen raw-regest snapshot is not a JSON object.")
    regest_id = payload.get("regest_id")
    header = payload.get("header")
    subentries = payload.get("subentries")
    if (
        not isinstance(regest_id, str)
        or not isinstance(header, str)
        or not isinstance(subentries, list)
        or not all(isinstance(value, str) for value in subentries)
    ):
        raise ValueError(
            "Frozen raw-regest snapshot has an invalid text shape."
        )
    regest = RegestText(
        regest_id=regest_id,
        header=header,
        subentries=tuple(subentries),
    )
    expected_digest = payload.get("content_sha256")
    observed_digest = _frozen_regest_payload(regest)["content_sha256"]
    if expected_digest != observed_digest:
        raise ValueError(
            "Frozen raw-regest snapshot content digest does not match."
        )
    return regest


def _raw_turtle_text(payload: dict[str, Any]) -> str:
    """Return only the unmodified captured Stage 2 Turtle response.

    A separate TBox/ABox representation is useful for DMW persistence, but
    concatenating those fields cannot prove the original model bytes. The raw
    Turtle sidecar is therefore written only from the explicit capture field.

    :param payload: Authoritative raw JSON result.
    :return: Captured or reconstructed Turtle text, or an empty string.
    """
    raw_output = payload.get("raw_ttl_output")
    if isinstance(raw_output, str) and raw_output:
        return raw_output
    return ""


def _stage1_response_capture(payload: dict[str, Any]) -> dict[str, str | None]:
    """Recover the exact Stage-1 reply only from preserved raw evidence.

    Success records produced before the explicit capture field used
    ``explanation`` for the exact OPA Designer response. Workflow failures may
    carry a newer upstream ``designerResponse`` diagnostic. When neither is
    present, a prompt, token count, or parsed Turtle cannot reconstruct the
    response bytes and the caller must record that absence instead.

    :param payload: Authoritative raw experiment result.
    :return: Capture status, source, exact output when available, and a reason
        when the upstream response was not preserved.
    """
    explicit_output = payload.get("raw_stage1_output")
    if isinstance(explicit_output, str) and explicit_output:
        source = payload.get("raw_stage1_output_source")
        return {
            "status": "captured",
            "source": (
                source
                if isinstance(source, str) and source
                else "explicit_raw_stage1_output"
            ),
            "output": explicit_output,
            "reason": None,
        }

    candidates = (
        ("reconstructed_from_explanation", payload.get("explanation")),
        (
            "reconstructed_from_workflow_review",
            _nested_text(
                payload,
                "raw_response",
                "ontology_review",
                "data",
                "explanation",
            ),
        ),
        (
            "reconstructed_from_workflow_debug",
            _nested_text(
                payload,
                "raw_response",
                "debug_output",
                "explanation",
            ),
        ),
        (
            "upstream_designer_response",
            _nested_text(
                payload,
                "raw_response",
                "detail",
                "generation_diagnostics",
                "designerResponse",
            ),
        ),
        (
            "upstream_designer_response",
            _nested_text(payload, "raw_response", "detail", "designerResponse"),
        ),
    )
    for source, output in candidates:
        if isinstance(output, str) and output:
            return {
                "status": "captured",
                "source": source,
                "output": output,
                "reason": None,
            }
    return {
        "status": "unavailable",
        "source": "not_returned_by_preserved_raw_result",
        "output": None,
        "reason": (
            "The preserved result contains no exact Stage-1 reply. Prompts, "
            "usage metadata, and Stage-2 Turtle are insufficient to recreate "
            "it without fabricating model output."
        ),
    }


def _nested_text(payload: dict[str, Any], *keys: str) -> str | None:
    """Read one text leaf from a nested JSON object without coercion.

    :param payload: JSON object to traverse.
    :param keys: Ordered object keys that locate the candidate value.
    :return: String leaf, or ``None`` when the path is absent or non-textual.
    """
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, str) else None


def _retrieval_artifact_payload(
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], str] | None:
    """Return explicitly captured native Haiu retrieval evidence.

    A Stage-1 prompt can contain Turtle text, but it cannot demonstrate the
    original retrieval snapshot or prove that the text was exported before the
    model call. Publication runs therefore require OPA's native snapshot.

    :param payload: Authoritative workflow result.
    :return: Turtle, YAML payload, and fidelity label when explicitly captured.
    """
    ontology_context = payload.get("ontology_context")
    if not isinstance(ontology_context, dict):
        ontology_context = {}
    retrieved_turtle = ontology_context.get("retrieved_turtle")
    retrieval_snapshot = ontology_context.get("retrieval_snapshot")
    if not (
        isinstance(retrieved_turtle, str)
        and retrieved_turtle.strip()
        and isinstance(retrieval_snapshot, dict)
        and retrieval_snapshot.get("snapshot_fidelity") == "native_full_graph"
    ):
        return None
    return retrieved_turtle, deepcopy(retrieval_snapshot), "native_full_graph"


def _portable_retrieval_snapshot_v3(
    snapshot: dict[str, Any],
    *,
    payload: dict[str, Any],
    turtle_text: str,
    fidelity: str,
    ttl_relative: str,
    metadata_relative: str,
) -> dict[str, Any]:
    """Attach portable artifact provenance to retrieval metadata.

    :param snapshot: Native or reconstructed retrieval payload.
    :param payload: Authoritative workflow result.
    :param turtle_text: Exact context sent to the model.
    :param fidelity: Declared snapshot fidelity.
    :param ttl_relative: Run-relative Turtle path.
    :param metadata_relative: Run-relative JSON metadata path.
    :return: Portable JSON payload without private host paths.
    """
    portable = deepcopy(snapshot)
    portable.pop("workdir", None)
    portable.update(
        {
            "snapshot_fidelity": fidelity,
            "source": str(
                portable.get("source")
                or (
                    "opa_haiu_native_snapshot"
                    if fidelity == "native_full_graph"
                    else "dmw_stage1_prompt"
                )
            ),
            "condition": str(payload.get("condition") or ""),
            "regest_id": str(payload.get("regest_id") or ""),
            "export_base": ttl_relative.removesuffix(".ttl"),
            "metadata_path": metadata_relative,
            "turtle_export_path": ttl_relative,
            "retrieved_turtle_chars": len(turtle_text),
            "retrieved_turtle_sha256": hashlib.sha256(
                turtle_text.encode("utf-8")
            ).hexdigest(),
        }
    )
    return portable


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace a text artifact only after its complete content is on disk.

    :param path: Final artifact path.
    :param content: Complete UTF-8 text.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    """Replace a binary artifact only after its complete content is on disk.

    :param path: Final artifact path.
    :param content: Complete binary content.
    :return: None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_bytes(content)
    temp_path.replace(path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace a JSON artifact only after serialization completes.

    :param path: Final artifact path.
    :param payload: JSON-compatible result payload.
    :return: ``None``.
    """
    _write_text_atomic(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object with an artifact-specific error.

    :param path: JSON artifact to parse.
    :return: Parsed object.
    :raises ValueError: If the JSON root is not an object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def _replace_hardlink(source: Path, target: Path) -> None:
    """Atomically point a second user-facing path at existing evidence.

    :param source: Complete source artifact in the same filesystem.
    :param target: Final alias path.
    :return: ``None``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    if temporary.exists():
        temporary.unlink()
    os.link(source, temporary)
    temporary.replace(target)
