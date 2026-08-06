from __future__ import annotations

import os
import sys
from types import ModuleType

import pytest

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.run_lmstudio_backend import (
    _apply_provider_split,
    _load_dmw_app,
    _parser,
)


def test_parser_requires_explicit_local_endpoint() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args([])


def test_parser_defaults_to_dmw_catalogued_model_name() -> None:
    args = _parser().parse_args(
        ["--lmstudio-base-url", "http://local.example/v1"]
    )

    assert args.model == "qwen/qwen3.6-27b"
    assert args.max_tokens == 60_000


def test_provider_split_keeps_remote_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAIU_OPENAI_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("HAIU_OPENAI_API_KEY", "embedding-key")

    _apply_provider_split(
        lmstudio_base_url="http://local.example/v1",
        model="qwen/qwen3.6-27b",
        max_tokens=20_000,
        provider_timeout_seconds=3_600,
        worker_timeout_seconds=7_200,
    )

    assert os.environ["HAIU_OPENAI_BASE_URL"] == "http://local.example/v1"
    assert (
        os.environ["HAIU_EMBEDDING_BASE_URL"] == "https://embedding.example/v1"
    )
    assert os.environ["HAIU_OPENAI_API_KEY"] == "lm-studio-local"
    assert os.environ["HAIU_EMBEDDING_API_KEY"] == "embedding-key"
    assert os.environ["HAIURAG_MODEL_LLM"] == "qwen/qwen3.6-27b"


def test_dmw_app_loads_from_installed_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_app = object()
    redaction_calls: list[str] = []
    package = ModuleType("datamodel_workflow")
    package.__path__ = []
    app_module = ModuleType("datamodel_workflow.app")
    app_module.__dict__["app"] = expected_app
    runtime_module = ModuleType("datamodel_workflow.runtime_bootstrap")
    runtime_module.__dict__["install_global_log_redaction"] = lambda: (
        redaction_calls.append("installed")
    )
    monkeypatch.setitem(sys.modules, "datamodel_workflow", package)
    monkeypatch.setitem(sys.modules, "datamodel_workflow.app", app_module)
    monkeypatch.setitem(
        sys.modules,
        "datamodel_workflow.runtime_bootstrap",
        runtime_module,
    )

    assert _load_dmw_app() is expected_app
    assert redaction_calls == ["installed"]
