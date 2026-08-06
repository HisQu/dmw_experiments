#!/usr/bin/env python3
"""Materialize header--sublemma units from a frozen complete-regest run.

The resulting catalogue is the immutable source for a later pair-level
replication. It deliberately reads the saved raw-regest snapshot rather than
the live DMW API, so a change to the RG source data cannot change the planned
population.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dmw_experiments.studies.haiu_comparison.paths import (
    INPUT_ROOT,
    REPOSITORY_ROOT,
    STUDY_ROOT,
)

EXPERIMENT_ROOT = STUDY_ROOT
DEFAULT_SOURCE_RUN_DIR = (
    REPOSITORY_ROOT
    / "output"
    / "runs"
    / "publication-academiccloud-v113-20260728"
)
DEFAULT_OUTPUT_PATH = INPUT_ROOT / "header_sublemma_input_catalog.json"
CATALOG_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class HeaderSublemmaUnit:
    """One independently modelled header and sublemma pair.

    :param source_regest_id: Identifier of the complete frozen RG record.
    :param source_subentry_index: Zero-based position in that record.
    :param header: Exact frozen header text.
    :param sublemma: Exact frozen sublemma text.
    :param source_regest_content_sha256: Digest of the complete source record.
    """

    source_regest_id: str
    source_subentry_index: int
    header: str
    sublemma: str
    source_regest_content_sha256: str

    @property
    def input_unit_id(self) -> str:
        """Return the synthetic DMW-safe identifier for this pair.

        :return: Identifier that differentiates sublemmas from one source
            regest while retaining its historical provenance.
        """
        return (
            f"hsp-{self.source_regest_id}-s{self.source_subentry_index + 1:02d}"
        )

    def as_dict(self) -> dict[str, int | str]:
        """Return the portable catalogue representation.

        :return: JSON-compatible source provenance and exact pair text.
        """
        record: dict[str, int | str] = {
            "input_unit_id": self.input_unit_id,
            "source_regest_id": self.source_regest_id,
            "source_subentry_index": self.source_subentry_index,
            "source_sublemma_number": self.source_subentry_index + 1,
            "header": self.header,
            "sublemma": self.sublemma,
            "source_regest_content_sha256": (self.source_regest_content_sha256),
        }
        record["content_sha256"] = _sha256_canonical_json(record)
        return record


def main(argv: list[str] | None = None) -> int:
    """Materialize one deterministic header--sublemma catalogue.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Process exit code.
    """
    args = _build_parser().parse_args(argv)
    source_run_dir = Path(args.source_run_dir).resolve()
    output_path = Path(args.output).resolve()
    catalogue = materialize_catalogue(source_run_dir)
    write_catalogue(
        catalogue=catalogue,
        output_path=output_path,
        overwrite=args.overwrite,
    )
    selection = catalogue["selection"]
    print(f"Source run: {source_run_dir.name}")
    print(f"Source regesta: {selection['source_regest_count']}")
    print(f"Header--sublemma pairs: {selection['input_unit_count']}")
    print(
        "Excluded header-only regesta: "
        f"{selection['excluded_header_only_regest_count']}"
    )
    print(f"Catalogue: {output_path}")
    return 0


def materialize_catalogue(source_run_dir: Path) -> dict[str, Any]:
    """Build pair units after validating every frozen source record.

    :param source_run_dir: Existing complete-regest run with frozen raw inputs.
    :return: Deterministic catalogue and source-integrity metadata.
    :raises ValueError: If the source snapshot is malformed or modified.
    """
    source_run_dir = source_run_dir.resolve()
    snapshot_path = source_run_dir / "provenance" / "raw_regests_manifest.json"
    snapshot = _read_json_object(snapshot_path)
    records = snapshot.get("records")
    if not isinstance(records, dict) or not records:
        raise ValueError("Frozen raw-regest snapshot has no records.")

    units: list[HeaderSublemmaUnit] = []
    header_only_regest_ids: list[str] = []
    seen_unit_ids: set[str] = set()
    for source_regest_id, manifest_record in records.items():
        if not isinstance(source_regest_id, str) or not source_regest_id:
            raise ValueError("Frozen raw-regest snapshot has an invalid ID.")
        raw_record = _load_verified_source_regest(
            source_run_dir=source_run_dir,
            source_regest_id=source_regest_id,
            manifest_record=manifest_record,
        )
        header = raw_record["header"]
        subentries = raw_record["subentries"]
        source_digest = raw_record["content_sha256"]
        if not subentries:
            header_only_regest_ids.append(source_regest_id)
            continue
        for subentry_index, sublemma in enumerate(subentries):
            unit = HeaderSublemmaUnit(
                source_regest_id=source_regest_id,
                source_subentry_index=subentry_index,
                header=header,
                sublemma=sublemma,
                source_regest_content_sha256=source_digest,
            )
            if unit.input_unit_id in seen_unit_ids:
                raise ValueError(
                    "Header--sublemma materialization produced duplicate "
                    f"input unit ID: {unit.input_unit_id}."
                )
            seen_unit_ids.add(unit.input_unit_id)
            units.append(unit)

    catalogue: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "unit_kind": "header_sublemma_pair",
        "description": (
            "One input unit contains the exact frozen header and one ordered "
            "sublemma from a complete RG regest."
        ),
        "source": {
            "source_run_id": source_run_dir.name,
            "raw_regest_snapshot_manifest": _portable_path(snapshot_path),
            "raw_regest_snapshot_manifest_sha256": _sha256_file(snapshot_path),
            "source_snapshot_schema_version": snapshot.get("schema_version"),
        },
        "selection": {
            "source_regest_count": len(records),
            "input_unit_count": len(units),
            "excluded_header_only_regest_count": len(header_only_regest_ids),
            "excluded_header_only_regest_ids": header_only_regest_ids,
        },
        "records": [unit.as_dict() for unit in units],
    }
    catalogue["catalogue_content_sha256"] = _sha256_canonical_json(catalogue)
    return catalogue


def write_catalogue(
    *, catalogue: dict[str, Any], output_path: Path, overwrite: bool
) -> None:
    """Persist the materialized input population without partial writes.

    :param catalogue: Validated catalogue from :func:`materialize_catalogue`.
    :param output_path: Destination JSON file.
    :param overwrite: Whether an existing destination may be replaced.
    :raises FileExistsError: If the destination exists without explicit consent.
    """
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Pass --overwrite to replace it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def _load_verified_source_regest(
    *,
    source_run_dir: Path,
    source_regest_id: str,
    manifest_record: Any,
) -> dict[str, Any]:
    """Read one snapshot entry after checking manifest and content digests.

    :param source_run_dir: Root of the frozen source run.
    :param source_regest_id: Expected source record identifier.
    :param manifest_record: Manifest item that names and hashes the source file.
    :return: Validated raw record with header and ordered subentries.
    :raises ValueError: If the file location, digest, or content is invalid.
    """
    if not isinstance(manifest_record, dict):
        raise ValueError(
            f"Frozen raw-regest manifest record is invalid: {source_regest_id}."
        )
    relative_path = manifest_record.get("path")
    expected_file_digest = manifest_record.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(
        expected_file_digest, str
    ):
        raise ValueError(
            f"Frozen raw-regest manifest record is incomplete: {source_regest_id}."
        )
    record_path = (source_run_dir / relative_path).resolve()
    try:
        record_path.relative_to(source_run_dir)
    except ValueError as exc:
        raise ValueError(
            "Frozen raw-regest manifest points outside its source run: "
            f"{source_regest_id}."
        ) from exc
    if (
        not record_path.is_file()
        or _sha256_file(record_path) != expected_file_digest
    ):
        raise ValueError(
            "Frozen raw-regest file does not match its manifest: "
            f"{source_regest_id}."
        )
    record = _read_json_object(record_path)
    record_id = record.get("regest_id")
    header = record.get("header")
    subentries = record.get("subentries")
    content_digest = record.get("content_sha256")
    if (
        record_id != source_regest_id
        or not isinstance(header, str)
        or not header.strip()
        or not isinstance(subentries, list)
        or not all(
            isinstance(subentry, str) and subentry.strip()
            for subentry in subentries
        )
        or not isinstance(content_digest, str)
    ):
        raise ValueError(
            f"Frozen raw-regest record has an invalid text shape: {source_regest_id}."
        )
    source_content = {
        "regest_id": record_id,
        "header": header,
        "subentries": subentries,
    }
    if _sha256_canonical_json(source_content) != content_digest:
        raise ValueError(
            "Frozen raw-regest record content digest does not match: "
            f"{source_regest_id}."
        )
    return {
        "header": header,
        "subentries": subentries,
        "content_sha256": content_digest,
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    """Decode an object-valued JSON document.

    :param path: JSON file to read.
    :return: Parsed object.
    :raises ValueError: If the document is not a JSON object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path.name}.")
    return payload


def _portable_path(path: Path) -> str:
    """Describe a source path without recording machine-specific locations.

    :param path: Source file within or outside the experiment directory.
    :return: Experiment-relative path where possible, otherwise the file name.
    """
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.name


def _sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest for one file.

    :param path: File to hash.
    :return: Lower-case hexadecimal digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_canonical_json(payload: dict[str, Any]) -> str:
    """Hash JSON data with a fixed serialization contract.

    :param payload: JSON-compatible object to serialize canonically.
    :return: Lower-case hexadecimal digest.
    """
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    """Create the standalone catalogue-materialization CLI.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Create one header--sublemma input catalogue from a frozen "
            "complete-regest experiment run."
        )
    )
    parser.add_argument(
        "--source-run-dir",
        default=str(DEFAULT_SOURCE_RUN_DIR),
        help="Complete-regest run containing provenance/raw_regests_manifest.json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Destination header--sublemma JSON catalogue.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing catalogue at --output.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
