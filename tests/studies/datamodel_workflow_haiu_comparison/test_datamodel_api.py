from typing import Any, cast

import httpx
import pytest

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.datamodel_api import (
    DatamodelClient,
    WorkflowRequestConfig,
    build_workflow_payload,
    regest_text_from_payload,
)


def test_regest_text_from_payload_uses_ordered_subentries() -> None:
    payload = {
        "success": True,
        "data": {
            "header": {"text": "Header", "entities": [{"type": "X"}]},
            "subentries": {
                "2": {"text": "Second", "entities": [{"type": "Y"}]},
                "1": {"text": "First", "entities": []},
            },
        },
    }

    regest = regest_text_from_payload("11010116-1", payload)

    assert regest.header == "Header"
    assert regest.subentries == ("First", "Second")
    assert regest.prompt_payload()["11010116-1"]["header"]["entities"] == []


def test_regest_text_from_payload_rejects_legacy_formatting_tokens() -> None:
    payload = {
        "success": True,
        "data": {
            "header": {"text": "Glusingk &w&w &y Capel."},
            "subentries": {},
        },
    }

    with pytest.raises(ValueError, match="legacy formatting token"):
        regest_text_from_payload("11002962", payload)


def test_build_workflow_payload_matches_current_dmw_contract() -> None:
    payload = build_workflow_payload(
        regest_id="11010116",
        config=WorkflowRequestConfig(
            branch="experiment",
            annotation_model="ner-model",
            annotation_guideline_version="1.5.8",
            annotation_min_version=None,
            annotation_top_n=5,
            annotation_example_limit=10,
            ontology_record_version="exp-v1",
            ontology_context_version="1.5.8",
            ontology_user_input="Model the regest.",
            ontology_min_example_version="1.0.0",
            ontology_model_name="ontology-model",
            ontology_context_mode="rag",
            ontology_example_limit=1,
            max_output_tokens=20_000,
            output_safety_margin_tokens=4_096,
            require_exact_prompt_tokens=True,
            require_finish_reason=True,
            include_annotations=True,
            use_only_existing_ontology_terms=False,
            allow_text_interpretation=False,
            existing_data_policy="recreate",
            require_existing_annotation=True,
            frozen_annotation_sha256="abc",
        ),
    )

    assert payload["branch"] == "experiment"
    assert payload["ontology"]["allow_text_interpretation"] is False
    assert payload["ontology"]["context_mode"] == "rag"
    assert payload["ontology"]["ontology_example_limit"] == 1
    assert payload["ontology"]["max_output_tokens"] == 20_000
    assert payload["ontology"]["output_safety_margin_tokens"] == 4_096
    assert payload["ontology"]["require_exact_prompt_tokens"] is True
    assert payload["require_existing_annotation"] is True


def test_completed_annotation_check_rejects_placeholder_and_missing_data() -> (
    None
):
    def handle_request(request: httpx.Request) -> httpx.Response:
        version = request.url.path.rsplit("/", maxsplit=1)[-1]
        assert request.url.params["regest_type"] == "annotated"
        assert request.url.params["branch"] == "experiment"
        if version == "missing":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "type": "raw",
                    "data": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "type": "annotated",
                "data": {
                    "generation_placeholder": version == "pending",
                    "annotation_guideline_delta": {"version": version},
                },
            },
        )

    client = DatamodelClient(
        base_url="http://dmw.test",
        login="user",
        password="password",
        timeout_seconds=1,
    )
    internal_client = cast(Any, client)._client
    internal_client.close()
    cast(Any, client)._client = httpx.Client(
        transport=httpx.MockTransport(handle_request)
    )
    cast(Any, client)._access_token = "token"
    try:
        assert client.has_completed_annotation(
            regest_id="1",
            version="accepted",
            branch="experiment",
        )
        assert not client.has_completed_annotation(
            regest_id="1",
            version="pending",
            branch="experiment",
        )
        assert not client.has_completed_annotation(
            regest_id="1",
            version="missing",
            branch="experiment",
        )
    finally:
        client.close()
