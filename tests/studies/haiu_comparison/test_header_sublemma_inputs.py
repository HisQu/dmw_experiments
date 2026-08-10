from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dmw_experiments.studies.haiu_comparison.model.inputs import (
    HeaderSublemmaCatalog,
    canonical_json_sha256,
    load_dmw_pair_import_manifest,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.preparation.dmw_storage import (
    MongoPairEnvironmentRepository,
    PairEnvironmentSpec,
    build_import_manifest,
    prepare_pair_environment,
    validate_spec,
    write_manifest,
)


def test_catalogue_loader_preserves_pair_text_and_lineage(
    tmp_path: Path,
) -> None:
    catalog_path = _write_catalog(tmp_path)

    catalog = load_header_sublemma_catalog(catalog_path)

    assert len(catalog.records) == 2
    first = catalog.records[0]
    assert first.input_unit_id == "hsp-100-s01"
    assert first.as_regest_text().subentries == ("First sublemma",)
    assert first.lineage()["source_sublemma_number"] == 1


def test_template_catalogue_records_targeted_input_normalization() -> None:
    repository_root = Path(__file__).parents[3]
    catalog_path = (
        repository_root
        / "studies_run_templates/haiu_comparison/template/INPUTS"
        / "header_sublemma_input_catalog.json"
    )

    catalog = load_header_sublemma_catalog(catalog_path)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert len(catalog.records) == 480
    assert payload["normalization"] == {
        "schema_version": 1,
        "name": "remove_legacy_regest_formatting_controls",
        "removed_tokens": ["&w&w", "&w&", "&w", "&y"],
        "rule": (
            "Remove obsolete TUSTEP layout controls and collapse whitespace "
            "only in fields containing a control; preserve all other fields "
            "byte-for-byte."
        ),
        "normalized_input_unit_count": 44,
        "normalized_source_regest_count": 9,
        "normalized_source_regest_ids": [
            "11002033",
            "11002971",
            "11007321",
            "11007477",
            "11007478",
            "11007990",
            "11009069",
            "11009463",
            "11009587",
        ],
        "normalized_header_count": 9,
        "normalized_sublemma_count": 0,
    }


def test_catalogue_loader_rejects_modified_record(tmp_path: Path) -> None:
    catalog_path = _write_catalog(tmp_path)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload["records"][0]["sublemma"] = "Changed"
    catalog_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="catalogue content hash"):
        load_header_sublemma_catalog(catalog_path)


def test_catalogue_loader_rejects_legacy_layout_controls(
    tmp_path: Path,
) -> None:
    catalog_path = _write_catalog(tmp_path)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    record = payload["records"][0]
    record["header"] = "Frozen &w&w header &y"
    record.pop("content_sha256")
    record["content_sha256"] = canonical_json_sha256(record)
    payload.pop("catalogue_content_sha256")
    payload["catalogue_content_sha256"] = canonical_json_sha256(payload)
    catalog_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="legacy formatting token"):
        load_header_sublemma_catalog(catalog_path)


def test_import_manifest_binds_catalogue_and_collection_identity(
    tmp_path: Path,
) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    spec = _spec()
    payload = build_import_manifest(
        catalog=catalog,
        spec=spec,
        storage_evidence=_storage_evidence(spec, catalog=catalog),
    )
    manifest_path = tmp_path / "import.json"
    write_manifest(manifest_path, payload)

    manifest = load_dmw_pair_import_manifest(manifest_path, catalog=catalog)

    assert manifest.collections["raw"] == spec.raw_collection
    assert manifest.target_branch["branch_slug"] == spec.target_branch
    assert manifest.ontology_context_version == "1.15.0"


def test_import_manifest_rejects_rehashed_wrong_raw_population(
    tmp_path: Path,
) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    spec = _spec()
    payload = build_import_manifest(
        catalog=catalog,
        spec=spec,
        storage_evidence=_storage_evidence(spec, catalog=catalog),
    )
    raw_population = payload["raw_population"]
    assert isinstance(raw_population, dict)
    raw_population["document_count"] = 1
    payload.pop("manifest_content_sha256")
    payload["manifest_content_sha256"] = canonical_json_sha256(payload)
    manifest_path = tmp_path / "wrong_raw_population.json"
    write_manifest(manifest_path, payload)

    with pytest.raises(ValueError, match="raw population"):
        load_dmw_pair_import_manifest(manifest_path, catalog=catalog)


def test_preparation_rejects_canonical_raw_collection() -> None:
    spec = replace(_spec(), raw_collection="RG_raw")

    with pytest.raises(ValueError, match="canonical RG_raw"):
        validate_spec(spec)


def test_preparation_rejects_non_dmw_branch_slug() -> None:
    spec = replace(_spec(), target_branch="Pair AcademicCloud")

    with pytest.raises(ValueError, match="lowercase DMW branch slug"):
        validate_spec(spec)


@pytest.mark.asyncio
async def test_mongo_preparation_creates_and_verifies_pristine_state(
    tmp_path: Path,
) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    spec = _spec()
    connector = _FakeConnector(
        {
            spec.branch_registry_collection: _FakeCollection(
                [
                    {
                        "branch_slug": spec.source_branch,
                        "github_branch": "publication-academiccloud",
                        "github_tag_scope": "publication-academiccloud",
                        "latest_version": "1.15.0",
                        "status": "active",
                    }
                ]
            ),
            spec.raw_collection: _FakeCollection([]),
            "annotations__pair_academiccloud": _FakeCollection([]),
            "ontologies__pair_academiccloud": _FakeCollection([]),
        }
    )
    scopes = _FakeScopes()
    repository = MongoPairEnvironmentRepository.__new__(
        MongoPairEnvironmentRepository
    )
    repository._database_connector = connector
    repository._collection_scopes = scopes

    first = await repository.prepare(catalog=catalog, spec=spec)
    second = await repository.prepare(catalog=catalog, spec=spec)

    raw = connector.collections[spec.raw_collection]
    assert raw.documents == catalog.dmw_raw_documents()
    assert raw.insert_many_calls == 1
    assert first == second
    assert scopes.ensure_calls == 2


@pytest.mark.asyncio
async def test_mongo_preparation_refuses_conflicting_raw_state(
    tmp_path: Path,
) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    spec = _spec()
    connector = _FakeConnector(
        {
            spec.branch_registry_collection: _FakeCollection(
                [
                    {
                        "branch_slug": spec.source_branch,
                        "github_branch": spec.source_branch,
                        "github_tag_scope": spec.source_branch,
                        "latest_version": "1.15.0",
                        "status": "active",
                    }
                ]
            ),
            spec.raw_collection: _FakeCollection(
                [{"id": "foreign", "header": "Wrong", "subentries": []}]
            ),
            "annotations__pair_academiccloud": _FakeCollection([]),
            "ontologies__pair_academiccloud": _FakeCollection([]),
        }
    )
    repository = MongoPairEnvironmentRepository.__new__(
        MongoPairEnvironmentRepository
    )
    repository._database_connector = connector
    repository._collection_scopes = _FakeScopes()

    with pytest.raises(RuntimeError, match="differs from the catalogue"):
        await repository.prepare(catalog=catalog, spec=spec)


@pytest.mark.asyncio
async def test_mongo_preparation_checks_branch_before_inserting_raw(
    tmp_path: Path,
) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    spec = _spec()
    raw_collection = _FakeCollection([])
    connector = _FakeConnector(
        {
            spec.branch_registry_collection: _FakeCollection(
                [
                    {
                        "branch_slug": spec.source_branch,
                        "github_branch": spec.source_branch,
                        "github_tag_scope": spec.source_branch,
                        "latest_version": "1.15.0",
                        "status": "active",
                    },
                    {
                        "branch_slug": spec.target_branch,
                        "github_branch": "different-assets",
                    },
                ]
            ),
            spec.raw_collection: raw_collection,
            "annotations__pair_academiccloud": _FakeCollection([]),
            "ontologies__pair_academiccloud": _FakeCollection([]),
        }
    )
    repository = MongoPairEnvironmentRepository.__new__(
        MongoPairEnvironmentRepository
    )
    repository._database_connector = connector
    repository._collection_scopes = _FakeScopes()

    with pytest.raises(RuntimeError, match="different identity"):
        await repository.prepare(catalog=catalog, spec=spec)

    assert raw_collection.documents == []
    assert raw_collection.insert_many_calls == 0


@pytest.mark.asyncio
async def test_prepare_workflow_closes_repository(tmp_path: Path) -> None:
    catalog = load_header_sublemma_catalog(_write_catalog(tmp_path))
    repository = _FakeRepository(_storage_evidence(_spec(), catalog=catalog))

    manifest = await prepare_pair_environment(
        repository=repository,
        catalog=catalog,
        spec=_spec(),
    )

    assert repository.closed is True
    assert manifest["catalogue"]["input_unit_count"] == 2
    assert "path" not in json.dumps(manifest).lower()


def test_import_manifest_never_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest(path, {"schema_version": 1})

    with pytest.raises(FileExistsError, match="already exists"):
        write_manifest(path, {"schema_version": 1})


def _write_catalog(tmp_path: Path) -> Path:
    source_digest = "a" * 64
    records = []
    for index, sublemma in enumerate(("First sublemma", "Second sublemma")):
        record: dict[str, Any] = {
            "input_unit_id": f"hsp-100-s{index + 1:02d}",
            "source_regest_id": "100",
            "source_subentry_index": index,
            "source_sublemma_number": index + 1,
            "header": "Frozen header",
            "sublemma": sublemma,
            "source_regest_content_sha256": source_digest,
        }
        record["content_sha256"] = canonical_json_sha256(record)
        records.append(record)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "unit_kind": "header_sublemma_pair",
        "description": "test",
        "source": {"source_run_id": "source-run"},
        "selection": {
            "source_regest_count": 1,
            "input_unit_count": len(records),
            "excluded_header_only_regest_count": 0,
            "excluded_header_only_regest_ids": [],
        },
        "records": records,
    }
    payload["catalogue_content_sha256"] = canonical_json_sha256(payload)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _spec() -> PairEnvironmentSpec:
    return PairEnvironmentSpec(
        database_name="UserData",
        raw_collection="RG_raw_pair_academiccloud",
        branch_registry_collection="ontology_branches",
        annotation_base_collection="annotations",
        ontology_base_collection="ontologies",
        source_branch="publication-academiccloud",
        target_branch="pair_academiccloud",
        ontology_context_version="1.15.0",
    )


def _storage_evidence(
    spec: PairEnvironmentSpec,
    *,
    catalog: HeaderSublemmaCatalog,
) -> dict[str, Any]:
    return {
        "source_branch": {
            "branch_slug": spec.source_branch,
            "github_branch": spec.source_branch,
            "github_tag_scope": spec.source_branch,
            "latest_version": "1.15.0",
        },
        "target_branch": {
            "branch_slug": spec.target_branch,
            "branch_name": f"Header--sublemma replication: {spec.target_branch}",
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


class _FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    async def to_list(self, *, length: int) -> list[dict[str, Any]]:
        return [dict(document) for document in self.documents[:length]]


class _FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = [dict(document) for document in documents]
        self.insert_many_calls = 0

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for document in self.documents:
            if all(
                document.get(field) == value
                for field, value in query.items()
                if not isinstance(value, dict)
            ):
                return dict(document)
        return None

    async def count_documents(self, _query: dict[str, Any]) -> int:
        return len(self.documents)

    def find(
        self,
        _query: dict[str, Any],
        _projection: dict[str, int],
    ) -> _FakeCursor:
        return _FakeCursor(self.documents)

    async def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def insert_many(
        self,
        documents: list[dict[str, Any]],
        *,
        ordered: bool,
    ) -> None:
        assert ordered is True
        self.insert_many_calls += 1
        self.documents.extend(dict(document) for document in documents)

    async def insert_one(self, document: dict[str, Any]) -> None:
        portable = {
            key: value
            for key, value in document.items()
            if key not in {"created_at", "updated_at"}
        }
        self.documents.append(portable)


class _FakeConnector:
    def __init__(self, collections: dict[str, _FakeCollection]) -> None:
        self.collections = collections

    async def get_collection(
        self, _database_name: str, collection_name: str
    ) -> _FakeCollection | None:
        return self.collections.get(collection_name)

    async def close_mongo_client(self) -> None:
        return None


class _FakeScopes:
    def __init__(self) -> None:
        self.ensure_calls = 0

    def build_annotation_ontology_scope(self, **kwargs: Any) -> Any:
        branch = kwargs["branch_slug"]
        return SimpleNamespace(
            annotation_collection_name=f"annotations__{branch}",
            ontology_collection_name=f"ontologies__{branch}",
        )

    async def ensure_branch_collections(self, _scope: Any) -> None:
        self.ensure_calls += 1


class _FakeRepository:
    def __init__(self, evidence: dict[str, Any]) -> None:
        self.evidence = evidence
        self.closed = False

    async def prepare(
        self,
        *,
        catalog: Any,
        spec: Any,
    ) -> dict[str, Any]:
        assert len(catalog.records) == 2
        assert spec.target_branch == "pair_academiccloud"
        return self.evidence

    async def close(self) -> None:
        self.closed = True
