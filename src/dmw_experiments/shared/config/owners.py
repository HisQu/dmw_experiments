"""Typed AppRC ownership for the measured DMW runtime."""

from __future__ import annotations

from pathlib import Path

import apprc as rc

from dmw_experiments.shared.config.app import APP_RC

UNSET_PATH = Path(".not-configured")


@APP_RC.config("app", prefix="DMW_EXPERIMENTS_", title="Experiment")
class AppRuntimeConfig(rc.Config):
    """Settings owned by the experiment harness itself."""

    storage_root: Path = rc.field(
        "DMW_EXPERIMENTS_STORAGE",
        default=Path("."),
        editable=False,
        title="Run storage root",
        explanation_short="Selected copied run directory.",
    )
    publication_python: Path = rc.field(
        "DMW_EXPERIMENTS_PUBLICATION_PYTHON",
        default=UNSET_PATH,
        title="Published-stack Python",
        explanation_short=(
            "Optional interpreter override; the active interpreter is used "
            "when omitted."
        ),
    )
    watchdog_stall_seconds: int = rc.field(
        "DMW_EXPERIMENTS_WATCHDOG_STALL_SECONDS",
        default=14_400,
        title="Watchdog stall limit",
        explanation_short="Seconds without a durable checkpoint.",
    )


@APP_RC.config("dmw_login", prefix="DATAMODEL_", title="DMW login")
class DatamodelLoginConfig(rc.Config):
    """Credentials used only to authenticate the experiment runner to DMW."""

    login: str = rc.field(
        "DATAMODEL_LOGIN",
        required=True,
        secret=True,
        title="DMW login",
    )
    password: str = rc.field(
        "DATAMODEL_PASSWORD",
        required=True,
        secret=True,
        title="DMW password",
    )


@APP_RC.config("mongo", prefix="MONGO_", title="MongoDB")
class MongoRuntimeConfig(rc.Config):
    """MongoDB connection and database settings used by DMW dependencies."""

    uri: str = rc.field(
        "MONGO_URI",
        required=True,
        secret=True,
        title="MongoDB URI",
    )
    database: str = rc.field(
        "MONGO_DB",
        default="UserData",
        title="MongoDB database",
    )


@APP_RC.config("jwt", prefix="JWT_", title="DMW JWT")
class JwtRuntimeConfig(rc.Config):
    """Backend signing settings required by the local DMW API."""

    secret: str = rc.field(
        "JWT_SECRET",
        required=True,
        secret=True,
        title="JWT signing secret",
    )
    issuer: str = rc.field(
        "JWT_ISSUER",
        default="dmw-experiments",
        title="JWT issuer",
    )


@APP_RC.config("provider", prefix="KISSKI_", title="Generation provider")
class ProviderRuntimeConfig(rc.Config):
    """OpenAI-compatible GTA provider settings used by OPA."""

    api_key: str = rc.field(
        "KISSKI_API_KEY",
        required=True,
        secret=True,
        title="Generation API key",
    )
    base_url: str = rc.field(
        "KISSKI_BASE_URL",
        required=True,
        title="Generation endpoint",
    )
    timeout_seconds: int = rc.field(
        "KISSKI_TIMEOUT_SECONDS",
        default=3_600,
        title="Provider timeout",
    )
    max_retries: int = rc.field(
        "KISSKI_MAX_RETRIES",
        default=3,
        title="Provider retry limit",
    )
    max_tokens: int = rc.field(
        "KISSKI_MAX_TOKENS",
        default=60_000,
        title="Provider output cap",
    )


@APP_RC.config("ner", prefix="FAISS_", title="NER resources")
class NerRuntimeConfig(rc.Config):
    """Machine-local NER asset required by the DMW annotation stage."""

    index_path: Path = rc.field(
        "FAISS_INDEX_PATH",
        required=True,
        title="NER example index",
        explanation_short="Absolute machine-local FAISS index file.",
    )


@APP_RC.config("haiu", prefix="HAIU_", title="Haiu")
class HaiuStudyRuntimeConfig(rc.Config):
    """Haiu settings that directly affect the measured study paths."""

    storage: Path = rc.field(
        "HAIU_STORAGE",
        default=Path("environment/haiu"),
        title="Haiu storage",
    )
    api_key: str = rc.field(
        "HAIU_OPENAI_API_KEY",
        required=True,
        secret=True,
        title="Haiu chat API key",
    )
    base_url: str = rc.field(
        "HAIU_OPENAI_BASE_URL",
        required=True,
        title="Haiu chat endpoint",
    )
    embedding_api_key: str = rc.field(
        "HAIU_EMBEDDING_API_KEY",
        default="",
        secret=True,
        title="Haiu embedding API key",
    )
    embedding_base_url: str = rc.field(
        "HAIU_EMBEDDING_BASE_URL",
        default="",
        title="Haiu embedding endpoint",
    )
    model_llm: str = rc.field(
        "HAIU_MODEL_LLM",
        required=True,
        title="Haiu generation model",
    )
    model_fast: str = rc.field(
        "HAIU_MODEL_FAST",
        required=True,
        title="Haiu fast model",
    )
    model_embed: str = rc.field(
        "HAIU_MODEL_EMBED",
        required=True,
        title="Haiu embedding model",
    )
    max_retries: int = rc.field(
        "HAIU_MAX_RETRIES",
        default=3,
        title="Haiu retry limit",
    )
    timeout_llm: int = rc.field(
        "HAIU_TIMEOUT_LLM",
        default=3_600,
        title="Haiu generation timeout",
    )
    timeout_embedding: int = rc.field(
        "HAIU_TIMEOUT_EMBEDDING",
        default=180,
        title="Haiu embedding timeout",
    )
    rpm: int = rc.field(
        "HAIU_RPM",
        default=30,
        title="Haiu requests per minute",
    )
    max_concurrency: int = rc.field(
        "HAIU_MAXCONCURRENCY",
        default=2,
        title="Haiu concurrency",
    )


@APP_RC.bundle
class StudyRuntimeConfig:
    """Resolve the AppRC-owned settings needed by one provider execution."""

    app: AppRuntimeConfig
    dmw_login: DatamodelLoginConfig
    mongo: MongoRuntimeConfig
    jwt: JwtRuntimeConfig
    provider: ProviderRuntimeConfig
    ner: NerRuntimeConfig
    haiu: HaiuStudyRuntimeConfig
