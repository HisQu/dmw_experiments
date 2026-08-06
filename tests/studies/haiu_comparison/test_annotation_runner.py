from __future__ import annotations

from typing import Any, cast

import pytest

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.annotations import (
    AnnotationPreparationConfig,
    FrozenAnnotationError,
    annotation_content_sha256,
    prepare_frozen_annotation,
)
from dmw_experiments.studies.haiu_comparison.data_collection.dmw.client import (
    DatamodelClient,
    WorkflowRequestConfig,
)


class _ExistingAnnotationClient:
    def __init__(self) -> None:
        self.accept_count = 0
        self.review_data: dict[str, Any] = {
            "regest_id": "1",
            "version": "0.0.1",
            "header_entities": [{"type": "Person", "value": "Ada"}],
            "subentry_entities": [],
            "generation_dependency": {
                "ner_commit": "a" * 40,
                "gta_commit": "b" * 40,
            },
            "generation_placeholder": False,
            "created_at": "2026-07-24T00:00:00+00:00",
        }

    def get_annotation_review(self, **_kwargs: Any):
        return 200, {"success": True, "data": self.review_data}

    def accept_annotation(self, **_kwargs: Any):
        self.accept_count += 1
        return 200, {"success": True}


def test_preexisting_annotation_is_accepted_and_frozen() -> None:
    client = _ExistingAnnotationClient()

    frozen = prepare_frozen_annotation(
        client=cast(DatamodelClient, client),
        regest_id="1",
        workflow_config=_workflow_config(),
        preparation_config=_preparation_config(),
    )

    assert client.accept_count == 1
    assert frozen.source == "preexisting_reviewed_and_accepted"
    assert frozen.content_sha256 == annotation_content_sha256(
        header_entities=client.review_data["header_entities"],
        subentry_entities=[],
    )
    assert frozen.preparation["attempt_history"][0]["success"] is True
    assert frozen.generation_dependency == {
        "ner_commit": "a" * 40,
        "gta_commit": "b" * 40,
    }


def test_resumed_snapshot_backfills_generation_dependency() -> None:
    client = _ExistingAnnotationClient()
    frozen = prepare_frozen_annotation(
        client=cast(DatamodelClient, client),
        regest_id="1",
        workflow_config=_workflow_config(),
        preparation_config=_preparation_config(),
    )
    snapshot = frozen.as_dict()
    snapshot["generation_dependency"] = None

    restored = prepare_frozen_annotation(
        client=cast(DatamodelClient, client),
        regest_id="1",
        workflow_config=_workflow_config(),
        preparation_config=_preparation_config(),
        existing_snapshot=snapshot,
    )

    assert restored.generation_dependency == {
        "ner_commit": "a" * 40,
        "gta_commit": "b" * 40,
    }


def test_resumed_snapshot_is_rejected_after_remote_content_changes() -> None:
    client = _ExistingAnnotationClient()
    frozen = prepare_frozen_annotation(
        client=cast(DatamodelClient, client),
        regest_id="1",
        workflow_config=_workflow_config(),
        preparation_config=_preparation_config(),
    )
    client.review_data["header_entities"] = [
        {"type": "Person", "value": "Grace"}
    ]

    with pytest.raises(FrozenAnnotationError, match="changed"):
        prepare_frozen_annotation(
            client=cast(DatamodelClient, client),
            regest_id="1",
            workflow_config=_workflow_config(),
            preparation_config=_preparation_config(),
            existing_snapshot=frozen.as_dict(),
        )


def test_resumed_snapshot_is_rejected_after_dependency_changes() -> None:
    client = _ExistingAnnotationClient()
    frozen = prepare_frozen_annotation(
        client=cast(DatamodelClient, client),
        regest_id="1",
        workflow_config=_workflow_config(),
        preparation_config=_preparation_config(),
    )
    client.review_data["generation_dependency"] = {
        "ner_commit": "c" * 40,
        "gta_commit": "b" * 40,
    }

    with pytest.raises(FrozenAnnotationError, match="dependency changed"):
        prepare_frozen_annotation(
            client=cast(DatamodelClient, client),
            regest_id="1",
            workflow_config=_workflow_config(),
            preparation_config=_preparation_config(),
            existing_snapshot=frozen.as_dict(),
        )


def _workflow_config() -> WorkflowRequestConfig:
    return WorkflowRequestConfig(
        branch="experiment",
        annotation_model="qwen3.6-27b",
        annotation_guideline_version="0.0.1",
        annotation_min_version=None,
        annotation_top_n=5,
        annotation_example_limit=10,
        ontology_record_version="unused",
        ontology_context_version="0.0.1",
        ontology_user_input="Model the regest.",
        ontology_min_example_version="999.0.0",
        ontology_model_name="qwen3.5-397b-a17b",
        ontology_context_mode="rag",
        ontology_example_limit=1,
        max_output_tokens=20_000,
        output_safety_margin_tokens=4_096,
        require_exact_prompt_tokens=False,
        require_finish_reason=False,
        include_annotations=True,
        use_only_existing_ontology_terms=False,
        allow_text_interpretation=False,
        existing_data_policy="reuse",
        require_existing_annotation=True,
    )


def _preparation_config() -> AnnotationPreparationConfig:
    return AnnotationPreparationConfig(
        max_attempts=1,
        retry_delay_seconds=0,
        poll_interval_seconds=0.05,
        timeout_seconds=1,
    )
