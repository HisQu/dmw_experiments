"""Validate and bootstrap one copied run's effective environment."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dotenv import dotenv_values, load_dotenv

from dmw_experiments.shared.config.app import APP_RC
from dmw_experiments.shared.config.owners import StudyRuntimeConfig


class RunExecution(Protocol):
    """Fields required to resolve one provider-specific runtime layer."""

    @property
    def name(self) -> str:
        """Return the provider execution identity."""
        ...

    @property
    def env_file(self) -> Path:
        """Return the run-relative provider override file."""
        ...

    @property
    def raw_collection(self) -> str:
        """Return the isolated raw-input collection."""
        ...

    @property
    def annotation_collection(self) -> str:
        """Return the isolated annotation collection."""
        ...

    @property
    def ontology_collection(self) -> str:
        """Return the isolated ontology collection."""
        ...


RUN_ENV_SECRET_KEYS = frozenset(
    {
        "DATAMODEL_LOGIN",
        "DATAMODEL_PASSWORD",
        "JWT_SECRET",
        "MONGO_URI",
        "GITHUB_TOKEN",
        "KISSKI_API_KEY",
        "HAIU_OPENAI_API_KEY",
        "HAIU_EMBEDDING_API_KEY",
    }
)
RUN_ENV_DERIVED_KEYS = frozenset(
    {
        "RG_RAW_COLLECTION",
        "ANNOTATION_COLLECTION",
        "ONTOLOGIES_COLLECTION",
        "HAIU_STORAGE",
    }
)
RUN_ENV_REQUIRED_KEYS = frozenset(
    {
        "DMW_EXPERIMENTS_STORAGE",
        "DMW_EXPERIMENTS_PUBLICATION_PYTHON",
        "DMW_EXPERIMENTS_WATCHDOG_STALL_SECONDS",
        "FAISS_INDEX_PATH",
        "LMSTUDIO_MODEL_ID",
        "MONGO_DB",
        "USERS_COLLECTION",
        "THREAD_COLLECTION",
        "BRANCH_REGISTRY_COLLECTION",
        "WORKFLOW_EVENTS_COLLECTION",
        "WORKFLOW_PROGRESS_COLLECTION",
        "WORKFLOW_EVENTS_TTL_SECONDS",
        "WORKFLOW_PROGRESS_TTL_SECONDS",
        "ACCESS_TTL_SECONDS",
        "REFRESH_TTL_SECONDS",
        "COOKIE_SECURE",
        "COOKIE_SAMESITE",
        "JWT_ISSUER",
        "GITHUB_ONTOLOGY_REPO_NAME",
        "SEND_EMAILS",
        "ALLOWED_ORIGINS",
        "UVICORN_WORKERS",
        "BACKGROUND_WORKER_PROCESSES",
        "KISSKI_BASE_URL",
        "KISSKI_TIMEOUT_SECONDS",
        "KISSKI_MAX_RETRIES",
        "KISSKI_MAX_TOKENS",
        "ONTOLOGY_WORKER_TIMEOUT_SECONDS",
        "NER_WORKER_TIMEOUT_SECONDS",
        "OPA_REQUIRE_ONTOLOGY_REF",
        "OPA_REQUIRE_SUCCESSFUL_RAG_RETRIEVAL",
        "OPA_SAFE_CONTEXT_RATIO",
        "OPA_FULL_ONTOLOGY_MAX_TOKENS",
        "OPA_THREAD_WRITE_MAX_RETRIES",
        "OPA_THREAD_WRITE_RETRY_DELAY_SECONDS",
        "HAIU_OPENAI_BASE_URL",
        "HAIU_EMBEDDING_BASE_URL",
        "HAIU_MODEL_LLM",
        "HAIU_MODEL_FAST",
        "HAIU_MODEL_FAST_REASON",
        "HAIU_MODEL_EMBED",
        "HAIU_MAX_RETRIES",
        "HAIU_MAX_RETRIES_OPENAI",
        "HAIU_TIMEOUT_LLM",
        "HAIU_TIMEOUT_EMBEDDING",
        "HAIU_RPM",
        "HAIU_MAXCONCURRENCY",
        "HAIURAG_MODEL_LLM",
        "HAIURAG_MODEL_EMBED",
        "HAIURAG_ENABLE_EMBEDDING_CACHE",
        "HAIURAG_IGNORE_EMBEDDING_CACHE_READS",
        "HAIURAG_ENABLE_TURTLE_UPWARD_SCHEMA_CLOSURE",
        "LIGHTRAG_TOP_K",
        "LIGHTRAG_CHUNK_TOP_K",
        "LIGHTRAG_MAX_ENTITY_TOKENS",
        "LIGHTRAG_MAX_RELATION_TOKENS",
        "LIGHTRAG_MAX_TOTAL_TOKENS",
        *RUN_ENV_SECRET_KEYS,
        *RUN_ENV_DERIVED_KEYS,
    }
)
EXECUTION_ENV_ALLOWED_KEYS = {
    "academiccloud": frozenset(
        {
            "KISSKI_BASE_URL",
            "HAIU_OPENAI_BASE_URL",
            "HAIU_EMBEDDING_BASE_URL",
            "HAIU_MODEL_LLM",
            "HAIU_MODEL_FAST",
            "HAIURAG_MODEL_LLM",
        }
    ),
    "lmstudio": frozenset(
        {
            "KISSKI_API_KEY",
            "KISSKI_BASE_URL",
            "HAIU_OPENAI_API_KEY",
            "HAIU_OPENAI_BASE_URL",
            "HAIU_MODEL_LLM",
            "HAIU_MODEL_FAST",
            "HAIURAG_MODEL_LLM",
            "LMSTUDIO_MODEL_ID",
        }
    ),
}
_DECLARATION = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=")
_LOCAL_DUMMY_SECRET = "lm-studio-local"


@dataclass(frozen=True, slots=True)
class ResolvedRunEnvironment:
    """Expose validated config and portable provenance for one execution.

    :param run_root: Selected AppRC storage root.
    :param execution: Provider execution whose override layer was loaded.
    :param config: Typed AppRC settings after all layers were merged.
    :param env_files: Ordered explicit dotenv files used for bootstrap.
    """

    run_root: Path
    execution: RunExecution
    config: StudyRuntimeConfig
    env_files: tuple[Path, Path]

    def provenance_payload(self) -> dict[str, dict[str, Any]]:
        """Return redacted, run-portable provenance for registered settings.

        :return: Environment keys mapped to safe values and source layers.
        """
        payload: dict[str, dict[str, Any]] = {}
        for section_name in (
            "app",
            "dmw_login",
            "mongo",
            "jwt",
            "github",
            "provider",
            "ontology_worker",
            "ner",
            "haiu",
        ):
            section = getattr(self.config, section_name)
            for source in section.provenance().values():
                if source.env_key is None:
                    continue
                value = source.display_value
                if isinstance(value, Path):
                    value = _portable_path(value, run_root=self.run_root)
                payload[source.env_key] = {
                    "configured": bool(str(source.value)),
                    "origin": source.origin,
                    "secret": source.secret,
                    "value": value,
                }
        for key, value in _derived_environment(
            run_root=self.run_root,
            execution=self.execution,
        ).items():
            payload[key] = {
                "configured": True,
                "origin": "run_toml",
                "secret": False,
                "value": _portable_path(Path(value), run_root=self.run_root)
                if key == "HAIU_STORAGE"
                else value,
            }
        return dict(sorted(payload.items()))


def validate_run_environment_contract(
    run_root: Path,
    execution: RunExecution,
) -> tuple[Path, Path]:
    """Validate exhaustive shared and minimal provider dotenv contracts.

    :param run_root: Copied run directory.
    :param execution: Declared provider execution.
    :return: Ordered shared and provider override paths.
    :raises ValueError: If keys, secrets, or execution overrides are invalid.
    """
    shared = run_root / "run.env"
    provider = run_root / execution.env_file
    declared = _declared_keys(shared)
    missing = sorted(RUN_ENV_REQUIRED_KEYS - declared)
    unknown = sorted(declared - RUN_ENV_REQUIRED_KEYS)
    if missing or unknown:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        raise ValueError(
            "run.env key inventory differs from the contract; "
            + "; ".join(details)
        )
    shared_values = _dotenv_values(shared)
    exposed = sorted(RUN_ENV_SECRET_KEYS & set(shared_values))
    if exposed:
        raise ValueError(
            "run.env must not assign secret keys: " + ", ".join(exposed)
        )
    provider_values = _dotenv_values(provider)
    allowed = EXECUTION_ENV_ALLOWED_KEYS[execution.name]
    unknown_provider = sorted(set(provider_values) - allowed)
    if unknown_provider:
        raise ValueError(
            f"{execution.env_file} contains unsupported overrides: "
            + ", ".join(unknown_provider)
        )
    active_provider_secrets = RUN_ENV_SECRET_KEYS & set(provider_values)
    if execution.name != "lmstudio" and active_provider_secrets:
        raise ValueError(
            f"{execution.env_file} must not assign real credential fields."
        )
    for key in active_provider_secrets:
        if provider_values[key] != _LOCAL_DUMMY_SECRET:
            raise ValueError(
                f"{execution.env_file} may use only the documented local "
                f"dummy value for {key}."
            )
    return shared, provider


def bootstrap_run_environment(
    run_root: Path,
    execution: RunExecution,
    *,
    require_app_wide_secrets: bool = True,
) -> ResolvedRunEnvironment:
    """Bootstrap AppRC and Haiu from one authoritative run environment.

    This function must run before importing DMW, OPA, GTA, NER, MongoDBAPI, or
    Haiu runtime clients because several published modules read environment
    variables during import.

    :param run_root: Copied run directory selected as AppRC storage.
    :param execution: Provider execution to resolve.
    :param require_app_wide_secrets: Enforce app-wide origin for real secrets.
    :return: Typed effective settings and safe provenance access.
    """
    resolved_root = run_root.expanduser().resolve()
    env_files = validate_run_environment_contract(resolved_root, execution)
    APP_RC.bootstrap(
        env_files=env_files,
        env_file_overrides_os_environ=True,
        load_dotenv_layers=True,
        storage=str(resolved_root),
    )
    os.environ.update(
        _derived_environment(run_root=resolved_root, execution=execution)
    )
    config = StudyRuntimeConfig()
    _validate_runtime_assets(config)
    if require_app_wide_secrets:
        _validate_secret_origins(config, execution=execution)
    return ResolvedRunEnvironment(
        run_root=resolved_root,
        execution=execution,
        config=config,
        env_files=env_files,
    )


def load_runtime_environment(environment_files: tuple[Path, ...]) -> None:
    """Load ordered dotenv files for low-level compatibility entry points.

    New lifecycle code uses :func:`bootstrap_run_environment`. This narrow
    adapter remains for direct module tests and subprocess entry points.

    :param environment_files: Existing dotenv files in precedence order.
    :return: ``None`` after later files replace earlier values.
    """
    for environment_file in environment_files:
        if not environment_file.is_file():
            raise SystemExit(
                f"Runtime environment file does not exist: {environment_file}"
            )
        load_dotenv(environment_file, override=True)


def _derived_environment(
    *,
    run_root: Path,
    execution: RunExecution,
) -> dict[str, str]:
    """Build settings whose only authority is ``run.toml`` or run identity."""
    return {
        "RG_RAW_COLLECTION": execution.raw_collection,
        "ANNOTATION_COLLECTION": execution.annotation_collection,
        "ONTOLOGIES_COLLECTION": execution.ontology_collection,
        "HAIU_STORAGE": str(
            (run_root / "environment" / f"haiu-{execution.name}").resolve()
        ),
    }


def _validate_runtime_assets(config: StudyRuntimeConfig) -> None:
    index_file = config.ner.index_path.expanduser()
    if not index_file.is_absolute():
        raise ValueError(
            "FAISS_INDEX_PATH must be an absolute machine-local path."
        )
    if not index_file.is_file():
        raise ValueError("FAISS_INDEX_PATH does not identify an existing file.")


def _validate_secret_origins(
    config: StudyRuntimeConfig,
    *,
    execution: RunExecution,
) -> None:
    required = (
        (config.dmw_login, "login"),
        (config.dmw_login, "password"),
        (config.mongo, "uri"),
        (config.jwt, "secret"),
        (config.github, "token"),
    )
    if execution.name == "academiccloud":
        required += (
            (config.provider, "api_key"),
            (config.haiu, "api_key"),
        )
    required += ((config.haiu, "embedding_api_key"),)
    app_wide_values = _dotenv_values(APP_RC.spec.app_wide_env_path())
    invalid = []
    for section, field_name in required:
        provenance = section.provenance_of(field_name)
        env_key = provenance.env_key or field_name
        app_wide_value = app_wide_values.get(env_key)
        effective_value = str(getattr(section, field_name))
        if not app_wide_value or effective_value != app_wide_value:
            invalid.append(env_key)
    if invalid:
        raise ValueError(
            "Real credentials must come from AppRC app-wide configuration: "
            + ", ".join(sorted(invalid))
        )


def _declared_keys(path: Path) -> frozenset[str]:
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _DECLARATION.match(line)
        if match:
            keys.add(match.group(1))
    return frozenset(keys)


def _dotenv_values(path: Path) -> dict[str, str]:
    values = dotenv_values(path)
    return {
        key: value for key, value in values.items() if isinstance(value, str)
    }


def _portable_path(path: Path, *, run_root: Path) -> str:
    expanded = path.expanduser()
    try:
        return expanded.resolve().relative_to(run_root).as_posix()
    except ValueError:
        return "<machine-local-path>"


__all__ = [
    "EXECUTION_ENV_ALLOWED_KEYS",
    "RUN_ENV_DERIVED_KEYS",
    "RUN_ENV_REQUIRED_KEYS",
    "RUN_ENV_SECRET_KEYS",
    "ResolvedRunEnvironment",
    "RunExecution",
    "bootstrap_run_environment",
    "load_runtime_environment",
    "validate_run_environment_contract",
]
