"""Validated input populations for the DMW--Haiu comparison experiment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.models import (
    RegestText,
)

HEADER_SUBLEMMA_CATALOG_SCHEMA_VERSION = 1
HEADER_SUBLEMMA_UNIT_KIND = "header_sublemma_pair"


@dataclass(frozen=True, slots=True)
class HeaderSublemmaInput:
    """One frozen header and sublemma submitted as an independent input.

    :param input_unit_id: Synthetic identifier used throughout DMW and Haiu.
    :param source_regest_id: Identifier of the original complete RG record.
    :param source_subentry_index: Zero-based sublemma position in that record.
    :param header: Exact frozen header text.
    :param sublemma: Exact frozen sublemma text.
    :param source_regest_content_sha256: Digest of the complete source record.
    :param content_sha256: Digest of this catalogue record.
    """

    input_unit_id: str
    source_regest_id: str
    source_subentry_index: int
    header: str
    sublemma: str
    source_regest_content_sha256: str
    content_sha256: str

    @property
    def source_sublemma_number(self) -> int:
        """Return the one-based sublemma number used in human-facing output.

        :return: One-based source position.
        """
        return self.source_subentry_index + 1

    def as_regest_text(self) -> RegestText:
        """Render the pair through the input contract shared by all conditions.

        :return: Header plus exactly one ordered subentry.
        """
        return RegestText(
            regest_id=self.input_unit_id,
            header=self.header,
            subentries=(self.sublemma,),
        )

    def lineage(self) -> dict[str, int | str]:
        """Return portable source information for results and manifests.

        :return: Stable identifiers and content hashes without repeating text.
        """
        return {
            "input_unit_kind": HEADER_SUBLEMMA_UNIT_KIND,
            "input_unit_id": self.input_unit_id,
            "source_regest_id": self.source_regest_id,
            "source_subentry_index": self.source_subentry_index,
            "source_sublemma_number": self.source_sublemma_number,
            "input_content_sha256": self.content_sha256,
            "source_regest_content_sha256": self.source_regest_content_sha256,
        }


@dataclass(frozen=True, slots=True)
class HeaderSublemmaCatalog:
    """Verified pair population and its immutable catalogue identity.

    :param path: Source catalogue supplied to the runner.
    :param file_sha256: Digest of the exact serialized file.
    :param content_sha256: Digest embedded in the canonical catalogue payload.
    :param source: Frozen complete-regest source description.
    :param records: Pair inputs in experimental order.
    """

    path: Path
    file_sha256: str
    content_sha256: str
    source: dict[str, Any]
    records: tuple[HeaderSublemmaInput, ...]

    @property
    def by_id(self) -> dict[str, HeaderSublemmaInput]:
        """Index inputs by their synthetic execution identifier.

        :return: Ordered catalogue records keyed by input unit ID.
        """
        return {record.input_unit_id: record for record in self.records}

    def manifest_entry(self) -> dict[str, Any]:
        """Return the portable catalogue identity used by run manifests.

        :return: Schema, population, and digest evidence without a local path.
        """
        return {
            "unit_kind": HEADER_SUBLEMMA_UNIT_KIND,
            "schema_version": HEADER_SUBLEMMA_CATALOG_SCHEMA_VERSION,
            "file_sha256": self.file_sha256,
            "catalogue_content_sha256": self.content_sha256,
            "input_unit_count": len(self.records),
            "source": self.source,
            "units": [record.lineage() for record in self.records],
        }

    def dmw_raw_documents(self) -> list[dict[str, Any]]:
        """Render the exact raw records consumed by the frozen DMW runtime.

        :return: Ordered documents with one header and one subentry each.
        """
        return [
            {
                "id": record.input_unit_id,
                "header": record.header,
                "subentries": [record.sublemma],
            }
            for record in self.records
        ]


@dataclass(frozen=True, slots=True)
class PairInputCandidate:
    """Catalogue input adapted to the existing availability-selection contract.

    :param catalog_position: Zero-based position in the frozen catalogue.
    :param unit: Verified header--sublemma record.
    """

    catalog_position: int
    unit: HeaderSublemmaInput

    @property
    def raw_id(self) -> str:
        """Return the unmodified catalogue identifier.

        :return: Synthetic pair ID.
        """
        return self.unit.input_unit_id

    @property
    def regest_id(self) -> str:
        """Return the identifier submitted to DMW.

        :return: Synthetic pair ID.
        """
        return self.unit.input_unit_id

    def as_dict(self) -> dict[str, int | str]:
        """Return selection-report metadata for this input.

        :return: Catalogue position and historical lineage.
        """
        return {
            "catalog_position": self.catalog_position,
            "raw_id": self.raw_id,
            "regest_id": self.regest_id,
            **self.unit.lineage(),
        }


@dataclass(frozen=True, slots=True)
class DmwPairImportManifest:
    """Verified evidence that a pair catalogue was loaded into isolated DMW.

    :param path: Source manifest supplied to capture or execution.
    :param file_sha256: Digest of the exact serialized file.
    :param content_sha256: Canonical self-digest embedded in the manifest.
    :param payload: Validated non-secret import evidence.
    """

    path: Path
    file_sha256: str
    content_sha256: str
    payload: dict[str, Any]

    @property
    def collections(self) -> dict[str, str]:
        """Return exact physical collection identities.

        :return: Raw, annotation, ontology, and registry collection names.
        """
        value = self.payload["collections"]
        assert isinstance(value, dict)
        return {str(key): str(item) for key, item in value.items()}

    @property
    def target_branch(self) -> dict[str, Any]:
        """Return the database branch identity created for the pair run.

        :return: Portable DMW branch record without timestamps or Mongo ID.
        """
        value = self.payload["target_branch"]
        assert isinstance(value, dict)
        return dict(value)

    @property
    def ontology_context_version(self) -> str:
        """Return the frozen ontology context version for the prepared run.

        :return: Version string supplied during environment preparation.
        """
        return str(self.payload["ontology_context_version"])


def load_header_sublemma_catalog(path: Path) -> HeaderSublemmaCatalog:
    """Load and fully validate one frozen header--sublemma catalogue.

    Validation covers the outer self-digest, record digests, generated IDs,
    ordering metadata, duplicate IDs, and the declared population count. This
    lets preparation and execution share one strict interpretation of the
    experiment input.

    :param path: Catalogue JSON file.
    :return: Verified input population in catalogue order.
    :raises ValueError: If the file is malformed or any digest is inconsistent.
    """
    resolved_path = path.expanduser().resolve()
    payload = _read_json_object(resolved_path)
    if payload.get("schema_version") != HEADER_SUBLEMMA_CATALOG_SCHEMA_VERSION:
        raise ValueError(
            "Header--sublemma catalogue must use schema_version 1."
        )
    if payload.get("unit_kind") != HEADER_SUBLEMMA_UNIT_KIND:
        raise ValueError(
            "Header--sublemma catalogue has an unsupported unit_kind."
        )

    expected_catalogue_digest = payload.get("catalogue_content_sha256")
    if not _is_sha256(expected_catalogue_digest):
        raise ValueError(
            "Header--sublemma catalogue has no valid content hash."
        )
    unhashed_payload = dict(payload)
    unhashed_payload.pop("catalogue_content_sha256", None)
    if canonical_json_sha256(unhashed_payload) != expected_catalogue_digest:
        raise ValueError(
            "Header--sublemma catalogue content hash does not match."
        )
    assert isinstance(expected_catalogue_digest, str)

    source = payload.get("source")
    selection = payload.get("selection")
    raw_records = payload.get("records")
    if not isinstance(source, dict) or not isinstance(selection, dict):
        raise ValueError("Header--sublemma catalogue metadata is malformed.")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("Header--sublemma catalogue has no input records.")
    if selection.get("input_unit_count") != len(raw_records):
        raise ValueError(
            "Header--sublemma catalogue population count does not match records."
        )

    records: list[HeaderSublemmaInput] = []
    seen_ids: set[str] = set()
    for index, raw_record in enumerate(raw_records):
        record = _parse_record(raw_record, position=index)
        if record.input_unit_id in seen_ids:
            raise ValueError(
                "Header--sublemma catalogue contains duplicate input unit ID: "
                f"{record.input_unit_id}."
            )
        seen_ids.add(record.input_unit_id)
        records.append(record)

    return HeaderSublemmaCatalog(
        path=resolved_path,
        file_sha256=file_sha256(resolved_path),
        content_sha256=expected_catalogue_digest,
        source=dict(source),
        records=tuple(records),
    )


def load_dmw_pair_import_manifest(
    path: Path,
    *,
    catalog: HeaderSublemmaCatalog,
) -> DmwPairImportManifest:
    """Validate an isolated DMW import manifest against its pair catalogue.

    :param path: Manifest written by the preparation command.
    :param catalog: Catalogue that must have populated the recorded collection.
    :return: Verified import evidence.
    :raises ValueError: If the self-digest, catalogue, or storage identity is
        malformed or inconsistent.
    """
    resolved_path = path.expanduser().resolve()
    payload = _read_json_object(resolved_path)
    if payload.get("schema_version") != 1:
        raise ValueError("DMW pair import manifest must use schema_version 1.")
    expected_digest = payload.get("manifest_content_sha256")
    unhashed_payload = dict(payload)
    unhashed_payload.pop("manifest_content_sha256", None)
    if (
        not _is_sha256(expected_digest)
        or canonical_json_sha256(unhashed_payload) != expected_digest
    ):
        raise ValueError(
            "DMW pair import manifest content hash does not match."
        )
    assert isinstance(expected_digest, str)

    expected_catalogue = {
        "schema_version": HEADER_SUBLEMMA_CATALOG_SCHEMA_VERSION,
        "unit_kind": HEADER_SUBLEMMA_UNIT_KIND,
        "file_sha256": catalog.file_sha256,
        "catalogue_content_sha256": catalog.content_sha256,
        "input_unit_count": len(catalog.records),
    }
    if payload.get("catalogue") != expected_catalogue:
        raise ValueError(
            "DMW pair import manifest does not identify the selected catalogue."
        )
    collections = payload.get("collections")
    source_branch = payload.get("source_branch")
    target_branch = payload.get("target_branch")
    raw_population = payload.get("raw_population")
    required_collections = ("raw", "annotation", "ontology", "branch_registry")
    source_branch_fields = (
        "branch_slug",
        "github_branch",
        "github_tag_scope",
        "latest_version",
    )
    target_branch_fields = (
        *source_branch_fields,
        "branch_name",
        "annotation_collection",
        "ontology_collection",
        "status",
        "creator_id",
    )
    if (
        not isinstance(collections, dict)
        or not all(
            isinstance(collections.get(name), str) and collections[name]
            for name in required_collections
        )
        or collections.get("raw") == "RG_raw"
        or not isinstance(source_branch, dict)
        or not all(
            isinstance(source_branch.get(name), str) and source_branch[name]
            for name in source_branch_fields
        )
        or not isinstance(target_branch, dict)
        or not all(
            isinstance(target_branch.get(name), str) and target_branch[name]
            for name in target_branch_fields
        )
        or target_branch.get("branch_slug") == source_branch.get("branch_slug")
        or not isinstance(payload.get("ontology_context_version"), str)
        or not payload["ontology_context_version"]
        or not _is_sha256(payload.get("database_name_sha256"))
        or not isinstance(raw_population, dict)
    ):
        raise ValueError(
            "DMW pair import manifest storage identity is incomplete."
        )
    if target_branch.get("annotation_collection") != collections.get(
        "annotation"
    ) or target_branch.get("ontology_collection") != collections.get(
        "ontology"
    ):
        raise ValueError(
            "DMW pair import manifest branch and collection identities disagree."
        )
    shared_asset_fields = (
        "github_branch",
        "github_tag_scope",
        "latest_version",
    )
    if (
        any(
            target_branch.get(field) != source_branch.get(field)
            for field in shared_asset_fields
        )
        or target_branch.get("status") != "active"
        or target_branch.get("creator_id") != "haiu_header_sublemma_experiment"
    ):
        raise ValueError(
            "DMW pair import manifest does not preserve the frozen source "
            "ontology asset identity."
        )
    expected_raw_population = {
        "document_count": len(catalog.records),
        "canonical_sha256": canonical_json_sha256(catalog.dmw_raw_documents()),
    }
    if raw_population != expected_raw_population:
        raise ValueError(
            "DMW pair import manifest raw population does not match the catalogue."
        )
    return DmwPairImportManifest(
        path=resolved_path,
        file_sha256=file_sha256(resolved_path),
        content_sha256=expected_digest,
        payload=payload,
    )


def canonical_json_sha256(payload: Any) -> str:
    """Hash a JSON-compatible value using the experiment's canonical form.

    :param payload: JSON-compatible value.
    :return: Lowercase hexadecimal SHA-256 digest.
    """
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Hash one file without loading it entirely into memory.

    :param path: Existing regular file.
    :return: Lowercase hexadecimal SHA-256 digest.
    :raises ValueError: If the path is not a regular file.
    """
    if not path.is_file():
        raise ValueError(f"Required file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_record(raw_record: Any, *, position: int) -> HeaderSublemmaInput:
    """Validate one pair record and convert it to the strict data container.

    :param raw_record: Decoded catalogue record.
    :param position: Zero-based catalogue position for error messages.
    :return: Verified pair input.
    :raises ValueError: If fields, ID construction, or digest are invalid.
    """
    if not isinstance(raw_record, dict):
        raise ValueError(
            f"Header--sublemma catalogue record {position} is not an object."
        )
    input_unit_id = raw_record.get("input_unit_id")
    source_regest_id = raw_record.get("source_regest_id")
    source_subentry_index = raw_record.get("source_subentry_index")
    source_sublemma_number = raw_record.get("source_sublemma_number")
    header = raw_record.get("header")
    sublemma = raw_record.get("sublemma")
    source_digest = raw_record.get("source_regest_content_sha256")
    content_digest = raw_record.get("content_sha256")
    if (
        not isinstance(input_unit_id, str)
        or not isinstance(source_regest_id, str)
        or not source_regest_id.isdigit()
        or not isinstance(source_subentry_index, int)
        or isinstance(source_subentry_index, bool)
        or source_subentry_index < 0
        or source_sublemma_number != source_subentry_index + 1
        or not isinstance(header, str)
        or not header.strip()
        or not isinstance(sublemma, str)
        or not sublemma.strip()
        or not _is_sha256(source_digest)
        or not _is_sha256(content_digest)
    ):
        raise ValueError(
            f"Header--sublemma catalogue record {position} is malformed."
        )
    expected_id = f"hsp-{source_regest_id}-s{source_subentry_index + 1:02d}"
    if input_unit_id != expected_id:
        raise ValueError(
            "Header--sublemma catalogue record has an inconsistent input ID: "
            f"{input_unit_id}."
        )
    unhashed_record = dict(raw_record)
    unhashed_record.pop("content_sha256", None)
    if canonical_json_sha256(unhashed_record) != content_digest:
        raise ValueError(
            "Header--sublemma catalogue record content hash does not match: "
            f"{input_unit_id}."
        )
    assert isinstance(source_digest, str)
    assert isinstance(content_digest, str)
    return HeaderSublemmaInput(
        input_unit_id=input_unit_id,
        source_regest_id=source_regest_id,
        source_subentry_index=source_subentry_index,
        header=header,
        sublemma=sublemma,
        source_regest_content_sha256=source_digest,
        content_sha256=content_digest,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read one JSON object with a concise validation error.

    :param path: Source file.
    :return: Decoded object.
    :raises ValueError: If the file is absent, invalid, or not an object.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON file is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _is_sha256(value: Any) -> bool:
    """Check whether a value is a lowercase SHA-256 digest.

    :param value: Candidate decoded from JSON.
    :return: Whether the value has the required hexadecimal shape.
    """
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
