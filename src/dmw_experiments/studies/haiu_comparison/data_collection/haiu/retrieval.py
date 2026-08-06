"""Standalone Haiu retrieval for the non-DMW ontologizer condition."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from haiu import HaiuRC
from haiu.rag import RAGWorkspace

from dmw_experiments.studies.haiu_comparison.model.traces import (
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.data_collection.haiu.workspace import (
    run_workspace_operation,
)


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    """Exact standalone retrieval context supplied to the planner.

    :param query: Raw regest query sent to Haiu retrieval.
    :param turtle: Exact Turtle context supplied to Stage 1.
    :param snapshot: Portable native retrieval graph and metadata.
    :param duration_seconds: Observed retrieval wall-clock duration.
    """

    query: str
    turtle: str
    snapshot: dict[str, Any]
    duration_seconds: float


def retrieve_regest_context(
    *, regest: RegestText, rc: HaiuRC
) -> RetrievalTrace:
    """Retrieve standalone ontology context from the canonical Haiu workspace.

    This deliberately calls Haiu directly rather than the DMW workflow. The
    returned Turtle and graph snapshot are retained verbatim by the experiment
    artifact writer before either LLM stage starts.

    :param regest: Raw source text used as the retrieval query.
    :param rc: Resolved Haiu runtime configuration.
    :return: Exact retrieval trace for one standalone observation.
    """
    return run_workspace_operation(
        _aretrieve_regest_context(regest=regest, rc=rc)
    )


async def _aretrieve_regest_context(
    *, regest: RegestText, rc: HaiuRC
) -> RetrievalTrace:
    query = regest.full_text()
    if not query:
        raise ValueError(
            "Cannot retrieve ontology context for an empty regest."
        )

    workspace = RAGWorkspace(
        rag_rc=rc.rag,
        client_rc=rc.client,
        workspace_ref=rc.rag.workspace_layout.canonical_ref(),
    )
    started = time.perf_counter()
    try:
        await workspace.init_lightrag_workspace(read_only=True)
        param = rc.rag.query_param(
            mode="hybrid",
            only_need_context=True,
            stream=False,
        )
        turtle, graph, metadata = await workspace.aquery_turtle(
            retrieval_query=query,
            param=param,
            keyword_llm_assist=False,
            include_lexicals=True,
            export_base=None,
        )
        if not turtle.strip():
            raise RuntimeError("Haiu retrieval returned empty Turtle context.")
        snapshot = {
            "snapshot_fidelity": "native_full_graph",
            "source": "haiu_standalone_native_snapshot",
            "retrieval_mode": "hybrid",
            "query": query,
            "workspace": {
                "workspace_name": workspace.workspace.workspace_name,
                "workspace_key": workspace.workspace.lightrag_workspace,
                "corpus_profile": workspace.workspace.corpus_profile,
            },
            "graph": graph.to_dict(),
            "metadata": _portable_metadata(metadata),
            "retrieved_turtle_sha256": hashlib.sha256(
                turtle.encode("utf-8")
            ).hexdigest(),
        }
        return RetrievalTrace(
            query=query,
            turtle=turtle,
            snapshot=snapshot,
            duration_seconds=round(time.perf_counter() - started, 3),
        )
    finally:
        await workspace.aclose()


def _portable_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop host-specific paths from a native retrieval metadata payload.

    :param metadata: Metadata returned by the workspace query.
    :return: Portable recursively filtered metadata.
    """
    return _portable_value(metadata)


def _portable_value(value: Any) -> Any:
    """Recursively remove fields that could expose a local filesystem path.

    :param value: Native metadata value.
    :return: JSON-compatible portable representation.
    """
    if isinstance(value, dict):
        return {
            str(key): _portable_value(item)
            for key, item in value.items()
            if "path" not in str(key).lower()
            and "workdir" not in str(key).lower()
        }
    if isinstance(value, list):
        return [_portable_value(item) for item in value]
    return value
