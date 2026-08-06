"""Start an isolated DMW backend with local chat and remote embeddings."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from typing import Any


def _parser() -> argparse.ArgumentParser:
    """Build the launcher interface used by the parallel experiment.

    :return: Argument parser for local provider and DMW server settings.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run DMW with LM Studio for chat generation while retaining the "
            "configured Haiu provider for embeddings."
        )
    )
    parser.add_argument("--lmstudio-base-url", required=True)
    parser.add_argument("--model", default="qwen/qwen3.6-27b")
    parser.add_argument(
        "--lmstudio-model-id",
        default="qwen/qwen3.6-27b",
        help="Exact model ID advertised by LM Studio.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--max-tokens", type=int, default=60_000)
    parser.add_argument("--provider-timeout-seconds", type=int, default=3_600)
    parser.add_argument("--worker-timeout-seconds", type=int, default=7_200)
    return parser


def _apply_provider_split(
    *,
    lmstudio_base_url: str,
    model: str,
    max_tokens: int,
    provider_timeout_seconds: int,
    worker_timeout_seconds: int,
    lmstudio_model_id: str = "qwen/qwen3.6-27b",
) -> None:
    """Route chat to LM Studio and embeddings to the configured provider.

    DMW loads its dotenv files with override semantics during application
    import. This function therefore runs after that import, retains the
    configured Haiu endpoint and credential for embeddings, and then applies
    process-local chat overrides. Spawned DMW workers inherit the resulting
    environment.

    :param lmstudio_base_url: OpenAI-compatible LM Studio ``/v1`` endpoint.
    :param model: Exact model ID exposed by LM Studio.
    :param max_tokens: Completion cap shared by GTA ontology calls.
    :param provider_timeout_seconds: Timeout for one GTA provider request.
    :param worker_timeout_seconds: Timeout for one DMW ontology worker.
    :return: None.
    """
    academic_embedding_base_url = os.environ["HAIU_OPENAI_BASE_URL"]
    academic_embedding_api_key = os.environ["HAIU_OPENAI_API_KEY"]
    local_api_key = "lm-studio-local"

    os.environ.update(
        {
            "KISSKI_API_KEY": local_api_key,
            "KISSKI_BASE_URL": lmstudio_base_url,
            "KISSKI_MAX_TOKENS": str(max_tokens),
            "KISSKI_TIMEOUT_SECONDS": str(provider_timeout_seconds),
            "ONTOLOGY_WORKER_TIMEOUT_SECONDS": str(worker_timeout_seconds),
            "OPA_REQUIRE_SUCCESSFUL_RAG_RETRIEVAL": "true",
            "HAIU_OPENAI_API_KEY": local_api_key,
            "HAIU_OPENAI_BASE_URL": lmstudio_base_url,
            "HAIU_EMBEDDING_API_KEY": academic_embedding_api_key,
            "HAIU_EMBEDDING_BASE_URL": academic_embedding_base_url,
            "HAIU_MODEL_LLM": model,
            "HAIURAG_MODEL_LLM": model,
            "LMSTUDIO_MODEL_ID": lmstudio_model_id,
            "HAIU_TIMEOUT_LLM": "2400",
            "HAIU_MAX_RETRIES": "3",
            "PYTHONUNBUFFERED": "1",
        }
    )

    # > DMW imports and bootstraps Haiu before this launcher can apply the
    # > split. Rebind AppRC from the updated process environment so newly
    # > constructed HaiuRC instances (including spawned workers) see the
    # > AcademicCloud embedding endpoint instead of the previous chat URL.
    from haiu.config import HAIU_CONFIG

    HAIU_CONFIG.bootstrap(load_dotenv_layers=False)


def _load_dmw_app() -> Any:
    """Import the ASGI application from the installed DMW distribution.

    The publication runtime installs DMW v1.1.3 as a non-editable package.
    Importing the public package path keeps the launcher independent from a
    neighboring source checkout. The redaction hook must run before importing
    the application because DMW's compatibility module imports MongoDBAPI
    before the application installs that hook itself.

    :return: FastAPI application exported by the installed DMW package.
    """
    from datamodel_workflow.runtime_bootstrap import (
        install_global_log_redaction,
    )

    install_global_log_redaction()

    from datamodel_workflow.app import app

    return app


def _load_dmw_dotenv_layers() -> None:
    """Load the repository configuration required before importing DMW.

    The academic backend starts with these layers so DMW can initialize MongoDB
    and the remote embedding client during application import. The LM Studio
    launcher needs the same pre-import environment; it changes only the chat
    provider after the application is available.

    :return: ``None`` after loading the documented repository dotenv layers.
    """
    from dotenv import load_dotenv

    load_dotenv(".env.mk", override=True)
    load_dotenv(".env", override=True)
    load_dotenv("../haiu/.env", override=False)


def main(argv: Sequence[str] | None = None) -> int:
    """Load DMW, apply process-local routing, and serve the application.

    A real script entrypoint is required because DMW creates workers with the
    multiprocessing ``spawn`` context. Launching the server from standard
    input leaves those workers without an importable parent module.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Process exit status after the server stops.
    """
    args = _parser().parse_args(argv)

    # > DMW initializes MongoDB during application import, before the local
    # > chat-provider split can safely replace only generation settings.
    _load_dmw_dotenv_layers()
    app = _load_dmw_app()

    _apply_provider_split(
        lmstudio_base_url=args.lmstudio_base_url,
        model=args.model,
        max_tokens=args.max_tokens,
        provider_timeout_seconds=args.provider_timeout_seconds,
        worker_timeout_seconds=args.worker_timeout_seconds,
        lmstudio_model_id=args.lmstudio_model_id,
    )
    split_is_valid = (
        os.environ["KISSKI_BASE_URL"] == os.environ["HAIU_OPENAI_BASE_URL"]
        and os.environ["HAIU_EMBEDDING_BASE_URL"]
        != os.environ["HAIU_OPENAI_BASE_URL"]
        and os.environ["HAIURAG_MODEL_LLM"] == args.model
        and os.environ["HAIU_EMBEDDING_API_KEY"]
        != os.environ["HAIU_OPENAI_API_KEY"]
    )
    print(
        "lmstudio_backend_provider_split="
        f"{str(split_is_valid).lower()} "
        f"chat_base_url={os.environ['KISSKI_BASE_URL']} "
        f"embedding_base_url={os.environ['HAIU_EMBEDDING_BASE_URL']}",
        flush=True,
    )
    if not split_is_valid:
        raise RuntimeError(
            "LM Studio chat and embedding provider split is invalid."
        )

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
