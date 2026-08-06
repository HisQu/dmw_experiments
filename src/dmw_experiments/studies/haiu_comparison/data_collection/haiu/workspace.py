"""Shared reference workspace preparation for both Haiu-RAG conditions."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Coroutine, TypeVar

from haiu import HaiuRC, RAGWorkspaceManager
from opa.rag.haiu_workspace_registry import (
    assert_or_register_workdir_identity,
    build_manifest,
    load_manifest,
    make_rc_for_ref,
    manifest_matches,
    manifest_path,
    write_manifest,
)
from opa.rag.ontology_ref import OntologyRef, ttl_sha256, workdir_base_for

from dmw_experiments.studies.haiu_comparison.model.inputs import (
    DmwPairImportManifest,
)


_Result = TypeVar("_Result")
_WORKSPACE_LOOP: asyncio.AbstractEventLoop | None = None


@dataclass(frozen=True, slots=True)
class PreparedReferenceWorkspace:
    """Verified branch-aware workspace shared by both retrieval conditions.

    :param rc: Haiu configuration derived for the immutable ontology ref.
    :param ontology_ref: Exact Git and content identity used by DMW.
    :param embedding_model: Embedding model that owns the index.
    :param synchronized: Whether this invocation had to rebuild the index.
    :param sync_result: Haiu indexing counts when synchronization ran.
    """

    rc: HaiuRC
    ontology_ref: OntologyRef
    embedding_model: str
    synchronized: bool
    sync_result: dict[str, int] | None

    def manifest_entry(self) -> dict[str, Any]:
        """Return the stable workspace contract for frozen provenance.

        The action-specific synchronization result is deliberately omitted.
        A resumed process must produce the same immutable run manifest after
        finding the index already prepared.

        :return: Portable reference and index identity without local paths.
        """
        return {
            "preparation": "verified_before_condition_timing",
            "ontology_ref": self.ontology_ref.model_dump(),
            "embedding_model": self.embedding_model,
            "workdir_base": workdir_base_for(self.ontology_ref).as_posix(),
            "workspace": "canonical",
        }


def prepare_reference_workspace(
    *,
    base_rc: HaiuRC,
    contract_path: Path,
    reference_ontology_path: Path,
    dmw_input_manifest: DmwPairImportManifest,
) -> PreparedReferenceWorkspace:
    """Prepare the exact reference index before timed conditions begin.

    The copied run's retrieval contract is checked against the frozen Turtle,
    the isolated DMW branch, and the effective runtime. Haiu then verifies or
    atomically synchronizes the branch-aware canonical workspace. Direct Haiu
    retrieval receives the derived configuration, while DMW resolves the same
    ontology ref independently through its published API.

    :param base_rc: Resolved provider and storage configuration.
    :param contract_path: Tracked portable retrieval-workspace contract.
    :param reference_ontology_path: Frozen reference Turtle input.
    :param dmw_input_manifest: Prepared DMW branch and collection evidence.
    :return: Derived runtime and stable reference identity.
    """
    payload = _load_contract(contract_path)
    ontology_ref = OntologyRef.model_validate(payload["ontology_ref"])
    ontology_turtle = reference_ontology_path.read_text(encoding="utf-8")
    if not ontology_turtle.strip():
        raise ValueError("Reference ontology input is empty.")
    _validate_contract(
        payload=payload,
        ontology_ref=ontology_ref,
        ontology_turtle=ontology_turtle,
        base_rc=base_rc,
        dmw_input_manifest=dmw_input_manifest,
    )
    derived_rc = make_rc_for_ref(ontology_ref, base_rc=base_rc)
    synchronized, sync_result = run_workspace_operation(
        _prepare_workspace(
            rc=derived_rc,
            ontology_ref=ontology_ref,
            ontology_turtle=ontology_turtle,
        )
    )
    return PreparedReferenceWorkspace(
        rc=derived_rc,
        ontology_ref=ontology_ref,
        embedding_model=base_rc.rag.haiu_settings.model_embed,
        synchronized=synchronized,
        sync_result=sync_result,
    )


def run_workspace_operation(
    operation: Coroutine[Any, Any, _Result],
) -> _Result:
    """Run Haiu workspace work on one process-long event loop.

    LightRAG storage retains asyncio synchronization primitives. One loop for
    preparation and all later direct queries prevents those primitives from
    becoming attached to a loop closed after an earlier input.

    :param operation: Awaitable Haiu workspace operation.
    :return: Operation result.
    """
    global _WORKSPACE_LOOP
    if _WORKSPACE_LOOP is None or _WORKSPACE_LOOP.is_closed():
        _WORKSPACE_LOOP = asyncio.new_event_loop()
    return _WORKSPACE_LOOP.run_until_complete(operation)


async def _prepare_workspace(
    *,
    rc: HaiuRC,
    ontology_ref: OntologyRef,
    ontology_turtle: str,
) -> tuple[bool, dict[str, int] | None]:
    _ensure_workspace_storage(rc)
    assert_or_register_workdir_identity(ontology_ref, rc=rc)
    embedding_model = rc.rag.haiu_settings.model_embed
    manifest_file = manifest_path(ontology_ref, rc=rc)
    existing_manifest = load_manifest(manifest_file)
    manager = RAGWorkspaceManager(rag_rc=rc.rag, client_rc=rc.client)
    canonical = manager.canonical_workspace()
    synchronized = False
    sync_result: dict[str, int] | None = None
    try:
        if manifest_matches(
            existing_manifest,
            ontology_ref,
            embedding_model=embedding_model,
        ):
            try:
                await canonical.init_lightrag_workspace(read_only=True)
            except Exception:
                # > A matching registry file is insufficient when its
                # > canonical workspace is missing or incomplete. Haiu's
                # > backends expose different concrete initialization errors,
                # > so any failed verification requires an atomic rebuild.
                existing_manifest = None

        if not manifest_matches(
            existing_manifest,
            ontology_ref,
            embedding_model=embedding_model,
        ):
            sync_result = await manager.sync_rdfsowl(
                graph_data=ontology_turtle,
                format="turtle",
                provenance_label=_provenance_label(ontology_ref),
            )
            synchronized = True
            write_manifest(
                manifest_file,
                build_manifest(
                    ontology_ref,
                    embedding_model=embedding_model,
                ),
            )
            await canonical.aclose()
            canonical = manager.canonical_workspace()
            await canonical.init_lightrag_workspace(read_only=True)
        return synchronized, sync_result
    finally:
        await canonical.aclose()


def _ensure_workspace_storage(rc: HaiuRC) -> None:
    """Create the run-owned root required by Haiu's YAML bundle writer.

    Haiu intentionally refuses to invent its upstream storage root while
    exporting an RDF-derived CustomKG. A fresh experiment storage has no
    corpus tree yet, so the harness owns this one-time initialization before
    asking the published synchronizer to write below it.

    :param rc: Branch-derived Haiu runtime configuration.
    :return: None.
    """
    customkg_root = rc.rag.storage.fpb_customkg_yaml.parent.parent
    customkg_root.mkdir(parents=True, exist_ok=True)


def _load_contract(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Cannot read retrieval workspace contract: {path}."
        ) from exc
    if not isinstance(payload, dict) or payload.get("snapshot_schema") != 2:
        raise ValueError(
            "Retrieval workspace contract must use snapshot_schema 2."
        )
    if not isinstance(payload.get("ontology_ref"), dict):
        raise ValueError(
            "Retrieval workspace contract has no ontology_ref object."
        )
    return payload


def _validate_contract(
    *,
    payload: dict[str, Any],
    ontology_ref: OntologyRef,
    ontology_turtle: str,
    base_rc: HaiuRC,
    dmw_input_manifest: DmwPairImportManifest,
) -> None:
    target_branch = dmw_input_manifest.target_branch
    tag_scope = str(target_branch["github_tag_scope"])
    version = dmw_input_manifest.ontology_context_version.removeprefix("v")
    expected_ref_name = f"{tag_scope}_v{version}"
    expected_repository = _ontology_repository_name()
    expected = {
        "repo": expected_repository,
        "ref_type": "tag",
        "ref_name": expected_ref_name,
        "base_ref_name": str(target_branch["github_branch"]),
        "ttl_sha256": ttl_sha256(ontology_turtle),
    }
    actual = ontology_ref.model_dump()
    mismatches = {
        field: {"expected": value, "actual": actual.get(field)}
        for field, value in expected.items()
        if actual.get(field) != value
    }
    if mismatches:
        raise ValueError(
            "Retrieval workspace contract does not match the frozen DMW "
            f"reference identity: {mismatches}."
        )
    embedding_model = base_rc.rag.haiu_settings.model_embed
    if payload.get("embedding_model") != embedding_model:
        raise ValueError(
            "Retrieval workspace embedding model does not match the "
            f"effective runtime: {payload.get('embedding_model')!r} != "
            f"{embedding_model!r}."
        )
    if payload.get("retrieval_mode") != "hybrid":
        raise ValueError("Retrieval workspace mode must be 'hybrid'.")
    if payload.get("workspace") != "canonical":
        raise ValueError("Retrieval workspace must be 'canonical'.")


def _ontology_repository_name() -> str:
    repository = os.getenv("GITHUB_ONTOLOGY_REPO_NAME", "").strip()
    if not repository:
        raise ValueError(
            "GITHUB_ONTOLOGY_REPO_NAME is required by the retrieval "
            "workspace contract."
        )
    return repository if "/" in repository else f"HisQu/{repository}"


def _provenance_label(ontology_ref: OntologyRef) -> str:
    commit = f":{ontology_ref.commit_sha}" if ontology_ref.commit_sha else ""
    return (
        f"{ontology_ref.repo}@{ontology_ref.ref_type}:"
        f"{ontology_ref.ref_name}{commit}"
    )
