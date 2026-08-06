"""Load and validate ignored runtime configuration files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ACADEMICCLOUD_REQUIRED_KEYS = (
    "DATAMODEL_LOGIN",
    "DATAMODEL_PASSWORD",
    "FAISS_INDEX_PATH",
    "HAIU_OPENAI_API_KEY",
    "HAIU_OPENAI_BASE_URL",
    "HAIU_STORAGE",
    "JWT_SECRET",
    "KISSKI_API_KEY",
    "MONGO_URI",
)


def load_runtime_environment(environment_files: Sequence[Path]) -> None:
    """Load explicit ignored dotenv files in precedence order.

    :param environment_files: Files whose later values replace earlier values.
    :return: ``None`` after populating the current process environment.
    :raises SystemExit: If a requested file does not exist.
    """
    for environment_file in environment_files:
        if not environment_file.is_file():
            raise SystemExit(
                f"Runtime environment file does not exist: {environment_file}"
            )
        load_dotenv(environment_file, override=True)


def validate_academiccloud_environment(environment_file: Path) -> Path:
    """Validate launch-critical values without exposing their contents.

    The NER example index is a local runtime asset rather than package data.
    Requiring an absolute existing file prevents its meaning from changing
    with a service working directory.

    :param environment_file: Ignored merged AcademicCloud dotenv file.
    :return: Absolute NER example-index path.
    :raises ValueError: If a required value or runtime asset is unavailable.
    """
    values = dotenv_values(environment_file)
    missing = [
        key for key in ACADEMICCLOUD_REQUIRED_KEYS if not values.get(key)
    ]
    if missing:
        raise ValueError(
            "AcademicCloud environment is missing required keys: "
            + ", ".join(missing)
        )
    index_file = Path(str(values["FAISS_INDEX_PATH"])).expanduser()
    if not index_file.is_absolute():
        raise ValueError(
            "FAISS_INDEX_PATH must be an absolute path so NER does not "
            "depend on a service working directory."
        )
    if not index_file.is_file():
        raise ValueError("FAISS_INDEX_PATH does not identify an existing file.")
    return index_file


__all__ = [
    "ACADEMICCLOUD_REQUIRED_KEYS",
    "load_runtime_environment",
    "validate_academiccloud_environment",
]
