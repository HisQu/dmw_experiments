"""Tests for the isolated AcademicCloud DMW backend entrypoint."""

from __future__ import annotations

import os
import sys
from types import ModuleType

import pytest

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.run_academiccloud_backend import (
    _install_raw_collection_override,
    _parser,
)


def test_parser_requires_an_explicit_raw_collection() -> None:
    """An AcademicCloud backend cannot silently use DMW's default raw store."""
    with pytest.raises(SystemExit):
        _parser().parse_args([])


def test_raw_collection_override_survives_dmw_dotenv_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The experiment scope wins after DMW reloads a conflicting dotenv file."""
    package = ModuleType("datamodel_workflow")
    package.__path__ = []
    env_module = ModuleType("datamodel_workflow.env")

    def conflicting_dotenv_loader(*_args: object, **_kwargs: object) -> bool:
        os.environ["RG_RAW_COLLECTION"] = "RG_raw"
        os.environ["KISSKI_MAX_TOKENS"] = "20000"
        return True

    env_module.__dict__["load_dotenv"] = conflicting_dotenv_loader
    monkeypatch.setitem(sys.modules, "datamodel_workflow", package)
    monkeypatch.setitem(sys.modules, "datamodel_workflow.env", env_module)
    monkeypatch.delenv("RG_RAW_COLLECTION", raising=False)
    monkeypatch.delenv("KISSKI_MAX_TOKENS", raising=False)

    _install_raw_collection_override(
        raw_collection="RG_raw_header_sublemma_academiccloud_20260806",
        max_tokens=60_000,
    )

    assert env_module.load_dotenv() is True
    assert os.environ["RG_RAW_COLLECTION"] == (
        "RG_raw_header_sublemma_academiccloud_20260806"
    )
    assert os.environ["KISSKI_MAX_TOKENS"] == "60000"
