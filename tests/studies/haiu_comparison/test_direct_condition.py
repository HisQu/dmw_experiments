from dmw_experiments.studies.haiu_comparison.comparison_experiment.direct_condition import (
    direct_trace_to_result,
)
from haiu.clients.llm.generation_budget import GenerationBudget
from dmw_experiments.studies.haiu_comparison.model.traces import (
    DirectRunTrace,
    DirectStageTrace,
    PromptBundle,
)


def test_direct_trace_to_result_emits_normalized_fields() -> None:
    trace = DirectRunTrace(
        regest_id="11010116-1",
        success=True,
        started_at="2026-06-18T00:00:00+00:00",
        finished_at="2026-06-18T00:00:02+00:00",
        duration_seconds=2.0,
        model="cl100k_base",
        allow_text_interpretation=False,
        stage1=DirectStageTrace(
            prompts=PromptBundle(system="SYS 1", user="USER 1"),
            output="Plan",
            duration_seconds=1.0,
        ),
        stage2=DirectStageTrace(
            prompts=PromptBundle(system="SYS 2", user="USER 2"),
            output="# --- TBOX ---\n:A a owl:Class .\n# --- ABOX ---\n:i a :A .",
            duration_seconds=1.0,
        ),
        tbox="# --- TBOX ---\n:A a owl:Class .",
        abox="# --- ABOX ---\n:i a :A .",
        retrieved_turtle=":Existing a owl:Class .",
        retrieval_snapshot={"snapshot_fidelity": "native_full_graph"},
        retrieval_query="Header",
        retrieval_duration_seconds=0.2,
        prompt_construction_seconds=0.1,
    )

    result = direct_trace_to_result(trace)

    assert result.condition == "haiu_rag_ontologizer"
    assert result.success is True
    assert result.payload["prompts"]["stage1"]["system"] == "SYS 1"
    assert result.payload["prompt_tokens"] >= 1
    assert result.payload["output_tokens"] >= 1
    assert result.payload["output_chars"] == len("Plan") + 2 + len(
        "# --- TBOX ---\n:A a owl:Class .\n# --- ABOX ---\n:i a :A ."
    )
    assert result.payload["prompt_tokens_complete"] is True
    assert result.payload["turtle_syntax_valid"] is True
    assert result.payload["raw_stage1_output"] == "Plan"
    assert result.payload["raw_stage1_capture_complete"] is True
    assert result.payload["raw_stage1_output_source"] == "direct_haiu_stage1"
    assert result.payload["duration_seconds"] == 2.0
    assert ":A a owl:Class" in str(result.payload["tbox"])
    assert ":i a :A" in str(result.payload["abox"])
    assert result.payload["ontology_context"] == {
        "retrieved_turtle": ":Existing a owl:Class .",
        "retrieval_snapshot": {"snapshot_fidelity": "native_full_graph"},
        "retrieval_metadata": None,
    }


def test_direct_truncation_is_terminal() -> None:
    trace = DirectRunTrace(
        regest_id="11010116-1",
        success=False,
        started_at="2026-06-18T00:00:00+00:00",
        finished_at="2026-06-18T00:00:02+00:00",
        duration_seconds=2.0,
        model="cl100k_base",
        allow_text_interpretation=False,
        error_message="Stage 2 reached the provider output length limit.",
        stage1=DirectStageTrace(
            prompts=PromptBundle(system="SYS 1", user="USER 1"),
        ),
        stage2=DirectStageTrace(
            prompts=PromptBundle(system="SYS 2", user="USER 2"),
            attempted=True,
            generation_budget=GenerationBudget(
                requested_max_output_tokens=20_000,
                predicted_max_output_tokens=20_000,
                effective_max_output_tokens=20_000,
                measured_prompt_tokens=100,
                prompt_token_source="huggingface_chat_template",
                provider_prompt_tokens=100,
                context_window_tokens=262_144,
                safety_margin_tokens=4_096,
                output_constrained=False,
                finish_reason="length",
                output_truncated=True,
                adjustments=(),
                tokenizer_repo="Qwen/Qwen3.6-27B",
                tokenizer_revision="revision",
            ),
        ),
    )

    result = direct_trace_to_result(trace)

    assert result.success is False
    assert result.payload["output_truncated"] is True
    assert result.payload["non_retryable"] is True
    assert result.payload["raw_stage1_output"] == ""
    assert result.payload["raw_stage1_capture_complete"] is False
