"""Experiment adapter for the direct Haiu ontologizer condition."""

from __future__ import annotations

from haiu import HaiuRC

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.metrics import (
    output_token_fields,
    prompt_token_fields,
    provider_usage_fields,
    turtle_generation_input_tokens,
    turtle_syntax_fields,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.models import (
    ExperimentResult,
    TokenMeasurement,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.direct_runner import (
    DirectRunConfig,
    run_direct_baseline,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.models import (
    DirectRunTrace,
    RegestText,
)

HAIU_RAG_CONDITION = "haiu_rag_ontologizer"


def run_haiu_rag_condition(
    *,
    regest: RegestText,
    config: DirectRunConfig,
    rc: HaiuRC,
) -> ExperimentResult:
    """Run standalone Haiu retrieval and normalize it for experiment outputs.

    :param regest: Raw-only regest text.
    :param config: Direct condition configuration.
    :param rc: Resolved Haiu runtime config.
    :return: Normalized experiment result.
    """
    trace = run_direct_baseline(regest=regest, config=config, rc=rc)
    return direct_trace_to_result(trace)


def direct_trace_to_result(trace: DirectRunTrace) -> ExperimentResult:
    """Convert a standalone Haiu-RAG trace into the common row shape.

    :param trace: Direct Haiu ontologizer trace.
    :return: Normalized experiment result.
    """
    payload = (
        _success_payload(trace) if trace.success else _failure_payload(trace)
    )
    return ExperimentResult(
        condition=HAIU_RAG_CONDITION,
        regest_id=trace.regest_id,
        success=trace.success,
        payload=payload,
    )


def _success_payload(trace: DirectRunTrace) -> dict[str, object]:
    return {
        "condition": HAIU_RAG_CONDITION,
        "regest_id": trace.regest_id,
        "success": True,
        "started_at": trace.started_at,
        "finished_at": trace.finished_at,
        "duration_seconds": trace.duration_seconds,
        "model": trace.model,
        "context_mode_requested": "haiu_rag",
        "context_mode_effective": "haiu_rag",
        "allow_text_interpretation": trace.allow_text_interpretation,
        "prompt_observation": "all standalone Stage 1 and Stage 2 calls are observed",
        "explanation": trace.stage1.output,
        "tbox": trace.tbox,
        "abox": trace.abox,
        "raw_stage1_output": trace.stage1.output,
        "raw_stage1_capture_complete": bool(trace.stage1.output),
        "raw_stage1_output_source": "direct_haiu_stage1",
        "raw_ttl_output": trace.stage2.output,
        "raw_ttl_capture_complete": bool(trace.stage2.output),
        "parse_warning": trace.parse_warning,
        "prompts": _prompt_payload(trace),
        "stage_metrics": _stage_metrics(trace),
        "generation_budget": _generation_budget_payload(trace),
        "output_constrained": _output_constrained(trace),
        "output_truncated": _output_truncated(trace),
        "finish_reason_missing": _finish_reason_missing(trace),
        "publication_eligible": _publication_eligible(trace),
        "ontology_context": {
            "retrieved_turtle": trace.retrieved_turtle,
            "retrieval_snapshot": trace.retrieval_snapshot,
            "retrieval_metadata": (
                trace.retrieval_snapshot.get("metadata")
                if trace.retrieval_snapshot is not None
                else None
            ),
        },
        "retrieval_query": trace.retrieval_query,
        "retrieval_duration_seconds": trace.retrieval_duration_seconds,
        "prompt_construction_duration_seconds": (
            trace.prompt_construction_seconds
        ),
        "stage1_context_reduced": False,
        "stage1_context_reduction": None,
        "stage2_output_reduced": False,
        "stage2_output_reduction": None,
        **turtle_syntax_fields(trace.stage2.output),
        **_aggregate_size_fields(trace),
    }


def _failure_payload(trace: DirectRunTrace) -> dict[str, object]:
    return {
        "condition": HAIU_RAG_CONDITION,
        "regest_id": trace.regest_id,
        "success": False,
        "started_at": trace.started_at,
        "finished_at": trace.finished_at,
        "duration_seconds": trace.duration_seconds,
        "model": trace.model,
        "allow_text_interpretation": trace.allow_text_interpretation,
        "error_message": trace.error_message,
        "raw_stage1_output": trace.stage1.output,
        "raw_stage1_capture_complete": bool(trace.stage1.output),
        "raw_stage1_output_source": "direct_haiu_stage1",
        "raw_ttl_output": trace.stage2.output,
        "raw_ttl_capture_complete": bool(trace.stage2.output),
        "prompts": _prompt_payload(trace),
        "stage_metrics": _stage_metrics(trace),
        "generation_budget": _generation_budget_payload(trace),
        "output_constrained": _output_constrained(trace),
        "output_truncated": _output_truncated(trace),
        "non_retryable": _output_truncated(trace),
        "finish_reason_missing": _finish_reason_missing(trace),
        "publication_eligible": False,
        "ontology_context": {
            "retrieved_turtle": trace.retrieved_turtle,
            "retrieval_snapshot": trace.retrieval_snapshot,
        },
        "retrieval_query": trace.retrieval_query,
        "retrieval_duration_seconds": trace.retrieval_duration_seconds,
        "prompt_construction_duration_seconds": (
            trace.prompt_construction_seconds
        ),
        "stage1_context_reduced": False,
        "stage1_context_reduction": None,
        "stage2_output_reduced": False,
        "stage2_output_reduction": None,
        **turtle_syntax_fields(trace.stage2.output),
    }


def _prompt_payload(trace: DirectRunTrace) -> dict[str, dict[str, str]]:
    return {
        "stage1": {
            "system": trace.stage1.prompts.system,
            "user": trace.stage1.prompts.user,
        },
        "stage2": {
            "system": trace.stage2.prompts.system,
            "user": trace.stage2.prompts.user,
        },
    }


def _stage_metrics(trace: DirectRunTrace) -> dict[str, dict[str, object]]:
    return {
        "retrieval": {
            "duration_seconds": trace.retrieval_duration_seconds,
            "query": trace.retrieval_query,
            "snapshot_fidelity": (
                trace.retrieval_snapshot.get("snapshot_fidelity")
                if trace.retrieval_snapshot is not None
                else None
            ),
        },
        "prompt_construction": {
            "duration_seconds": trace.prompt_construction_seconds,
        },
        "stage1": {
            "duration_seconds": trace.stage1.duration_seconds,
            **prompt_token_fields(
                trace.stage1.prompts,
                model=trace.model,
                prefix="stage1",
            ),
            **output_token_fields(
                trace.stage1.output,
                model=trace.model,
                prefix="stage1_output",
            ),
            **provider_usage_fields(trace.stage1.response, prefix="stage1"),
        },
        "stage2": {
            "duration_seconds": trace.stage2.duration_seconds,
            **prompt_token_fields(
                trace.stage2.prompts,
                model=trace.model,
                prefix="stage2",
            ),
            **output_token_fields(
                trace.stage2.output,
                model=trace.model,
                prefix="stage2_output",
            ),
            **provider_usage_fields(trace.stage2.response, prefix="stage2"),
        },
    }


def _aggregate_size_fields(trace: DirectRunTrace) -> dict[str, int | str]:
    prompt_tokens = _turtle_generation_input_tokens(trace)
    output_text = "\n\n".join(
        part for part in (trace.stage1.output, trace.stage2.output) if part
    )
    output = output_token_fields(
        output_text, model=trace.model, prefix="output"
    )
    return {
        "prompt_tokens": prompt_tokens.tokens,
        "prompt_tokens_source": prompt_tokens.source,
        "prompt_tokens_complete": True,
        "output_tokens": output["output_tokens"],
        "output_tokens_source": output["output_tokens_source"],
        "output_chars": output["output_chars"],
        "output_observation": "Stage 1 plan plus Stage 2 Turtle",
    }


def _turtle_generation_input_tokens(
    trace: DirectRunTrace,
) -> TokenMeasurement:
    """Return the full input context sent before direct Turtle generation.

    :param trace: Direct Haiu ontologizer execution trace.
    :return: Stage-2 input measurement excluding the generated Turtle.
    """
    return turtle_generation_input_tokens(
        stage1_user=trace.stage1.prompts.user,
        stage1_output=trace.stage1.output,
        stage2_system=trace.stage2.prompts.system,
        stage2_user=trace.stage2.prompts.user,
        stage2_provider_prompt_tokens=(
            trace.stage2.response.metrics.prompt_tokens
            if trace.stage2.response is not None
            else None
        ),
        model=trace.model,
    )


def _generation_budget_payload(
    trace: DirectRunTrace,
) -> dict[str, dict[str, object]]:
    """Return stable stage-keyed budget records, including unattempted stages.

    :param trace: Direct execution trace.
    :return: Stage-1 and Stage-2 generation budget records.
    """
    payload: dict[str, dict[str, object]] = {}
    for stage_name, stage in (
        ("stage1", trace.stage1),
        ("stage2", trace.stage2),
    ):
        budget = (
            stage.generation_budget.as_dict()
            if stage.generation_budget is not None
            else {
                "requested_max_output_tokens": (
                    trace.requested_max_output_tokens
                ),
                "predicted_max_output_tokens": None,
                "effective_max_output_tokens": None,
                "measured_prompt_tokens": None,
                "prompt_token_source": None,
                "provider_prompt_tokens": None,
                "context_window_tokens": trace.context_window_tokens,
                "safety_margin_tokens": (trace.output_safety_margin_tokens),
                "output_constrained": None,
                "finish_reason": None,
                "output_truncated": None,
                "adjustments": [],
                "tokenizer_repo": None,
                "tokenizer_revision": None,
            }
        )
        budget["attempted"] = stage.attempted
        payload[stage_name] = budget
    return payload


def _output_constrained(trace: DirectRunTrace) -> bool:
    """Return whether either direct stage used less than the requested cap.

    :param trace: Direct execution trace.
    :return: Whether predictive budgeting constrained an attempted request.
    """
    return any(
        stage.generation_budget is not None
        and stage.generation_budget.output_constrained
        for stage in (trace.stage1, trace.stage2)
    )


def _publication_eligible(trace: DirectRunTrace) -> bool:
    """Check stop-cause completeness for a successful direct observation.

    :param trace: Direct execution trace.
    :return: Whether both provider calls ended naturally with known reasons.
    """
    return trace.success and all(
        stage.generation_budget is not None
        and stage.generation_budget.finish_reason is not None
        and stage.generation_budget.output_truncated is False
        for stage in (trace.stage1, trace.stage2)
    )


def _output_truncated(trace: DirectRunTrace) -> bool:
    """Return whether an attempted direct stage ended at the length limit.

    :param trace: Direct execution trace.
    :return: Whether provider metadata identifies truncation.
    """
    return any(
        stage.generation_budget is not None
        and stage.generation_budget.output_truncated is True
        for stage in (trace.stage1, trace.stage2)
    )


def _finish_reason_missing(trace: DirectRunTrace) -> bool:
    """Return whether an attempted stage lacks provider stop metadata.

    :param trace: Direct execution trace.
    :return: Whether any attempted stage has no finish reason.
    """
    return any(
        stage.attempted
        and (
            stage.generation_budget is None
            or stage.generation_budget.finish_reason is None
        )
        for stage in (trace.stage1, trace.stage2)
    )
