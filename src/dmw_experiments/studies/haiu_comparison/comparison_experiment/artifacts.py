"""Artifact writing for ontology comparison outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import haiu.utils as ut

from dmw_experiments.studies.haiu_comparison.comparison_experiment.metrics import (
    summarize_rows,
)
from dmw_experiments.studies.haiu_comparison.comparison_experiment.models import (
    ExperimentResult,
)
from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.models import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
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
    """Write one execution's evidence into the flat run-directory contract.

    :param output_dir: Top-level ``raw-<execution>`` directory.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        if not output_dir.name.startswith("raw-"):
            raise ValueError(
                "ArtifactWriter output must be a raw-<execution> directory."
            )
        self.execution_name = output_dir.name.removeprefix("raw-")
        self.run_root = output_dir.parent
        self.path_root = self.run_root
        self.intermediate_dirs = {
            condition: output_dir / f"intermediates-{condition}"
            for condition in CONDITIONS
        }
        self.result_dirs = {
            condition: output_dir / f"result-{condition}"
            for condition in CONDITIONS
        }
        self.raw_annotation_dir = self.intermediate_dirs[
            "workflow_full_ontology"
        ]
        self.annotation_mirror_dir = self.intermediate_dirs["workflow_rag"]
        self.normalized_dir = self.run_root / "analysis" / "intermediate"
        self.diagnostics_dir = self.run_root / "analysis" / "diagnostics"
        self.environment_dir = self.run_root / "environment"
        self.amendment_dir = self.environment_dir / (
            f"{self.execution_name}-amendments"
        )
        self.superseded_dir = self.environment_dir / (
            f"{self.execution_name}-superseded"
        )
        self.provenance_dir = (
            self.intermediate_dirs["haiu_rag_ontologizer"] / "provenance"
        )
        for path in (
            *self.intermediate_dirs.values(),
            *self.result_dirs.values(),
            self.normalized_dir,
            self.diagnostics_dir,
            self.environment_dir,
            self.amendment_dir,
            self.superseded_dir,
            self.provenance_dir,
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
            target = self.provenance_dir / f"{_safe_name(label)}{suffix}"
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
        path = self.provenance_dir / "provenance_manifest.json"
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
        manifest_path = self.provenance_dir / "provenance_manifest.json"
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
        snapshot_dir = self.provenance_dir / "raw_regests"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        records: dict[str, dict[str, str]] = {}
        regests: dict[str, RegestText] = {}
        for regest_id in regest_ids:
            path = snapshot_dir / f"{_safe_name(regest_id)}.json"
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
        manifest_path = self.provenance_dir / "raw_regests_manifest.json"
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

    def write_result(self, result: ExperimentResult) -> dict[str, Any]:
        """Write per-result artifacts and return the normalized row.

        :param result: Condition result.
        :return: Normalized row with artifact paths.
        """
        condition_raw_dir = self.result_dirs[result.condition]
        condition_prompt_dir = self.intermediate_dirs[result.condition]
        safe_id = _safe_name(result.regest_id)
        raw_path = condition_raw_dir / f"{safe_id}.json"
        raw_json = json.dumps(
            result.payload, indent=2, ensure_ascii=False, default=str
        )
        _write_text_atomic(
            raw_path,
            raw_json,
        )
        prompt_paths = self._write_prompts(
            condition_prompt_dir=condition_prompt_dir,
            safe_id=safe_id,
            prompts=result.payload.get("prompts"),
        )
        raw_document_paths = self._write_raw_documents(
            condition=result.condition,
            safe_id=safe_id,
            payload=json.loads(raw_json),
        )
        return self._normalized_row(
            payload=result.payload,
            condition=result.condition,
            regest_id=result.regest_id,
            raw_path=raw_path,
            raw_document_paths=raw_document_paths,
            prompt_paths=prompt_paths,
        )

    def load_existing_rows(self) -> list[dict[str, Any]]:
        """Rebuild normalized rows from authoritative per-result artifacts.

        The raw artifact is written before aggregate checkpoints. Reading it
        directly recovers a result when a process stopped between those two
        writes.

        :return: Normalized rows recovered from the run directory.
        """
        rows: list[dict[str, Any]] = []
        for condition, result_dir in self.result_dirs.items():
            for raw_path in sorted(result_dir.glob("*.json")):
                rows.append(
                    self._row_from_existing_result(
                        raw_path=raw_path,
                        condition=condition,
                    )
                )
        return rows

    def _row_from_existing_result(
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
        safe_id = _safe_name(regest_id)
        raw_document_paths = self._write_raw_documents(
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
        """Backfill Stage-1, Turtle, and YAML documents from raw JSON artifacts.

        This method only writes derived per-result documents. It does not
        replace aggregate JSONL, CSV, or summary checkpoints, so it is safe to
        use while the experiment runner is active.

        :return: Counts of written derived documents and unavailable Stage-1
            captures.
        """
        counts = {
            "yaml": 0,
            "ttl": 0,
            "stage1": 0,
            "stage1_unavailable": 0,
            "retrieved_yaml": 0,
            "retrieved_ttl": 0,
        }
        for condition, result_dir in self.result_dirs.items():
            for raw_path in sorted(result_dir.glob("*.json")):
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"Raw result is not a JSON object: "
                        f"{raw_path.relative_to(self.path_root)}"
                    )
                regest_id = str(payload.get("regest_id") or raw_path.stem)
                written = self._write_raw_documents(
                    condition=condition,
                    safe_id=_safe_name(regest_id),
                    payload=payload,
                )
                counts["yaml"] += 1
                counts["ttl"] += int("ttl" in written)
                counts["stage1"] += int("stage1" in written)
                counts["stage1_unavailable"] += int(
                    written["stage1_capture_status"] == "unavailable"
                )
                counts["retrieved_yaml"] += int("retrieved_yaml" in written)
                counts["retrieved_ttl"] += int("retrieved_ttl" in written)
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
        row["raw_stage1_metadata_artifact_path"] = raw_document_paths[
            "stage1_metadata"
        ]
        row["attempt_ttl_artifact_paths"] = raw_document_paths.get(
            "attempt_ttl"
        )
        row["raw_yaml_artifact_path"] = raw_document_paths["yaml"]
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
        path = self.raw_annotation_dir / f"{_safe_name(regest_id)}.json"
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
        """Persist the exact accepted annotation in JSON and YAML.

        :param regest_id: Datamodel regest identifier.
        :param payload: Portable raw annotation and preparation provenance.
        :return: Run-relative JSON and YAML paths.
        """
        safe_id = _safe_name(regest_id)
        json_path = self.raw_annotation_dir / f"{safe_id}.json"
        yaml_path = self.raw_annotation_dir / f"{safe_id}.yaml"
        _write_text_atomic(
            json_path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        _write_yaml_atomic(yaml_path, payload)
        mirror_json = self.annotation_mirror_dir / json_path.name
        mirror_yaml = self.annotation_mirror_dir / yaml_path.name
        shutil.copy2(json_path, mirror_json)
        shutil.copy2(yaml_path, mirror_yaml)
        return {
            "json": json_path.relative_to(self.path_root).as_posix(),
            "yaml": yaml_path.relative_to(self.path_root).as_posix(),
            "workflow_rag_json": mirror_json.relative_to(
                self.path_root
            ).as_posix(),
            "workflow_rag_yaml": mirror_yaml.relative_to(
                self.path_root
            ).as_posix(),
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
        path = self.raw_annotation_dir / (
            f"{_safe_name(regest_id)}.annotation-attempt.json"
        )
        _write_text_atomic(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        shutil.copy2(path, self.annotation_mirror_dir / path.name)
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
        path = self.raw_annotation_dir / (
            f"{_safe_name(regest_id)}.annotation-attempt.json"
        )
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
        safe_id = _safe_name(regest_id)
        source = self.raw_annotation_dir / f"{safe_id}.annotation-attempt.json"
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
        path = self.environment_dir / f"{self.execution_name}-run-manifest.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                raise ValueError(
                    "Run manifest differs from the requested experiment "
                    "configuration."
                )
            return path
        if has_existing_results:
            raise ValueError(
                "Cannot safely resume raw results without a run manifest."
            )
        _write_text_atomic(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        )
        return path

    def load_run_manifest(self) -> dict[str, Any]:
        """Load the immutable base identity required for an amendment.

        :return: Parsed run-manifest payload.
        :raises ValueError: If no valid immutable base identity exists.
        """
        path = self.environment_dir / f"{self.execution_name}-run-manifest.json"
        if not path.is_file():
            raise ValueError("Cannot amend a run without its run manifest.")
        payload = json.loads(path.read_text(encoding="utf-8"))
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
        safe_id = _safe_name(amendment_id)
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
        safe_id = _safe_name(regest_id)
        archive_root = self.superseded_dir / amendment_id
        index_path = archive_root / "archive_index.json"
        key = f"{condition}/{safe_id}"
        raw_path = self.result_dirs[condition] / f"{safe_id}.json"
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
        result_dir = self.result_dirs[condition]
        intermediate_dir = self.intermediate_dirs[condition]
        patterns = (
            result_dir / f"{safe_id}.json",
            result_dir / f"{safe_id}.yaml",
            result_dir / f"{safe_id}.ttl",
            intermediate_dir / f"{safe_id}.attempt.json",
        )
        paths = [path for path in patterns if path.is_file()]
        for directory, pattern in (
            (result_dir, f"{safe_id}.attempt-*.ttl"),
            (intermediate_dir, f"{safe_id}.*"),
            (intermediate_dir, f"{safe_id}_*"),
        ):
            if directory.is_dir():
                paths.extend(sorted(directory.glob(pattern)))
        return sorted({path for path in paths if path.is_file()})

    def _write_prompts(
        self,
        *,
        condition_prompt_dir: Path,
        safe_id: str,
        prompts: Any,
    ) -> dict[str, str]:
        if not isinstance(prompts, dict):
            return {}
        written: dict[str, str] = {}
        for stage, bundle in prompts.items():
            if not isinstance(bundle, dict):
                continue
            stage_label = _safe_name(str(stage))
            for role in ("system", "user"):
                text = str(bundle.get(role) or "")
                if not text:
                    continue
                path = (
                    condition_prompt_dir / f"{safe_id}_{stage_label}_{role}.md"
                )
                _write_text_atomic(path, text)
                written[f"{stage_label}_{role}"] = path.relative_to(
                    self.path_root
                ).as_posix()
        return written

    def _existing_prompt_paths(
        self, *, condition: str, safe_id: str
    ) -> dict[str, str]:
        condition_prompt_dir = self.intermediate_dirs[condition]
        prefix = f"{safe_id}_"
        written: dict[str, str] = {}
        for path in sorted(condition_prompt_dir.glob(f"{safe_id}_*.md")):
            label = path.stem.removeprefix(prefix)
            written[label] = path.relative_to(self.path_root).as_posix()
        return written

    def _write_raw_documents(
        self,
        *,
        condition: str,
        safe_id: str,
        payload: dict[str, Any],
    ) -> RawDocumentPaths:
        condition_result_dir = self.result_dirs[condition]
        condition_intermediate_dir = self.intermediate_dirs[condition]

        written: RawDocumentPaths = {}
        yaml_path = condition_result_dir / f"{safe_id}.yaml"
        _write_yaml_atomic(yaml_path, payload)
        written["yaml"] = yaml_path.relative_to(self.path_root).as_posix()

        turtle_text = _raw_turtle_text(payload)
        ttl_path = condition_result_dir / f"{safe_id}.ttl"
        if turtle_text:
            _write_text_atomic(ttl_path, turtle_text)
            written["ttl"] = ttl_path.relative_to(self.path_root).as_posix()
        elif ttl_path.exists():
            ttl_path.unlink()
        written["attempt_ttl"] = self._write_attempt_turtle_documents(
            condition_ttl_dir=condition_result_dir,
            safe_id=safe_id,
            payload=payload,
        )
        written.update(
            self._write_stage1_documents(
                condition_stage1_dir=condition_intermediate_dir,
                safe_id=safe_id,
                payload=payload,
            )
        )
        written.update(
            self._write_retrieval_documents(
                condition=condition,
                safe_id=safe_id,
                payload=payload,
            )
        )
        return written

    def _write_stage1_documents(
        self,
        *,
        condition_stage1_dir: Path,
        safe_id: str,
        payload: dict[str, Any],
    ) -> RawDocumentPaths:
        """Materialize exact or transparently unavailable Stage-1 evidence.

        The Stage-1 model reply is the conceptual plan supplied to Turtle
        generation. Older workflow artifacts stored it under ``explanation``
        without an explicit capture label, while some failed upstream calls
        preserved no reply at all. This sidecar keeps the reconstructed source
        explicit and never fabricates unavailable model text.

        :param condition_stage1_dir: Condition-specific Stage-1 output directory.
        :param safe_id: Portable regest identifier.
        :param payload: Authoritative raw observation.
        :return: Relative paths and availability metadata for the Stage-1 reply.
        """
        capture = _stage1_response_capture(payload)
        metadata_path = condition_stage1_dir / f"{safe_id}.json"
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "capture_status": capture["status"],
            "source": capture["source"],
            "raw_artifact_path": (
                f"raw-{self.execution_name}/result-"
                f"{_safe_name(str(payload.get('condition') or ''))}/"
                f"{safe_id}.json"
            ),
        }
        written: RawDocumentPaths = {
            "stage1_metadata": metadata_path.relative_to(
                self.path_root
            ).as_posix(),
            "stage1_capture_status": capture["status"],
        }
        output = capture["output"]
        if output is None:
            metadata["unavailable_reason"] = capture["reason"]
            _write_text_atomic(
                metadata_path,
                json.dumps(metadata, indent=2, ensure_ascii=False),
            )
            return written

        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        output_path = condition_stage1_dir / f"{safe_id}.{digest[:12]}.md"
        metadata.update(
            {
                "content_sha256": digest,
                "characters": len(output),
                "output_artifact_path": output_path.relative_to(
                    self.path_root
                ).as_posix(),
            }
        )
        _write_text_atomic(output_path, output)
        _write_text_atomic(
            metadata_path,
            json.dumps(metadata, indent=2, ensure_ascii=False),
        )
        written["stage1"] = metadata["output_artifact_path"]
        return written

    def _write_attempt_turtle_documents(
        self,
        *,
        condition_ttl_dir: Path,
        safe_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """Persist raw Stage-2 text from retained upstream retry attempts.

        :param condition_ttl_dir: Condition-specific output directory.
        :param safe_id: Portable regest identifier.
        :param payload: Authoritative normalized observation.
        :return: Attempt labels mapped to relative Turtle artifact paths.
        """
        attempts = payload.get("generation_attempts")
        if not isinstance(attempts, list):
            return {}
        written: dict[str, str] = {}
        for index, attempt in enumerate(attempts, start=1):
            if not isinstance(attempt, dict):
                continue
            diagnostics = attempt.get("diagnostics")
            if not isinstance(diagnostics, dict):
                continue
            turtle_text = diagnostics.get("rawTtlOutput")
            if not isinstance(turtle_text, str) or not turtle_text:
                continue
            attempt_number = attempt.get("attempt")
            label = (
                str(attempt_number)
                if isinstance(attempt_number, int) and attempt_number > 0
                else str(index)
            )
            path = condition_ttl_dir / f"{safe_id}.attempt-{label}.ttl"
            _write_text_atomic(path, turtle_text)
            written[f"attempt_{label}"] = path.relative_to(
                self.path_root
            ).as_posix()
        return written

    def _write_retrieval_documents(
        self,
        *,
        condition: str,
        safe_id: str,
        payload: dict[str, Any],
    ) -> RawDocumentPaths:
        if condition not in RETRIEVAL_CONDITIONS:
            return {}

        retrieval = _retrieval_artifact_payload(payload)
        if retrieval is None:
            # > A failed retrieval must remain observable as a terminal raw
            # result. The analysis exporter rejects the missing sidecars for a
            # publication run, rather than losing the failure at write time.
            return {"retrieval_sidecars_complete": False}
        turtle_text, snapshot, fidelity = retrieval
        # Keep retrieval exports condition-scoped.  This prevents a direct
        # and workflow observation for the same regest from overwriting one
        # another and makes the provider path explicit in raw artifacts.
        retrieval_dir = self.intermediate_dirs[condition]
        ttl_path = retrieval_dir / f"{safe_id}.retrieved.ttl"
        yaml_path = retrieval_dir / f"{safe_id}.retrieved.yaml"
        ttl_relative = ttl_path.relative_to(self.path_root).as_posix()
        yaml_relative = yaml_path.relative_to(self.path_root).as_posix()
        snapshot = _portable_retrieval_snapshot(
            snapshot,
            payload=payload,
            turtle_text=turtle_text,
            fidelity=fidelity,
            ttl_relative=ttl_relative,
            yaml_relative=yaml_relative,
        )
        _write_text_atomic(ttl_path, turtle_text)
        _write_yaml_atomic(yaml_path, snapshot)
        return {
            "retrieved_ttl": ttl_relative,
            "retrieved_yaml": yaml_relative,
            "retrieval_snapshot_fidelity": fidelity,
            "retrieval_sidecars_complete": True,
        }

    def _attempt_state_path(self, *, condition: str, regest_id: str) -> Path:
        return self.intermediate_dirs[condition] / (
            f"{_safe_name(regest_id)}.attempt.json"
        )


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


def _safe_name(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in value
    )


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


def _portable_retrieval_snapshot(
    snapshot: dict[str, Any],
    *,
    payload: dict[str, Any],
    turtle_text: str,
    fidelity: str,
    ttl_relative: str,
    yaml_relative: str,
) -> dict[str, Any]:
    """Attach portable artifact provenance to one retrieval YAML payload.

    :param snapshot: Native or reconstructed retrieval payload.
    :param payload: Authoritative workflow result.
    :param turtle_text: Exact context sent to the model.
    :param fidelity: Declared snapshot fidelity.
    :param ttl_relative: Run-relative Turtle path.
    :param yaml_relative: Run-relative YAML path.
    :return: Portable YAML payload without private host paths.
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
            "export_yaml_path": yaml_relative,
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
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    """Replace a binary artifact only after its complete content is on disk.

    :param path: Final artifact path.
    :param content: Complete binary content.
    :return: None.
    """
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_bytes(content)
    temp_path.replace(path)


def _write_yaml_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace a YAML artifact only after serialization completes.

    :param path: Final artifact path.
    :param payload: JSON-compatible result payload.
    """
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    ut.export_yaml(payload, temp_path)
    temp_path.replace(path)
