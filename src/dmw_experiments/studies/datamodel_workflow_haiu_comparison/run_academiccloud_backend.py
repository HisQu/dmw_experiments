"""Start DMW against an isolated raw collection for an AcademicCloud run."""

from __future__ import annotations

import argparse
import importlib
import os
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

SAFE_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class DmwEnvironmentModule(Protocol):
    """Dynamic DMW dotenv interface available in the publication runtime."""

    load_dotenv: Callable[..., Any]


class RawCollectionModule(Protocol):
    """Dynamic MongoDBAPI selector exposed by the publication runtime."""

    RG_RAW_COLLECTION_NAME: str


def _parser() -> argparse.ArgumentParser:
    """Build the isolated AcademicCloud backend launcher interface.

    :return: Parser for the physical raw collection and Uvicorn settings.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-collection", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-tokens", type=int, default=60_000)
    return parser


def _load_dmw_dotenv_layers() -> None:
    """Load DMW's documented repository configuration before application import.

    The installed DMW application requires these layers to resolve MongoDB and
    the AcademicCloud provider. The raw-collection override is installed
    separately because DMW reloads dotenv files during its own bootstrap.

    :return: ``None`` after loading the required environment layers.
    """
    from dotenv import load_dotenv

    load_dotenv(".env.mk", override=True)
    load_dotenv(".env", override=True)
    load_dotenv("../haiu/.env", override=False)


def _install_raw_collection_override(
    *,
    raw_collection: str,
    max_tokens: int,
) -> None:
    """Preserve isolated storage settings across DMW's dotenv reload.

    DMW's startup calls its own dotenv loader with override semantics. This
    hook reapplies the explicit experiment collection and generation cap after
    every such reload, before MongoDBAPI is imported by the application.

    :param raw_collection: Experiment-only MongoDB raw collection identity.
    :param max_tokens: DMW generation cap advertised to workflow workers.
    :return: ``None`` after installing the process-local bootstrap hook.
    """
    env = cast(
        DmwEnvironmentModule,
        importlib.import_module("datamodel_workflow.env"),
    )
    original_load_dotenv = env.load_dotenv

    def load_dotenv_and_restore_experiment_scope(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = original_load_dotenv(*args, **kwargs)
        os.environ["RG_RAW_COLLECTION"] = raw_collection
        os.environ["KISSKI_MAX_TOKENS"] = str(max_tokens)
        return result

    env.load_dotenv = load_dotenv_and_restore_experiment_scope
    os.environ["RG_RAW_COLLECTION"] = raw_collection
    os.environ["KISSKI_MAX_TOKENS"] = str(max_tokens)


def _load_dmw_app() -> Any:
    """Import DMW from the installed publication distribution.

    :return: FastAPI application exported by the installed DMW package.
    """
    from datamodel_workflow.runtime_bootstrap import (
        install_global_log_redaction,
    )

    install_global_log_redaction()

    from datamodel_workflow.app import app

    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Serve DMW with a verified, isolated AcademicCloud raw collection.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Process exit status after the server stops.
    """
    args = _parser().parse_args(argv)
    if not SAFE_COLLECTION_NAME.fullmatch(args.raw_collection):
        raise SystemExit("--raw-collection is not a safe collection identity.")
    if args.max_tokens <= 0:
        raise SystemExit("--max-tokens must be positive.")

    _load_dmw_dotenv_layers()
    _install_raw_collection_override(
        raw_collection=args.raw_collection,
        max_tokens=args.max_tokens,
    )
    app = _load_dmw_app()

    # > MongoDBAPI also keeps a module-level collection selector. Set it after
    # > DMW import so the API routes and spawned workers use the same scope.
    raw_collection_module = cast(
        RawCollectionModule,
        importlib.import_module("MongoDBAPI.RG_raw"),
    )

    raw_collection_module.RG_RAW_COLLECTION_NAME = os.environ[
        "RG_RAW_COLLECTION"
    ]
    print(
        "academiccloud_backend_scope="
        f"{raw_collection_module.RG_RAW_COLLECTION_NAME} "
        f"max_tokens={os.environ['KISSKI_MAX_TOKENS']}",
        flush=True,
    )

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
