from types import SimpleNamespace
from typing import cast

import pytest

from haiu import HaiuRC

from dmw_experiments.studies.haiu_comparison.model.providers import (
    provider_profile,
)
from dmw_experiments.studies.haiu_comparison.data_collection.runner import (
    _configure_provider_profile,
)


def test_provider_profiles_keep_logical_model_and_embedding_constant() -> None:
    academiccloud = provider_profile("academiccloud-qwen36")
    lmstudio = provider_profile("lmstudio-qwen36-q6")

    assert academiccloud.logical_generation_model == "qwen3.6-27b"
    assert lmstudio.logical_generation_model == "qwen3.6-27b"
    assert academiccloud.quantization == "FP8"
    assert academiccloud.weight_artifact == "Qwen/Qwen3.6-27B-FP8"
    assert lmstudio.provider_generation_model == "qwen/qwen3.6-27b"
    assert lmstudio.quantization == "Q6"
    assert academiccloud.embedding_provider == lmstudio.embedding_provider
    assert (
        lmstudio.weight_artifact
        == "record exact local Q6 model-file SHA-256 in environment_lock"
    )


def test_profile_configuration_keeps_academiccloud_embedding_model() -> None:
    rc = cast(
        HaiuRC,
        SimpleNamespace(
            client=SimpleNamespace(model_llm="old", model_embed="other"),
            rag=SimpleNamespace(
                haiu_settings=SimpleNamespace(model_embed="qwen3-embedding-4b")
            ),
        ),
    )

    _configure_provider_profile(
        rc=rc,
        profile=provider_profile("lmstudio-qwen36-q6"),
    )

    assert rc.client.model_llm == "qwen/qwen3.6-27b"
    assert rc.client.model_embed == "qwen3-embedding-4b"
    assert rc.rag.haiu_settings.model_llm == "qwen/qwen3.6-27b"


def test_profile_configuration_rejects_changed_embedding_model() -> None:
    rc = cast(
        HaiuRC,
        SimpleNamespace(
            client=SimpleNamespace(model_llm="old", model_embed="other"),
            rag=SimpleNamespace(
                haiu_settings=SimpleNamespace(model_embed="other-embed")
            ),
        ),
    )

    with pytest.raises(SystemExit, match="qwen3-embedding-4b"):
        _configure_provider_profile(
            rc=rc,
            profile=provider_profile("academiccloud-qwen36"),
        )
