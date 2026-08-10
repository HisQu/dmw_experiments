"""Migrate legacy flat evidence into the per-unit artifact layout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import haiu.utils as haiu_utils

from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ARTIFACT_SCHEMA_VERSION,
    ExecutionArtifactLayout,
    portable_name,
)
from dmw_experiments.studies.haiu_comparison.model.artifact_records import (
    load_upstream_payload,
)
from dmw_experiments.studies.haiu_comparison.data_collection.artifacts import (
    ArtifactWriter,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    CONDITIONS,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    REPOSITORY_ROOT,
)

SOURCE_SCHEMA_VERSION = 2
MIGRATION_RECORD_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ArtifactMigrationReport:
    """Summarize one completed execution-layout migration.

    :param execution: Provider execution whose evidence was migrated.
    :param source_schema_version: Layout version found before migration.
    :param target_schema_version: Layout version exposed after migration.
    :param terminal_cells: Terminal result bundles verified after conversion.
    :param shared_annotations: Shared annotation bundles recovered.
    :param checkpoints: Cell checkpoints moved into unit directories.
    :param failed_attempts: Attempt directories explicitly marked ``-failed``.
    :param backup: Run-relative recovery snapshot path.
    :param record: Run-relative migration-record path.
    """

    execution: str
    source_schema_version: int
    target_schema_version: int
    terminal_cells: int
    shared_annotations: int
    checkpoints: int
    failed_attempts: int
    backup: str
    record: str


class ArtifactLayoutMigrator:
    """Convert one stopped provider execution without changing observations.

    The migrator first hard-links every legacy source file into a recovery
    snapshot and records its digest. It then writes the schema-v3 view,
    verifies every compressed source payload byte-for-byte, and only then
    removes legacy duplicates from the active provider directory.

    :param run_root: Complete copied run directory.
    :param execution: Provider execution such as ``academiccloud``.
    """

    def __init__(self, *, run_root: Path, execution: str) -> None:
        self.run_root = run_root.expanduser().resolve()
        self.execution = execution
        self.layout = ExecutionArtifactLayout(
            self.run_root / f"raw-{execution}"
        )
        self.environment = self.run_root / "environment"
        self.legacy_manifest = (
            self.environment / f"{execution}-run-manifest.json"
        )
        self.migration_record = (
            self.environment / f"{execution}-artifact-layout-migration.json"
        )
        self.backup = (
            self.environment
            / "artifact-migration-backups"
            / f"{execution}-schema-v2"
        )

    def migrate(self) -> ArtifactMigrationReport:
        """Perform an idempotent, verified schema-v2 to schema-v3 migration.

        :return: Counts and recovery paths for the completed conversion.
        :raises ValueError: If the source is incomplete, already ambiguous, or
            fails any content-integrity check.
        """
        if self.migration_record.is_file():
            return self._load_completed_report()
        if self.layout.manifest.is_file():
            raise ValueError(
                "Provider output already has a schema-v3 manifest but no "
                "completed migration record. Inspect it before retrying."
            )
        if not self.legacy_manifest.is_file():
            raise ValueError(
                "Legacy execution manifest is missing: "
                f"{self.legacy_manifest.name}"
            )
        self._require_no_retry_pending_attempts()

        # !! Refuse a dirty or uncommitted migration harness before creating
        # !! either the recovery snapshot or any schema-v3 output.
        target_harness = _clean_harness_identity()
        source_harness = self._source_harness_identity()

        legacy_results = tuple(self.layout.iter_legacy_result_records())
        if not legacy_results:
            raise ValueError(
                "No legacy terminal results are available to migrate."
            )
        debug_paths = self._referenced_debug_paths(legacy_results)
        source_inventory = self._source_inventory(debug_paths)
        self._create_recovery_snapshot(source_inventory)

        provenance, raw_regest_snapshot = self._migrate_provenance()
        self._migrate_run_manifest(
            provenance=provenance,
            raw_regest_snapshot=raw_regest_snapshot,
        )
        annotations = self._migrate_annotations()
        checkpoints = self._migrate_checkpoints()

        writer = ArtifactWriter(self.layout.output)
        writer.materialize_existing_raw_documents()
        terminal_cells, failed_attempts = self._verify_results(legacy_results)
        writer.write_final_outputs(writer.load_existing_rows())
        self._verify_recovery_snapshot(source_inventory)

        self._remove_legacy_view(debug_paths)
        record_payload = {
            "schema_version": MIGRATION_RECORD_SCHEMA_VERSION,
            "record_type": "haiu_comparison_artifact_layout_migration",
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "execution": self.execution,
            "source_schema_version": SOURCE_SCHEMA_VERSION,
            "target_schema_version": ARTIFACT_SCHEMA_VERSION,
            "source_harness": source_harness,
            "target_harness": target_harness,
            "terminal_cells": terminal_cells,
            "shared_annotations": annotations,
            "checkpoints": checkpoints,
            "failed_attempts": failed_attempts,
            "source_file_count": len(source_inventory),
            "source_inventory_sha256": _inventory_digest(source_inventory),
            "backup": self.backup.relative_to(self.run_root).as_posix(),
        }
        _write_json_atomic(self.migration_record, record_payload)
        return self._report_from_record(record_payload)

    def _require_no_retry_pending_attempts(self) -> None:
        """Refuse to misclassify a provisional result as a terminal cell.

        Schema v2 temporarily wrote a result JSON before retrying. Its
        checkpoint is the only unambiguous signal that the same matrix cell
        is still open. Migration therefore waits for the retry chain to reach
        a terminal state instead of promoting that temporary failure.

        :return: ``None`` when no checkpoint requests a retry.
        :raises ValueError: If a selected cell is still retry-pending.
        """
        pending: list[str] = []
        for condition in CONDITIONS:
            root = self.layout.intermediate_condition(condition)
            for checkpoint in sorted(root.glob("*.attempt.json")):
                payload = _load_json_object(checkpoint)
                if payload.get("status") == "retry_pending":
                    pending.append(
                        f"{condition}/{checkpoint.name.removesuffix('.attempt.json')}"
                    )
        if pending:
            raise ValueError(
                "Artifact migration requires terminal retry chains; still "
                "retry-pending: " + ", ".join(pending)
            )

    def _load_completed_report(self) -> ArtifactMigrationReport:
        """Validate and return an earlier successful migration.

        :return: Stable report reconstructed from the immutable record.
        :raises ValueError: If the record or target layout is incomplete.
        """
        payload = _load_json_object(self.migration_record)
        if (
            payload.get("status") != "completed"
            or payload.get("execution") != self.execution
            or payload.get("target_schema_version") != ARTIFACT_SCHEMA_VERSION
            or not self.layout.manifest.is_file()
            or not self.backup.is_dir()
        ):
            raise ValueError(
                "Artifact migration record is incomplete or invalid."
            )
        return self._report_from_record(payload)

    def _report_from_record(
        self, payload: dict[str, Any]
    ) -> ArtifactMigrationReport:
        """Build the public report from one validated record.

        :param payload: Completed migration record.
        :return: Typed migration summary.
        """
        return ArtifactMigrationReport(
            execution=self.execution,
            source_schema_version=int(payload["source_schema_version"]),
            target_schema_version=int(payload["target_schema_version"]),
            terminal_cells=int(payload["terminal_cells"]),
            shared_annotations=int(payload["shared_annotations"]),
            checkpoints=int(payload["checkpoints"]),
            failed_attempts=int(payload["failed_attempts"]),
            backup=str(payload["backup"]),
            record=self.migration_record.relative_to(self.run_root).as_posix(),
        )

    def _source_inventory(
        self, debug_paths: tuple[Path, ...]
    ) -> dict[str, str]:
        """Hash every source file retained by the recovery snapshot.

        :param debug_paths: DMW-owned duplicate files referenced by results.
        :return: Run-relative source paths mapped to SHA-256 digests.
        """
        sources = [
            path for path in self.layout.output.rglob("*") if path.is_file()
        ]
        sources.extend((self.legacy_manifest, *debug_paths))
        return {
            path.relative_to(self.run_root).as_posix(): _sha256_file(path)
            for path in sorted(set(sources))
        }

    def _create_recovery_snapshot(self, inventory: dict[str, str]) -> None:
        """Retain exact source files before creating or deleting active paths.

        :param inventory: Run-relative source paths and expected digests.
        :return: ``None`` after the snapshot and inventory are durable.
        :raises ValueError: If an unrecorded partial snapshot already exists.
        """
        if self.backup.exists():
            raise ValueError(
                "A partial artifact migration backup already exists: "
                f"{self.backup.relative_to(self.run_root)}"
            )
        for relative in inventory:
            source = self.run_root / relative
            target = self.backup / "files" / relative
            _link_or_copy(source, target)
        _write_json_atomic(
            self.backup / "inventory.json",
            {
                "schema_version": 1,
                "source_schema_version": SOURCE_SCHEMA_VERSION,
                "execution": self.execution,
                "files": inventory,
            },
        )
        self._verify_recovery_snapshot(inventory)

    def _verify_recovery_snapshot(self, inventory: dict[str, str]) -> None:
        """Confirm every snapshotted byte still matches its source digest.

        :param inventory: Run-relative source paths and expected digests.
        :return: ``None`` when the snapshot is complete.
        :raises ValueError: If a backup member is absent or changed.
        """
        for relative, expected in inventory.items():
            backup_path = self.backup / "files" / relative
            if (
                not backup_path.is_file()
                or _sha256_file(backup_path) != expected
            ):
                raise ValueError(
                    "Artifact migration backup failed integrity verification: "
                    f"{relative}"
                )

    def _migrate_provenance(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Move execution-wide frozen inputs out of a condition directory.

        :return: New provenance manifest and raw-regest snapshot reference.
        :raises ValueError: If legacy provenance cannot prove its contents.
        """
        source_root = (
            self.layout.intermediate_condition("haiu_rag_ontologizer")
            / "provenance"
        )
        source_manifest_path = source_root / "provenance_manifest.json"
        source_snapshot_path = source_root / "raw_regests_manifest.json"
        source_manifest = _load_json_object(source_manifest_path)
        source_snapshot = _load_json_object(source_snapshot_path)

        input_records = source_manifest.get("inputs")
        if not isinstance(input_records, dict):
            raise ValueError("Legacy provenance manifest has no input index.")
        migrated_inputs: dict[str, dict[str, str]] = {}
        for label, raw_record in sorted(input_records.items()):
            if not isinstance(raw_record, dict):
                raise ValueError(f"Invalid provenance input record: {label}")
            source = _resolved_artifact(self.run_root, raw_record.get("path"))
            suffix = source.suffix or ".bin"
            target = self.layout.provenance / f"{portable_name(label)}{suffix}"
            _copy_verified(source, target, expected=raw_record.get("sha256"))
            migrated_inputs[label] = {
                "path": target.relative_to(self.run_root).as_posix(),
                "sha256": _sha256_file(target),
            }

        snapshot_records = source_snapshot.get("records")
        if not isinstance(snapshot_records, dict):
            raise ValueError("Legacy raw-regest snapshot has no record index.")
        migrated_snapshot_records: dict[str, dict[str, str]] = {}
        snapshot_root = self.layout.provenance / "raw-regests"
        for unit_id, raw_record in sorted(snapshot_records.items()):
            if not isinstance(raw_record, dict):
                raise ValueError(f"Invalid raw-regest snapshot: {unit_id}")
            source = _resolved_artifact(self.run_root, raw_record.get("path"))
            target = snapshot_root / f"{portable_name(unit_id)}.json"
            _copy_verified(source, target, expected=raw_record.get("sha256"))
            migrated_snapshot_records[unit_id] = {
                "path": target.relative_to(self.run_root).as_posix(),
                "sha256": _sha256_file(target),
            }
        migrated_snapshot = deepcopy(source_snapshot)
        migrated_snapshot["records"] = migrated_snapshot_records
        migrated_snapshot_path = snapshot_root / "manifest.json"
        _write_json_atomic(migrated_snapshot_path, migrated_snapshot)
        snapshot_reference = {
            "path": migrated_snapshot_path.relative_to(
                self.run_root
            ).as_posix(),
            "sha256": _sha256_file(migrated_snapshot_path),
            "count": len(migrated_snapshot_records),
        }

        migrated_manifest = deepcopy(source_manifest)
        migrated_manifest["inputs"] = migrated_inputs
        migrated_manifest["raw_regest_snapshot"] = snapshot_reference
        _write_json_atomic(
            self.layout.provenance / "manifest.json", migrated_manifest
        )
        return migrated_manifest, snapshot_reference

    def _migrate_run_manifest(
        self,
        *,
        provenance: dict[str, Any],
        raw_regest_snapshot: dict[str, Any],
    ) -> None:
        """Rewrite only artifact references in the immutable run identity.

        :param provenance: Migrated execution-wide provenance payload.
        :param raw_regest_snapshot: Migrated standalone-input snapshot index.
        :return: ``None`` after the schema-v3 wrapper is written.
        """
        payload = _load_json_object(self.legacy_manifest)
        payload["provenance"] = provenance
        payload["raw_regest_snapshot"] = raw_regest_snapshot
        _write_json_atomic(
            self.layout.manifest,
            {
                "schema_version": ARTIFACT_SCHEMA_VERSION,
                "record_type": "haiu_comparison_execution_manifest",
                "run": payload,
            },
        )

    def _migrate_annotations(self) -> int:
        """Recover shared annotations from collision-free legacy evidence.

        Completed legacy cells overwrote ``<unit>.json`` with Stage-1 capture
        metadata. Their duplicate YAML annotation remains authoritative and is
        checked against the annotation-attempt content hash before conversion.

        :return: Number of shared annotation units recovered.
        """
        source_root = self.layout.intermediate_condition(
            "workflow_full_ontology"
        )
        count = 0
        for state_path in sorted(source_root.glob("*.annotation-attempt.json")):
            unit_id = state_path.name.removesuffix(".annotation-attempt.json")
            state = _load_json_object(state_path)
            json_path = source_root / f"{portable_name(unit_id)}.json"
            yaml_path = source_root / f"{portable_name(unit_id)}.yaml"
            annotation = self._legacy_annotation(json_path, yaml_path)
            expected = state.get("content_sha256")
            observed = annotation.get("content_sha256")
            if isinstance(expected, str) and expected != observed:
                raise ValueError(
                    f"Frozen annotation hash differs for input unit {unit_id}."
                )
            target_root = self.layout.annotation_unit(unit_id)
            _write_json_atomic(target_root / "annotation.json", annotation)
            _copy_verified(state_path, target_root / "attempts.json")
            count += 1
        return count

    def _legacy_annotation(
        self, json_path: Path, yaml_path: Path
    ) -> dict[str, Any]:
        """Read an annotation without mistaking Stage-1 metadata for one.

        :param json_path: Legacy collision-prone JSON path.
        :param yaml_path: Legacy annotation-only YAML mirror.
        :return: Parsed annotation mapping.
        :raises ValueError: If neither source contains annotation content.
        """
        if json_path.is_file():
            candidate = _load_json_object(json_path)
            if isinstance(candidate.get("content"), dict):
                return candidate
        if not yaml_path.is_file():
            raise ValueError(
                f"Frozen annotation is missing for {json_path.stem}."
            )
        candidate = haiu_utils.load_yaml(yaml_path)
        if not isinstance(candidate, dict) or not isinstance(
            candidate.get("content"), dict
        ):
            raise ValueError(
                f"Frozen annotation is malformed: {yaml_path.name}"
            )
        return candidate

    def _migrate_checkpoints(self) -> int:
        """Move all cell checkpoints beside their per-unit attempts.

        :return: Number of checkpoints migrated.
        """
        count = 0
        for condition in CONDITIONS:
            source_root = self.layout.intermediate_condition(condition)
            for source in sorted(source_root.glob("*.attempt.json")):
                unit_id = source.name.removesuffix(".attempt.json")
                target = self.layout.checkpoint(condition, unit_id)
                _copy_verified(source, target)
                count += 1
        return count

    def _verify_results(
        self, legacy_results: tuple[tuple[str, Path], ...]
    ) -> tuple[int, int]:
        """Verify every v3 bundle against its exact legacy JSON bytes.

        :param legacy_results: Condition and source paths captured pre-migration.
        :return: Terminal-cell and explicitly failed-attempt counts.
        """
        failed_attempts = 0
        for condition, source in legacy_results:
            source_bytes = source.read_bytes()
            source_payload = json.loads(source_bytes.decode("utf-8"))
            if not isinstance(source_payload, dict):
                raise ValueError(
                    f"Legacy result is not an object: {source.name}"
                )
            unit_id = str(source_payload.get("regest_id") or source.stem)
            result_path = self.layout.result_record(condition, unit_id)
            record = _load_json_object(result_path)
            migrated_payload = load_upstream_payload(
                record,
                run_root=self.run_root,
            )
            if migrated_payload != source_payload:
                raise ValueError(
                    f"Migrated result fields differ for {condition}/{unit_id}."
                )
            upstream = record.get("artifacts", {}).get("upstream_result", {})
            if (
                upstream.get("uncompressed_sha256")
                != hashlib.sha256(source_bytes).hexdigest()
            ):
                raise ValueError(
                    f"Migrated source bytes differ for {condition}/{unit_id}."
                )
            attempt_root = (
                self.layout.intermediate_unit(condition, unit_id) / "attempts"
            )
            failed_attempts += len(tuple(attempt_root.glob("*-failed")))
        return len(legacy_results), failed_attempts

    def _referenced_debug_paths(
        self, legacy_results: tuple[tuple[str, Path], ...]
    ) -> tuple[Path, ...]:
        """Resolve only DMW debug duplicates named by this execution's results.

        :param legacy_results: Terminal legacy result sources.
        :return: Existing run-owned debug files safe to archive and remove.
        """
        found: set[Path] = set()
        for _condition, result_path in legacy_results:
            payload = _load_json_object(result_path)
            raw_response = payload.get("raw_response")
            relative = (
                raw_response.get("debug_output_path")
                if isinstance(raw_response, dict)
                else None
            )
            if not isinstance(relative, str) or not relative:
                continue
            candidate = (self.run_root / relative).resolve()
            if (
                candidate.is_relative_to(self.run_root)
                and candidate.is_file()
                and candidate.parent == self.run_root / "debug_output"
            ):
                found.add(candidate)
        return tuple(sorted(found))

    def _source_harness_identity(self) -> dict[str, Any]:
        """Read the originally frozen experiment-harness identity.

        :return: Commit, branch, and cleanliness evidence from first launch.
        """
        environment_lock = _load_json_object(
            self.environment / f"{self.execution}-environment-lock.json"
        )
        identity = environment_lock.get("experiment_harness")
        if not isinstance(identity, dict):
            raise ValueError(
                "Environment lock has no experiment-harness identity."
            )
        return identity

    def _remove_legacy_view(self, debug_paths: tuple[Path, ...]) -> None:
        """Remove verified duplicates while leaving the recovery snapshot.

        :param debug_paths: Exact DMW duplicate files owned by this execution.
        :return: ``None`` after only schema-v3 paths remain active.
        """
        for condition in CONDITIONS:
            for root in (
                self.layout.intermediate_condition(condition),
                self.layout.result_condition(condition),
            ):
                for child in root.iterdir():
                    if child.is_file() and child.name != ".gitkeep":
                        child.unlink()
            provenance = (
                self.layout.intermediate_condition(condition) / "provenance"
            )
            if provenance.is_dir():
                shutil.rmtree(provenance)
        for path in debug_paths:
            path.unlink(missing_ok=True)
        debug_root = self.run_root / "debug_output"
        if debug_root.is_dir() and not any(debug_root.iterdir()):
            debug_root.rmdir()
        self.legacy_manifest.unlink()


def migration_report_payload(report: ArtifactMigrationReport) -> dict[str, Any]:
    """Return a JSON-friendly report for the CLI and lifecycle log.

    :param report: Completed migration summary.
    :return: Plain dictionary preserving every report field.
    """
    return asdict(report)


def _clean_harness_identity() -> dict[str, Any]:
    """Capture the committed harness that performs the migration.

    :return: Commit, branch, and clean-worktree evidence.
    :raises ValueError: If Git cannot prove a clean committed checkout.
    """
    commands = {
        "commit": ("git", "rev-parse", "HEAD"),
        "branch": ("git", "branch", "--show-current"),
        "status": ("git", "status", "--porcelain"),
    }
    outputs: dict[str, str] = {}
    for label, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise ValueError(f"Cannot inspect experiment harness Git {label}.")
        outputs[label] = completed.stdout.strip()
    if outputs["status"]:
        raise ValueError(
            "Commit the artifact-layout implementation before migrating a run."
        )
    return {
        "commit": outputs["commit"],
        "branch": outputs["branch"],
        "worktree_clean": True,
    }


def _inventory_digest(inventory: dict[str, str]) -> str:
    """Hash one stable path-to-digest inventory.

    :param inventory: Run-relative source paths and content hashes.
    :return: SHA-256 digest of canonical compact JSON.
    """
    encoded = json.dumps(
        inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolved_artifact(run_root: Path, raw_path: Any) -> Path:
    """Resolve and constrain one portable path from legacy provenance.

    :param run_root: Copied-run trust boundary.
    :param raw_path: Candidate run-relative path.
    :return: Existing path below ``run_root``.
    :raises ValueError: If the path is absent, absolute, or escapes the run.
    """
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Legacy provenance artifact has no portable path.")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise ValueError("Legacy provenance artifact path is absolute.")
    resolved = (run_root / relative).resolve()
    if not resolved.is_relative_to(run_root) or not resolved.is_file():
        raise ValueError(f"Legacy provenance artifact is missing: {raw_path}")
    return resolved


def _copy_verified(source: Path, target: Path, *, expected: Any = None) -> None:
    """Copy one source and verify the optional declared digest.

    :param source: Existing source file.
    :param target: New canonical path.
    :param expected: Optional SHA-256 digest declared by legacy metadata.
    :return: ``None`` after exact bytes are present at ``target``.
    :raises ValueError: If source, declaration, or copied bytes disagree.
    """
    observed = _sha256_file(source)
    if expected is not None and expected != observed:
        raise ValueError(f"Legacy artifact hash differs: {source.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if _sha256_file(target) != observed:
            raise ValueError(f"Migration target differs: {target.name}")
        return
    shutil.copy2(source, target)
    if _sha256_file(target) != observed:
        raise ValueError(f"Copied artifact differs: {target.name}")


def _link_or_copy(source: Path, target: Path) -> None:
    """Create a space-efficient exact backup with a copy fallback.

    :param source: Existing source artifact.
    :param target: Recovery-snapshot destination.
    :return: ``None`` after one exact backup member exists.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _sha256_file(path: Path) -> str:
    """Hash one file without loading it entirely into memory.

    :param path: Existing file to hash.
    :return: Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object with a path-specific error.

    :param path: Existing JSON artifact.
    :return: Parsed object.
    :raises ValueError: If the root value is not an object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace one JSON object without exposing a partial file.

    :param path: Destination artifact.
    :param payload: JSON-compatible object.
    :return: ``None`` after atomic replacement.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "ArtifactLayoutMigrator",
    "ArtifactMigrationReport",
    "migration_report_payload",
]
