"""Tests for ignored runtime-environment validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from dmw_experiments.config.runtime_environment import (
    ACADEMICCLOUD_REQUIRED_KEYS,
    validate_academiccloud_environment,
)


def _environment_file(tmp_path: Path, *, index_value: str) -> Path:
    """Write a non-secret complete AcademicCloud test environment.

    :param tmp_path: Isolated pytest directory.
    :param index_value: FAISS path representation under test.
    :return: Created dotenv file.
    """
    environment = tmp_path / "academiccloud.env"
    values = {key: "test-value" for key in ACADEMICCLOUD_REQUIRED_KEYS}
    values["FAISS_INDEX_PATH"] = index_value
    environment.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return environment


def test_absolute_existing_ner_index_is_accepted(tmp_path: Path) -> None:
    """An explicit runtime asset is independent from the service cwd."""
    index_file = tmp_path / "ner.index"
    index_file.write_bytes(b"index")
    environment = _environment_file(
        tmp_path,
        index_value=str(index_file),
    )

    assert validate_academiccloud_environment(environment) == index_file


def test_relative_ner_index_is_rejected_before_launch(tmp_path: Path) -> None:
    """A DMW-repository-relative legacy value cannot reach service launch."""
    environment = _environment_file(
        tmp_path,
        index_value="external_data/ner.index",
    )

    with pytest.raises(ValueError, match="absolute path"):
        validate_academiccloud_environment(environment)
