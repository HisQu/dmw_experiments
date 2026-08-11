from dataclasses import replace

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.annotations import (
    annotation_content_sha256,
)
from dmw_experiments.studies.haiu_comparison.data_collection.dmw.client import (
    WorkflowRequestConfig,
)
from dmw_experiments.studies.haiu_comparison.data_collection.dmw.condition import (
    _normalize_workflow_payload,
)


def test_normalize_workflow_payload_counts_exposed_prompts() -> None:
    payload = {
        "success": True,
        "annotation_version": "1.5.8",
        "ontology_record_version": "v1",
        "ontology_context_version": "1.5.8",
        "existing_data_policy": "reuse",
        "debug_output": {
            "context_mode_requested": "rag",
            "context_mode_effective": "rag",
            "explanation": "Plan",
            "tbox": ":A a owl:Class .",
            "abox": ":i a :A .",
            "raw_ttl_output": ":A a owl:Class .\n:i a :A .",
            "timing_scopes": {
                "stage1_total": {
                    "duration_seconds": 5.5,
                    "timing_source": "opa_server_wall_clock",
                }
            },
            "prompts": {"system": "SYS", "user": "USER"},
            "stage_prompts": {
                "stage1": {"system": "SYS", "user": "USER"},
                "stage2": {"system": "SYS2", "user": "USER2"},
            },
            "ontology_ref": {
                "repository": "ontology",
                "ref": "refs/tags/ontology/main/v1.5.8",
            },
            "dependency": {"opa_commit": "abc123"},
            "provider_run_metadata": {
                "stage1": {
                    "completion_params": {"max_tokens": 18_975},
                    "context_window_adjustment": {
                        "requested_max_tokens": 20_000,
                        "effective_max_tokens": 18_975,
                    },
                }
            },
            "annotation_override_used": True,
            "examples_used": 0,
            "ontology_context": {
                "retrieved_turtle": ":Existing a owl:Class .",
                "retrieval_snapshot": {
                    "snapshot_fidelity": "native_full_graph",
                },
                "retrieval_metadata": {
                    "retrieval_status": {
                        "status": "ok",
                        "reason": "semantic_result",
                    }
                },
            },
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_rag",
        regest_id="11010116-1",
        status_code=200,
        success=True,
        started_at="2026-06-18T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=_workflow_config(),
    )

    assert row["success"] is True
    assert row["context_mode_effective"] == "rag"
    assert row["prompt_tokens"] >= 1
    assert row["prompt_tokens_complete"] is True
    assert row["prompt_tokens_source"] == "estimated"
    assert row["prompt_tokens"] > row["workflow_stage2_prompt_tokens"]
    assert row["output_tokens"] >= 1
    assert row["turtle_syntax_valid"] is True
    assert row["generation_dependency"] == {"opa_commit": "abc123"}
    assert (
        row["provider_run_metadata"]["stage1"]["context_window_adjustment"][
            "effective_max_tokens"
        ]
        == 18_975
    )
    assert row["annotation_override_used"] is True
    assert row["ontology_examples_used"] == 0
    assert row["rag_retrieval_status"] == {
        "status": "ok",
        "reason": "semantic_result",
    }
    assert row["rag_retrieval_valid"] is True
    assert row["raw_ttl_capture_complete"] is True
    assert row["raw_ttl_output"] == ":A a owl:Class .\n:i a :A ."
    assert row["raw_stage1_output"] == "Plan"
    assert row["raw_stage1_capture_complete"] is True
    assert row["raw_stage1_output_source"] == "workflow_explanation"
    assert row["stage_timings"]["stage1_total"]["duration_seconds"] == 5.5
    assert row["prompts"]["workflow_stage2"]["user"] == "USER2"


def test_normalize_workflow_failure_preserves_invalid_stage2_artifacts() -> (
    None
):
    payload = {
        "success": False,
        "detail": {
            "pipeline_error": "The AI produced invalid Turtle format.",
            "generation_diagnostics": {
                "designerResponse": "Observed Stage-1 plan",
                "rawTtlOutput": "```ttl\ninvalid\n```",
                "rawTtlOutputObserved": True,
                "timingScopes": {"opa_total": {"duration_seconds": 4.2}},
                "stagePrompts": {
                    "stage1": {"system": "sys1", "user": "user1"},
                    "stage2": {"system": "sys2", "user": "user2"},
                },
                "contextExampleProvenance": [
                    {
                        "regest_id": "10900102",
                        "sha256": "example-sha",
                    }
                ],
            },
            "generation_attempts": [
                {
                    "attempt": 1,
                    "success": False,
                    "diagnostics": {"rawTtlOutput": "```ttl\ninvalid\n```"},
                }
            ],
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="11010116-1",
        status_code=502,
        success=False,
        started_at="2026-06-18T00:00:00+00:00",
        request_duration_seconds=5.0,
        config=_workflow_config(),
    )

    assert row["success"] is False
    assert row["raw_ttl_output"] == "```ttl\ninvalid\n```"
    assert row["raw_ttl_capture_complete"] is True
    assert row["raw_stage1_output"] == "Observed Stage-1 plan"
    assert row["raw_stage1_capture_complete"] is True
    assert (
        row["raw_stage1_output_source"] == "workflow_failure_designer_response"
    )
    assert row["output_chars"] == len("```ttl\ninvalid\n```")
    assert row["output_tokens"] > 0
    assert row["stage_timings"]["opa_total"]["duration_seconds"] == 4.2
    assert row["prompts"]["workflow_stage2"]["user"] == "user2"
    assert row["generation_attempts"][0]["attempt"] == 1
    assert row["ontology_examples_used"] == 1
    assert row["context_example_provenance"] == [
        {
            "regest_id": "10900102",
            "sha256": "example-sha",
        }
    ]


def test_normalize_workflow_payload_rejects_recovered_rag_retrieval() -> None:
    payload = {
        "success": True,
        "debug_output": {
            "raw_ttl_output": ":A a owl:Class .",
            "ontology_context": {
                "retrieval_metadata": {
                    "retrieval_status": {
                        "status": "recovered_error",
                        "reason": "retrieval_error",
                    }
                }
            },
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_rag",
        regest_id="11010116-1",
        status_code=200,
        success=True,
        started_at="2026-06-18T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=_workflow_config(),
    )

    assert row["success"] is False
    assert row["rag_retrieval_valid"] is False
    assert "semantic retrieval" in row["error_message"]


def test_normalize_workflow_payload_rejects_missing_raw_stage2_capture() -> (
    None
):
    payload = {
        "success": True,
        "debug_output": {
            "tbox": ":A a owl:Class .",
            "abox": ":item a :A .",
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="11010116-1",
        status_code=200,
        success=True,
        started_at="2026-06-18T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=_workflow_config(),
    )

    assert row["success"] is False
    assert row["raw_ttl_capture_complete"] is False
    assert "exact unmodified Stage-2 Turtle" in row["error_message"]


def test_normalize_workflow_payload_rejects_reused_ontology_result() -> None:
    payload = {
        "success": True,
        "reused_existing_data": True,
        "debug_output": {
            "raw_ttl_output": ":A a owl:Class .",
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="11010116-1",
        status_code=200,
        success=True,
        started_at="2026-06-18T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=_workflow_config(),
    )

    assert row["success"] is False
    assert row["reused_existing_data"] is True
    assert "fresh ontology observation" in row["error_message"]


def test_normalize_workflow_payload_preserves_non_retryable_context_failure() -> (
    None
):
    pipeline_error = (
        "The number of tokens to keep from the initial prompt is greater than "
        "the context length."
    )
    payload = {
        "detail": {
            "message": "Ontology generation failed.",
            "pipeline_error": pipeline_error,
            "failure_code": "model_context_window_exceeded",
            "non_retryable": True,
            "ontology_stage_timing": {
                "duration_seconds": 3.0,
            },
        }
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="11010116-1",
        status_code=502,
        success=False,
        started_at="2026-07-24T00:00:00+00:00",
        request_duration_seconds=4.0,
        config=_workflow_config(),
    )

    assert row["success"] is False
    assert row["duration_seconds"] == 3.0
    assert row["pipeline_error"] == pipeline_error
    assert row["failure_code"] == "model_context_window_exceeded"
    assert row["non_retryable"] is True
    assert row["error_message"] == (
        f"Model context window exceeded: {pipeline_error}"
    )


def test_normalize_workflow_payload_guards_generic_context_capacity_failure() -> (
    None
):
    """Classify the legacy generic DMW context response without retrying it."""
    pipeline_error = (
        "Internal server error during ontology design: Prompt and safety "
        "margin exhaust the model context window."
    )
    payload = {
        "detail": {
            "message": "Ontology generation failed.",
            "pipeline_error": pipeline_error,
            "failure_code": "ontology_generation_failed",
            "non_retryable": False,
            "ontology_stage_timing": {
                "duration_seconds": 3.0,
            },
        }
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="11010116-1",
        status_code=502,
        success=False,
        started_at="2026-07-31T00:00:00+00:00",
        request_duration_seconds=4.0,
        config=_workflow_config(),
    )

    assert row["failure_code"] == "model_context_window_exceeded"
    assert row["non_retryable"] is True
    assert row["error_message"] == (
        f"Model context window exceeded: {pipeline_error}"
    )


def test_normalize_workflow_payload_uses_dmw_timing_and_frozen_annotation() -> (
    None
):
    header_entities = [{"type": "Person", "value": "Ada"}]
    annotation_sha256 = annotation_content_sha256(
        header_entities=header_entities,
        subentry_entities=[],
    )
    payload = {
        "success": True,
        "ontology_stage_timing": {
            "scope": "ontology_context_resolution_through_worker",
            "duration_seconds": 12.5,
        },
        "annotation_review": {
            "data": {
                "header_entities": header_entities,
                "subentry_entities": [],
            }
        },
        "debug_output": {
            "provider_run_metadata": {
                "stage1": {
                    "provider_message": {
                        "role": "assistant",
                        "content": "Plan",
                    },
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    },
                },
                "stage2": {
                    "provider_message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "Incomplete reasoning",
                    },
                    "usage": {
                        "prompt_tokens": 150,
                        "completion_tokens": 30,
                        "total_tokens": 180,
                    },
                },
            },
            "tbox": ":A a owl:Class .",
            "raw_ttl_output": ":A a owl:Class .",
        },
    }
    config = replace(
        _workflow_config(),
        require_existing_annotation=True,
        frozen_annotation_sha256=annotation_sha256,
    )

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="1",
        status_code=200,
        success=True,
        started_at="2026-07-24T00:00:00+00:00",
        request_duration_seconds=99.0,
        config=config,
    )

    assert row["success"] is True
    assert row["duration_seconds"] == 12.5
    assert row["request_duration_seconds"] == 99.0
    assert row["annotation_matches_frozen"] is True
    assert row["ontology_provider_usage_complete"] is True
    assert row["ontology_provider_total_tokens"] == 300
    assert row["prompt_tokens"] == 150
    assert row["prompt_tokens_source"] == "provider"
    assert row["raw_stage1_provider_message"] == {
        "role": "assistant",
        "content": "Plan",
    }
    assert row["raw_stage2_provider_message"] == {
        "role": "assistant",
        "content": None,
        "reasoning_content": "Incomplete reasoning",
    }
    assert "provider_message" not in row["provider_run_metadata"]["stage1"]
    assert "provider_message" not in row["provider_run_metadata"]["stage2"]


def test_constrained_natural_completion_remains_publication_eligible() -> None:
    provider_metadata = {
        stage: {
            "finish_reason": "stop",
            "output_truncated": False,
            "generation_budget": {
                "requested_max_output_tokens": 20_000,
                "predicted_max_output_tokens": effective,
                "effective_max_output_tokens": effective,
                "measured_prompt_tokens": 262_144 - 4_096 - effective,
                "prompt_token_source": "huggingface_chat_template",
                "provider_prompt_tokens": 250_000,
                "context_window_tokens": 262_144,
                "safety_margin_tokens": 4_096,
                "output_constrained": True,
                "finish_reason": "stop",
                "output_truncated": False,
                "adjustments": [],
            },
        }
        for stage, effective in (("stage1", 13_566), ("stage2", 8_000))
    }
    payload = {
        "success": True,
        "debug_output": {
            "raw_ttl_output": ":A a owl:Class .",
            "provider_run_metadata": provider_metadata,
        },
    }
    config = replace(_workflow_config(), require_finish_reason=True)

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="1",
        status_code=200,
        success=True,
        started_at="2026-07-28T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=config,
    )

    assert row["success"] is True
    assert row["output_constrained"] is True
    assert row["output_truncated"] is False
    assert row["publication_eligible"] is True
    assert (
        row["generation_budget"]["stage1"]["measured_prompt_tokens"] == 244_482
    )


def test_length_finish_reason_invalidates_workflow_observation() -> None:
    payload = {
        "success": True,
        "debug_output": {
            "raw_ttl_output": ":A a owl:Class .",
            "provider_run_metadata": {
                "stage1": {
                    "finish_reason": "stop",
                    "output_truncated": False,
                },
                "stage2": {
                    "finish_reason": "length",
                    "output_truncated": True,
                },
            },
        },
    }

    row = _normalize_workflow_payload(
        response_payload=payload,
        condition="workflow_full_ontology",
        regest_id="1",
        status_code=200,
        success=True,
        started_at="2026-07-28T00:00:00+00:00",
        request_duration_seconds=1.0,
        config=replace(_workflow_config(), require_finish_reason=True),
    )

    assert row["success"] is False
    assert row["output_truncated"] is True
    assert row["non_retryable"] is True
    assert row["publication_eligible"] is False
    assert "length limit" in row["error_message"]


def _workflow_config() -> WorkflowRequestConfig:
    return WorkflowRequestConfig(
        branch="main",
        annotation_model="model",
        annotation_guideline_version="1.5.8",
        annotation_min_version=None,
        annotation_top_n=5,
        annotation_example_limit=10,
        ontology_record_version="v1",
        ontology_context_version="1.5.8",
        ontology_user_input="Model the regest.",
        ontology_min_example_version="1.0.0",
        ontology_model_name="cl100k_base",
        ontology_context_mode="rag",
        ontology_example_limit=1,
        max_output_tokens=20_000,
        output_safety_margin_tokens=4_096,
        require_exact_prompt_tokens=False,
        require_finish_reason=False,
        include_annotations=True,
        use_only_existing_ontology_terms=False,
        allow_text_interpretation=False,
        existing_data_policy="recreate",
    )
