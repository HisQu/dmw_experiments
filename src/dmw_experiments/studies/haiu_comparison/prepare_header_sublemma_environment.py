#!/usr/bin/env python3
"""Prepare isolated DMW storage for the header--sublemma replication.

Run this command with the frozen DMW publication interpreter. It uses the
installed MongoDBAPI package to create experiment-only collections and a
database branch that reuses an existing branch's immutable ontology assets.
It does not import or modify a DMW source checkout.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from dmw_experiments.shared.config.runtime_environment import (
    load_runtime_environment,
)
from dmw_experiments.studies.haiu_comparison.comparison_experiment.input_catalog import (
    HeaderSublemmaCatalog,
    canonical_json_sha256,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.paths import (
    RUN_TEMPLATE_ROOT,
    TEMPLATE_INPUT_ROOT,
)

EXPERIMENT_ROOT = RUN_TEMPLATE_ROOT
DEFAULT_CATALOG_PATH = (
    TEMPLATE_INPUT_ROOT / "header_sublemma_input_catalog.json"
)
DEFAULT_DATABASE_NAME = "UserData"
DEFAULT_BRANCH_REGISTRY_COLLECTION = "ontology_branches"
DEFAULT_ANNOTATION_COLLECTION = "annotations"
DEFAULT_ONTOLOGY_COLLECTION = "ontologies"
DEFAULT_RAW_COLLECTION = "RG_raw"
SAFE_STORAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_BRANCH_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class PairEnvironmentSpec:
    """Explicit storage and ontology-asset identity for one pair run.

    :param database_name: Logical MongoDB database used by DMW.
    :param raw_collection: New raw collection selected through
        ``RG_RAW_COLLECTION`` when DMW starts.
    :param branch_registry_collection: DMW branch-registry collection.
    :param annotation_base_collection: Base name used for scoped annotations.
    :param ontology_base_collection: Base name used for scoped ontologies.
    :param source_branch: Existing DMW branch that owns frozen ontology assets.
    :param target_branch: New database branch for isolated pair outputs.
    :param ontology_context_version: Frozen ontology version used by the run.
    """

    database_name: str
    raw_collection: str
    branch_registry_collection: str
    annotation_base_collection: str
    ontology_base_collection: str
    source_branch: str
    target_branch: str
    ontology_context_version: str


class PairEnvironmentRepository(Protocol):
    """Storage operations required by the experiment preparation workflow."""

    async def prepare(
        self,
        *,
        catalog: HeaderSublemmaCatalog,
        spec: PairEnvironmentSpec,
    ) -> dict[str, Any]:
        """Create or verify one isolated pair environment.

        :param catalog: Verified pair population.
        :param spec: Explicit target identities.
        :return: Stable source and target evidence.
        """
        ...

    async def close(self) -> None:
        """Close the database client owned by the runtime adapter."""
        ...


class MongoPairEnvironmentRepository:
    """MongoDBAPI-backed adapter loaded only in the frozen DMW runtime."""

    def __init__(self) -> None:
        # !! Dynamic boundary: MongoDBAPI is installed only in the separately
        # !! frozen DMW runtime, not in Haiu's development environment.
        self._database_connector = importlib.import_module(
            "MongoDBAPI.database_connector"
        )
        self._collection_scopes = importlib.import_module(
            "MongoDBAPI.collection_scopes"
        )

    async def prepare(
        self,
        *,
        catalog: HeaderSublemmaCatalog,
        spec: PairEnvironmentSpec,
    ) -> dict[str, Any]:
        """Create the raw population and database-only branch safely.

        :param catalog: Verified pair population.
        :param spec: Explicit isolated target identities.
        :return: Stable source and target evidence for the import manifest.
        :raises RuntimeError: If source state is missing or target state is not
            empty and exactly compatible.
        """
        scope = self._collection_scopes.build_annotation_ontology_scope(
            branch_slug=spec.target_branch,
            annotation_base_collection=spec.annotation_base_collection,
            ontology_base_collection=spec.ontology_base_collection,
            db_name=spec.database_name,
        )
        registry = await self._collection(spec, spec.branch_registry_collection)
        raw_collection = await self._collection(spec, spec.raw_collection)
        annotation_collection = await self._collection(
            spec, scope.annotation_collection_name
        )
        ontology_collection = await self._collection(
            spec, scope.ontology_collection_name
        )

        source_branch = await registry.find_one(
            {"branch_slug": spec.source_branch, "status": {"$ne": "deleted"}}
        )
        if not isinstance(source_branch, dict):
            raise RuntimeError(
                f"Source DMW branch does not exist: {spec.source_branch}."
            )
        expected_branch = _target_branch_record(
            source_branch=source_branch,
            spec=spec,
            annotation_collection=scope.annotation_collection_name,
            ontology_collection=scope.ontology_collection_name,
        )
        existing_target_branch = await registry.find_one(
            {"branch_slug": spec.target_branch}
        )
        if existing_target_branch is not None and not _branch_record_matches(
            existing_target_branch, expected_branch
        ):
            raise RuntimeError(
                "Target DMW branch exists with a different identity: "
                f"{spec.target_branch}."
            )
        source_collection_names = {
            source_branch.get("annotation_collection"),
            source_branch.get("ontology_collection"),
        }
        if (
            scope.annotation_collection_name in source_collection_names
            or scope.ontology_collection_name in source_collection_names
        ):
            raise RuntimeError(
                "Target DMW branch would reuse a source data collection."
            )
        if await annotation_collection.count_documents({}) != 0:
            raise RuntimeError(
                "Target annotation collection is not empty: "
                f"{scope.annotation_collection_name}."
            )
        if await ontology_collection.count_documents({}) != 0:
            raise RuntimeError(
                "Target ontology collection is not empty: "
                f"{scope.ontology_collection_name}."
            )

        expected_raw_documents = catalog.dmw_raw_documents()
        existing_raw_documents = await raw_collection.find(
            {},
            {"_id": 0, "id": 1, "header": 1, "subentries": 1},
        ).to_list(length=len(expected_raw_documents) + 1)
        if existing_raw_documents:
            expected_by_id = {
                str(document["id"]): document
                for document in expected_raw_documents
            }
            existing_by_id = {
                str(document.get("id") or ""): document
                for document in existing_raw_documents
            }
            if (
                len(existing_raw_documents) != len(expected_raw_documents)
                or existing_by_id != expected_by_id
            ):
                raise RuntimeError(
                    "Target raw collection contains data that differs from "
                    f"the catalogue: {spec.raw_collection}."
                )
        else:
            await raw_collection.insert_many(
                [dict(document) for document in expected_raw_documents],
                ordered=True,
            )
        await raw_collection.create_index("id", unique=True)

        if existing_target_branch is None:
            branch_document = {
                **expected_branch,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            await registry.insert_one(branch_document)

        await self._collection_scopes.ensure_branch_collections(scope)
        return {
            "source_branch": _portable_source_branch(source_branch),
            "target_branch": expected_branch,
            "collections": {
                "raw": spec.raw_collection,
                "annotation": scope.annotation_collection_name,
                "ontology": scope.ontology_collection_name,
                "branch_registry": spec.branch_registry_collection,
            },
            "raw_population": {
                "document_count": len(expected_raw_documents),
                "canonical_sha256": canonical_json_sha256(
                    expected_raw_documents
                ),
            },
        }

    async def close(self) -> None:
        """Close the MongoDBAPI client after preparation.

        :return: ``None``.
        """
        await self._database_connector.close_mongo_client()

    async def _collection(self, spec: PairEnvironmentSpec, name: str) -> Any:
        collection = await self._database_connector.get_collection(
            spec.database_name,
            name,
        )
        if collection is None:
            raise RuntimeError(f"MongoDB collection is unavailable: {name}.")
        return collection


def validate_spec(spec: PairEnvironmentSpec) -> None:
    """Reject ambiguous, unsafe, or non-isolated storage identities.

    :param spec: Candidate preparation configuration.
    :return: ``None`` after validation.
    :raises ValueError: If any identity could affect canonical experiment data.
    """
    named_values = {
        "database name": spec.database_name,
        "raw collection": spec.raw_collection,
        "branch registry collection": spec.branch_registry_collection,
        "annotation base collection": spec.annotation_base_collection,
        "ontology base collection": spec.ontology_base_collection,
    }
    for label, value in named_values.items():
        if not SAFE_STORAGE_NAME.fullmatch(value):
            raise ValueError(
                f"{label.capitalize()} must use only letters, numbers, "
                "underscores, and hyphens: "
                f"{value!r}."
            )
    for label, value in (
        ("source branch", spec.source_branch),
        ("target branch", spec.target_branch),
    ):
        if not SAFE_BRANCH_SLUG.fullmatch(value):
            raise ValueError(
                f"{label.capitalize()} must be a lowercase DMW branch slug: "
                f"{value!r}."
            )
    if spec.raw_collection == DEFAULT_RAW_COLLECTION:
        raise ValueError(
            "The canonical RG_raw collection cannot be used for pair inputs."
        )
    if spec.source_branch == spec.target_branch:
        raise ValueError("Source and target DMW branches must differ.")
    if not spec.ontology_context_version.strip():
        raise ValueError("Ontology context version must not be empty.")


def build_import_manifest(
    *,
    catalog: HeaderSublemmaCatalog,
    spec: PairEnvironmentSpec,
    storage_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build the non-secret import identity consumed by later run locks.

    :param catalog: Verified frozen population.
    :param spec: Explicit preparation configuration.
    :param storage_evidence: Stable values returned by the storage adapter.
    :return: Portable manifest without credentials, endpoints, or local paths.
    """
    payload = {
        "schema_version": 1,
        "purpose": "DMW header--sublemma pair environment",
        "catalogue": {
            "schema_version": 1,
            "unit_kind": "header_sublemma_pair",
            "file_sha256": catalog.file_sha256,
            "catalogue_content_sha256": catalog.content_sha256,
            "input_unit_count": len(catalog.records),
        },
        "ontology_context_version": spec.ontology_context_version,
        "database_name_sha256": hashlib.sha256(
            spec.database_name.encode("utf-8")
        ).hexdigest(),
        **storage_evidence,
    }
    payload["manifest_content_sha256"] = canonical_json_sha256(payload)
    return payload


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Write an import manifest atomically without replacing existing evidence.

    :param path: New destination file.
    :param payload: Non-secret manifest.
    :return: ``None``.
    :raises FileExistsError: If a manifest already exists at the destination.
    """
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(
            f"Import manifest already exists: {resolved}. Choose a new path."
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_suffix(f"{resolved.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(resolved)


async def prepare_pair_environment(
    *,
    repository: PairEnvironmentRepository,
    catalog: HeaderSublemmaCatalog,
    spec: PairEnvironmentSpec,
) -> dict[str, Any]:
    """Validate, prepare, and describe one isolated DMW environment.

    :param repository: Storage adapter for the frozen DMW runtime.
    :param catalog: Verified pair input population.
    :param spec: Explicit target storage and ontology identity.
    :return: Non-secret import manifest.
    """
    validate_spec(spec)
    try:
        evidence = await repository.prepare(catalog=catalog, spec=spec)
    finally:
        await repository.close()
    return build_import_manifest(
        catalog=catalog,
        spec=spec,
        storage_evidence=evidence,
    )


def _target_branch_record(
    *,
    source_branch: dict[str, Any],
    spec: PairEnvironmentSpec,
    annotation_collection: str,
    ontology_collection: str,
) -> dict[str, Any]:
    """Describe an isolated database branch that reuses frozen Git assets.

    :param source_branch: Existing source branch registry record.
    :param spec: Pair environment configuration.
    :param annotation_collection: New physical annotation collection.
    :param ontology_collection: New physical generated-ontology collection.
    :return: Stable target record without database-generated fields.
    :raises RuntimeError: If the source lacks a frozen Git asset identity.
    """
    github_branch = source_branch.get("github_branch")
    github_tag_scope = source_branch.get(
        "github_tag_scope"
    ) or source_branch.get("branch_slug")
    latest_version = source_branch.get("latest_version")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (github_branch, github_tag_scope, latest_version)
    ):
        raise RuntimeError(
            f"Source DMW branch is incomplete: {spec.source_branch}."
        )
    return {
        "branch_slug": spec.target_branch,
        "branch_name": f"Header--sublemma replication: {spec.target_branch}",
        "github_branch": github_branch,
        "github_tag_scope": github_tag_scope,
        "annotation_collection": annotation_collection,
        "ontology_collection": ontology_collection,
        "latest_version": latest_version,
        "status": "active",
        "creator_id": "haiu_header_sublemma_experiment",
    }


def _branch_record_matches(
    actual: dict[str, Any], expected: dict[str, Any]
) -> bool:
    """Check stable branch fields while ignoring timestamps and Mongo IDs.

    :param actual: Existing database branch record.
    :param expected: Target identity derived from the source branch.
    :return: Whether every expected field has the same stored value.
    """
    return all(actual.get(field) == value for field, value in expected.items())


def _portable_source_branch(source_branch: dict[str, Any]) -> dict[str, str]:
    """Select the source fields required to audit ontology asset reuse.

    :param source_branch: Existing database branch record.
    :return: Non-secret Git asset and version identity.
    """
    fields = (
        "branch_slug",
        "github_branch",
        "github_tag_scope",
        "latest_version",
    )
    return {field: str(source_branch.get(field) or "") for field in fields}


def _build_parser() -> argparse.ArgumentParser:
    """Build the isolated pair-environment command-line interface.

    :return: Parser with explicit source and target storage identities.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Load the frozen header--sublemma catalogue into an isolated DMW "
            "raw collection and database branch."
        )
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-branch", required=True)
    parser.add_argument("--target-branch", required=True)
    parser.add_argument("--raw-collection", required=True)
    parser.add_argument("--ontology-context-version", required=True)
    parser.add_argument(
        "--env-file",
        type=Path,
        action="append",
        required=True,
        help=(
            "Ignored runtime dotenv file containing MongoDB configuration. "
            "The path and values are not written to the manifest."
        ),
    )
    parser.add_argument("--mongo-db", default=DEFAULT_DATABASE_NAME)
    parser.add_argument(
        "--branch-registry-collection",
        default=DEFAULT_BRANCH_REGISTRY_COLLECTION,
    )
    parser.add_argument(
        "--annotation-base-collection",
        default=DEFAULT_ANNOTATION_COLLECTION,
    )
    parser.add_argument(
        "--ontology-base-collection",
        default=DEFAULT_ONTOLOGY_COLLECTION,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Prepare one isolated environment and write its immutable evidence.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Zero after verified preparation and manifest creation.
    """
    args = _build_parser().parse_args(argv)
    load_runtime_environment(tuple(args.env_file))
    catalog = load_header_sublemma_catalog(args.catalog)
    spec = PairEnvironmentSpec(
        database_name=args.mongo_db,
        raw_collection=args.raw_collection,
        branch_registry_collection=args.branch_registry_collection,
        annotation_base_collection=args.annotation_base_collection,
        ontology_base_collection=args.ontology_base_collection,
        source_branch=args.source_branch,
        target_branch=args.target_branch,
        ontology_context_version=args.ontology_context_version,
    )
    manifest = asyncio.run(
        prepare_pair_environment(
            repository=MongoPairEnvironmentRepository(),
            catalog=catalog,
            spec=spec,
        )
    )
    write_manifest(args.output, manifest)
    print(f"Prepared {len(catalog.records)} header--sublemma inputs.")
    print(f"Raw collection: {spec.raw_collection}")
    print(f"DMW database branch: {spec.target_branch}")
    print(f"Import manifest: {args.output.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
