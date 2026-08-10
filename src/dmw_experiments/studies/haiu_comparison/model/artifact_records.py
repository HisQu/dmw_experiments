"""Small, navigable records that index complete experiment evidence."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ARTIFACT_SCHEMA_VERSION,
)

EXTERNALIZED_RESULT_FIELDS = frozenset(
    {
        "abox",
        "explanation",
        "frozen_annotation_artifact_paths",
        "generation_attempts",
        "ontology_context",
        "prompts",
        "raw_response",
        "raw_stage1_output",
        "raw_stage1_provider_message",
        "raw_stage2_provider_message",
        "raw_ttl_output",
        "tbox",
    }
)

IDENTITY_FIELDS = frozenset(
    {
        "branch_requested",
        "condition",
        "condition_order",
        "condition_order_position",
        "model",
        "regest_id",
    }
)
OUTCOME_FIELDS = frozenset(
    {
        "error_message",
        "failure_code",
        "finish_reason_missing",
        "http_status",
        "non_retryable",
        "pipeline_error",
        "publication_eligible",
        "success",
    }
)
ATTEMPT_FIELDS = frozenset(
    {
        "attempt",
        "attempt_history",
        "max_attempts",
        "total_retry_delay_seconds",
    }
)
PROVENANCE_FIELDS = frozenset(
    {
        "generation_dependency",
        "input_lineage",
        "ontology_record_version",
        "provider_profile",
    }
)


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Describe one exact file without embedding its contents.

    :param path: Portable path relative to the copied run directory.
    :param sha256: Digest of the bytes stored at ``path``.
    :param bytes: Stored byte count.
    :param media_type: MIME type that explains how to read the file.
    :param content_encoding: Optional transport encoding such as ``gzip``.
    :param uncompressed_sha256: Optional digest before transport encoding.
    :param uncompressed_bytes: Optional byte count before transport encoding.
    """

    path: str
    sha256: str
    bytes: int
    media_type: str
    content_encoding: str | None = None
    uncompressed_sha256: str | None = None
    uncompressed_bytes: int | None = None

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        run_root: Path,
        media_type: str,
        content_encoding: str | None = None,
        uncompressed: bytes | None = None,
    ) -> ArtifactReference:
        """Measure a written artifact and make its path portable.

        :param path: Existing artifact to describe.
        :param run_root: Copied run used as the relative-path boundary.
        :param media_type: MIME type for the decoded contents.
        :param content_encoding: Optional encoding applied to the stored bytes.
        :param uncompressed: Original bytes when ``path`` stores an encoding.
        :return: Complete portable artifact reference.
        """
        stored = path.read_bytes()
        return cls(
            path=path.relative_to(run_root).as_posix(),
            sha256=hashlib.sha256(stored).hexdigest(),
            bytes=len(stored),
            media_type=media_type,
            content_encoding=content_encoding,
            uncompressed_sha256=(
                hashlib.sha256(uncompressed).hexdigest()
                if uncompressed is not None
                else None
            ),
            uncompressed_bytes=(
                len(uncompressed) if uncompressed is not None else None
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation without empty optionals.

        :return: Portable artifact metadata.
        """
        payload: dict[str, Any] = {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "media_type": self.media_type,
        }
        if self.content_encoding is not None:
            payload["content_encoding"] = self.content_encoding
        if self.uncompressed_sha256 is not None:
            payload["uncompressed_sha256"] = self.uncompressed_sha256
        if self.uncompressed_bytes is not None:
            payload["uncompressed_bytes"] = self.uncompressed_bytes
        return payload


@dataclass(frozen=True, slots=True)
class CellResultRecord:
    """Index one terminal condition cell without repeating large evidence.

    The original payload remains authoritative in the compressed upstream
    artifact. This record groups every compact field for navigation, status,
    and schema-aware analysis while pointing to exact prompts and responses.

    :param identity: Stable cell and provider identifiers.
    :param outcome: Terminal success or failure classification.
    :param timing: Measurements and their declared scopes.
    :param attempts: Retry history and terminal attempt number.
    :param annotation: Shared NER identity and preparation evidence.
    :param context: Ontology and retrieval context metadata.
    :param generation: Token, budget, and provider-generation measurements.
    :param validation: Turtle and retrieval validation results.
    :param provenance: Input, package, and generated-ontology lineage.
    :param configuration: Scientific switches observed for this cell.
    :param additional_fields: Unrecognized compact fields retained losslessly.
    :param artifacts: Exact evidence files keyed by semantic role.
    """

    identity: dict[str, Any]
    outcome: dict[str, Any]
    timing: dict[str, Any]
    attempts: dict[str, Any]
    annotation: dict[str, Any]
    context: dict[str, Any]
    generation: dict[str, Any]
    validation: dict[str, Any]
    provenance: dict[str, Any]
    configuration: dict[str, Any]
    additional_fields: dict[str, Any]
    artifacts: dict[str, Any]

    @classmethod
    def from_payload(
        cls,
        *,
        payload: dict[str, Any],
        condition: str,
        unit_id: str,
        artifacts: dict[str, Any],
    ) -> CellResultRecord:
        """Group one legacy-compatible payload into schema-v3 sections.

        Large content fields are represented by ``artifacts`` and remain in
        the compressed upstream payload. Every other field is assigned to one
        section; unfamiliar fields are retained under ``additional_fields``.

        :param payload: Complete condition result before artifact extraction.
        :param condition: Stable condition directory owner.
        :param unit_id: Stable input-unit identifier.
        :param artifacts: Semantic references to exact written evidence.
        :return: Navigable terminal record.
        """
        groups: dict[str, dict[str, Any]] = {
            "identity": {},
            "outcome": {},
            "timing": {},
            "attempts": {},
            "annotation": {},
            "context": {},
            "generation": {},
            "validation": {},
            "provenance": {},
            "configuration": {},
            "additional_fields": {},
        }
        for key, value in payload.items():
            if key in EXTERNALIZED_RESULT_FIELDS:
                continue
            groups[_field_group(key)][key] = value
        groups["identity"]["condition"] = condition
        groups["identity"]["regest_id"] = unit_id
        return cls(artifacts=artifacts, **groups)

    def as_dict(self) -> dict[str, Any]:
        """Return the stable serialized schema-v3 representation.

        :return: Nested JSON object with empty sections omitted.
        """
        record: dict[str, Any] = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "record_type": "haiu_comparison_terminal_cell",
        }
        for name in (
            "identity",
            "outcome",
            "timing",
            "attempts",
            "annotation",
            "context",
            "generation",
            "validation",
            "provenance",
            "configuration",
            "additional_fields",
            "artifacts",
        ):
            value = getattr(self, name)
            if value:
                record[name] = value
        return record


def load_upstream_bytes(record: dict[str, Any], *, run_root: Path) -> bytes:
    """Load and verify the exact decoded source bytes indexed by a v3 record.

    :param record: Parsed schema-v3 terminal or attempt metadata.
    :param run_root: Copied run used to resolve portable artifact paths.
    :return: Original uncompressed JSON bytes.
    :raises ValueError: If the artifact is absent or corrupted.
    """
    artifacts = record.get("artifacts")
    upstream = (
        artifacts.get("upstream_result")
        if isinstance(artifacts, dict)
        else None
    )
    if not isinstance(upstream, dict):
        raise ValueError("Schema-v3 record has no upstream-result artifact.")
    relative = upstream.get("path")
    if not isinstance(relative, str):
        raise ValueError("Upstream-result artifact has no portable path.")
    artifact_path = run_root / relative
    if not artifact_path.is_file():
        raise ValueError(f"Upstream-result artifact is missing: {relative}")
    stored = artifact_path.read_bytes()
    if hashlib.sha256(stored).hexdigest() != upstream.get("sha256"):
        raise ValueError(f"Upstream-result artifact hash changed: {relative}")
    try:
        decoded = gzip.decompress(stored)
    except OSError as exc:
        raise ValueError(
            f"Upstream-result artifact is not valid gzip: {relative}"
        ) from exc
    if hashlib.sha256(decoded).hexdigest() != upstream.get(
        "uncompressed_sha256"
    ):
        raise ValueError(
            f"Decoded upstream-result artifact hash changed: {relative}"
        )
    return decoded


def load_upstream_payload(
    record: dict[str, Any], *, run_root: Path
) -> dict[str, Any]:
    """Load and verify the exact source payload indexed by a v3 record.

    :param record: Parsed schema-v3 terminal or attempt metadata.
    :param run_root: Copied run used to resolve portable artifact paths.
    :return: Original flat JSON-compatible payload.
    :raises ValueError: If the artifact is absent, corrupted, or malformed.
    """
    decoded = load_upstream_bytes(record, run_root=run_root)
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Upstream result is not a JSON object.")
    return payload


def verify_artifact_references(
    record: dict[str, Any], *, run_root: Path
) -> None:
    """Verify every path-bearing artifact reference in one compact record.

    :param record: Parsed schema-v3 terminal or attempt record.
    :param run_root: Copied-run boundary used to resolve portable paths.
    :return: ``None`` when every referenced stored byte matches its digest.
    :raises ValueError: If a reference escapes the run, is missing, or differs.
    """
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Schema-v3 record has no artifact index.")
    for role, reference in _walk_artifact_references(artifacts):
        relative = reference["path"]
        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise ValueError(f"Artifact reference is absolute: {role}")
        path = (run_root / relative_path).resolve()
        if not path.is_relative_to(run_root) or not path.is_file():
            raise ValueError(f"Artifact reference is missing: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference.get(
            "sha256"
        ):
            raise ValueError(f"Artifact reference hash changed: {relative}")


def _walk_artifact_references(
    value: dict[str, Any], *, prefix: str = "artifacts"
) -> list[tuple[str, dict[str, Any]]]:
    """Collect nested mappings that declare both a path and digest.

    :param value: Artifact index or one of its nested mappings.
    :param prefix: Diagnostic key path for the current mapping.
    :return: Semantic key paths and artifact-reference dictionaries.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for key, child in value.items():
        role = f"{prefix}.{key}"
        if not isinstance(child, dict):
            continue
        if isinstance(child.get("path"), str):
            found.append((role, child))
            continue
        found.extend(_walk_artifact_references(child, prefix=role))
    return found


def _field_group(key: str) -> str:
    """Assign one compact legacy field to its schema-v3 section.

    :param key: Original top-level payload key.
    :return: :class:`CellResultRecord` dictionary attribute name.
    """
    if key in IDENTITY_FIELDS:
        return "identity"
    if key in OUTCOME_FIELDS:
        return "outcome"
    if key in ATTEMPT_FIELDS:
        return "attempts"
    if key in PROVENANCE_FIELDS:
        return "provenance"
    if _is_timing_field(key):
        return "timing"
    if key.startswith(("annotation_", "frozen_", "observed_annotation_")):
        return "annotation"
    if _is_context_field(key):
        return "context"
    if _is_generation_field(key):
        return "generation"
    if key.startswith("turtle_") or key in {
        "rag_retrieval_valid",
        "retrieval_sidecars_complete",
    }:
        return "validation"
    if key.endswith("_version") or key in {
        "ontology_ref",
        "raw_stage1_output_source",
    }:
        return "provenance"
    if key in {
        "allow_text_interpretation",
        "existing_data_policy",
        "existing_data_policy_requested",
        "include_annotations",
        "ontology_example_limit_requested",
        "reused_existing_data",
        "use_only_existing_ontology_terms",
    }:
        return "configuration"
    return "additional_fields"


def _is_timing_field(key: str) -> bool:
    """Return whether a field describes elapsed or wall-clock time.

    :param key: Original top-level payload key.
    :return: Whether the key belongs to the timing section.
    """
    return (
        "duration" in key
        or "timing" in key
        or key in {"duration_measure", "finished_at", "started_at"}
    )


def _is_context_field(key: str) -> bool:
    """Return whether a field describes ontology or retrieval context.

    :param key: Original top-level payload key.
    :return: Whether the key belongs to the context section.
    """
    return key.startswith(
        ("context_", "rag_retrieval", "retrieval_")
    ) or key in {
        "context_example_provenance",
        "ontology_examples_used",
        "ontology_ref",
    }


def _is_generation_field(key: str) -> bool:
    """Return whether a field describes one provider generation.

    :param key: Original top-level payload key.
    :return: Whether the key belongs to the generation section.
    """
    return key.startswith(
        (
            "generation_",
            "ontology_cost_",
            "ontology_provider_",
            "output_",
            "prompt_",
            "provider_",
            "stage1_",
            "stage2_",
            "workflow_",
        )
    ) or key in {
        "finish_reason_missing",
        "raw_stage1_capture_complete",
        "raw_ttl_capture_complete",
    }
