"""Datamodel-workflow condition execution and normalization."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, cast

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.annotations import (
    annotation_content_sha256,
)
from dmw_experiments.studies.haiu_comparison.data_collection.dmw.client import (
    DatamodelClient,
    WorkflowRequestConfig,
)
from dmw_experiments.studies.haiu_comparison.data_collection.measurements import (
    output_token_fields,
    prompt_token_fields,
    turtle_generation_input_tokens,
)
from dmw_experiments.studies.haiu_comparison.model.ontology import (
    turtle_syntax_fields,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    ExperimentResult,
)
from haiu.llm_specs import llm_spec


def run_workflow_condition(
    *,
    client: DatamodelClient,
    regest_id: str,
    condition: str,
    config: WorkflowRequestConfig,
) -> ExperimentResult:
    """Run and normalize one datamodel-workflow condition.

    :param client: Authenticated datamodel client.
    :param regest_id: Datamodel regest identifier.
    :param condition: Stable condition name.
    :param config: Workflow request settings.
    :return: Normalized experiment result.
    """
    started_at = _utc_now()
    started_perf = time.perf_counter()
    try:
        status_code, response_payload = client.run_workflow(
            regest_id=regest_id,
            config=config,
        )
        request_duration = time.perf_counter() - started_perf
        success = status_code == 200 and bool(response_payload.get("success"))
        payload = _normalize_workflow_payload(
            response_payload=response_payload,
            condition=condition,
            regest_id=regest_id,
            status_code=status_code,
            success=success,
            started_at=started_at,
            request_duration_seconds=round(request_duration, 3),
            config=config,
        )
        success = bool(payload.get("success"))
        return ExperimentResult(
            condition=condition,
            regest_id=regest_id,
            success=success,
            payload=payload,
        )
    except Exception as exc:
        request_duration = round(time.perf_counter() - started_perf, 3)
        generation_budget = _stage_generation_budgets(
            provider_run_metadata={},
            config=config,
            model=config.ontology_model_name,
        )
        payload = {
            "condition": condition,
            "regest_id": regest_id,
            "success": False,
            "http_status": None,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "duration_seconds": request_duration,
            "attempt_duration_seconds": request_duration,
            "request_duration_seconds": request_duration,
            "ontology_stage_duration_seconds": request_duration,
            "ontology_stage_timing_source": "client_request_wall_clock_fallback",
            "model": config.ontology_model_name,
            "branch_requested": config.branch,
            "annotation_model": config.annotation_model,
            "include_annotations": config.include_annotations,
            "existing_data_policy_requested": config.existing_data_policy,
            "use_only_existing_ontology_terms": (
                config.use_only_existing_ontology_terms
            ),
            "allow_text_interpretation": config.allow_text_interpretation,
            "context_mode_requested": config.ontology_context_mode,
            "context_mode_effective": None,
            "generation_budget": generation_budget,
            "output_constrained": False,
            "output_truncated": False,
            "finish_reason_missing": False,
            "publication_eligible": False,
            "frozen_annotation_sha256": config.frozen_annotation_sha256,
            "prompt_tokens_complete": False,
            "turtle_syntax_valid": None,
            "error_message": f"{type(exc).__name__}: {exc}",
        }
        return ExperimentResult(
            condition=condition,
            regest_id=regest_id,
            success=False,
            payload=payload,
        )


def _normalize_workflow_payload(
    *,
    response_payload: dict[str, Any],
    condition: str,
    regest_id: str,
    status_code: int,
    success: bool,
    started_at: str,
    request_duration_seconds: float,
    config: WorkflowRequestConfig,
) -> dict[str, Any]:
    model = config.ontology_model_name
    debug_data = _dict_payload(response_payload.get("debug_output"))
    ontology_review = response_payload.get("ontology_review")
    ontology_review_data = (
        ontology_review.get("data") if isinstance(ontology_review, dict) else {}
    )
    review_data = _dict_payload(ontology_review_data)
    failure_detail = _dict_payload(response_payload.get("detail"))
    failure_diagnostics = _dict_payload(
        failure_detail.get("generation_diagnostics")
    )
    context_example_provenance = (
        debug_data.get("context_example_provenance")
        or review_data.get("context_example_provenance")
        or failure_diagnostics.get("contextExampleProvenance")
        or []
    )
    ontology_examples_used = debug_data.get("examples_used")
    if ontology_examples_used is None:
        ontology_examples_used = review_data.get("examples_used")
    if (
        ontology_examples_used is None
        and isinstance(context_example_provenance, list)
        and context_example_provenance
    ):
        ontology_examples_used = len(context_example_provenance)
    ontology_context = _dict_payload(
        debug_data.get("ontology_context")
        or review_data.get("ontology_context")
        or failure_diagnostics.get("ontologyContext")
    )
    ontology_stage_timing = _ontology_stage_timing(
        response_payload=response_payload,
        debug_data=debug_data,
        ontology_context=ontology_context,
    )
    ontology_stage_duration = ontology_stage_timing.get("duration_seconds")
    if not isinstance(ontology_stage_duration, int | float):
        ontology_stage_duration = request_duration_seconds
        ontology_stage_timing_source = "client_request_wall_clock_fallback"
    else:
        ontology_stage_timing_source = "dmw_ontology_stage"
    ontology_stage_duration = round(float(ontology_stage_duration), 3)
    retrieval_metadata = _dict_payload(
        ontology_context.get("retrieval_metadata")
    )
    retrieval_status = _dict_payload(retrieval_metadata.get("retrieval_status"))
    retrieval_metadata_observed = "retrieval_metadata" in ontology_context
    rag_retrieval_valid: bool | None = None
    if condition == "workflow_rag":
        retrieved_turtle = ontology_context.get("retrieved_turtle")
        retrieval_snapshot = ontology_context.get("retrieval_snapshot")
        rag_retrieval_valid = (
            retrieval_metadata_observed
            and retrieval_status.get("status") != "recovered_error"
            and isinstance(retrieved_turtle, str)
            and bool(retrieved_turtle.strip())
            and isinstance(retrieval_snapshot, dict)
            and retrieval_snapshot.get("snapshot_fidelity")
            == "native_full_graph"
        )
        if not rag_retrieval_valid:
            success = False
    prompts = _prompts_from(debug_data, review_data, failure_diagnostics)
    stage_prompts = _stage_prompts_from(
        debug_data, review_data, failure_diagnostics, prompts
    )
    explanation = str(
        debug_data.get("explanation") or review_data.get("explanation") or ""
    )
    raw_stage1_output, raw_stage1_output_source = _raw_stage1_output(
        explanation=explanation,
        debug_data=debug_data,
        review_data=review_data,
        failure_diagnostics=failure_diagnostics,
    )
    tbox = str(debug_data.get("tbox") or review_data.get("tbox") or "")
    abox = str(debug_data.get("abox") or review_data.get("abox") or "")
    raw_ttl_output = _raw_ttl_output(
        debug_data, review_data, failure_diagnostics
    )
    raw_ttl_capture_complete = bool(raw_ttl_output)
    if success and not raw_ttl_capture_complete:
        success = False
    output_text = "\n\n".join(
        part for part in (explanation, tbox, abox) if part
    )
    observed_output_text = output_text or raw_ttl_output
    prompt_fields = prompt_token_fields(prompts, model=model, prefix="workflow")
    stage2_prompt_fields = prompt_token_fields(
        stage_prompts.get("workflow_stage2", {}),
        model=model,
        prefix="workflow_stage2",
    )
    output_fields = output_token_fields(
        observed_output_text, model=model, prefix="output"
    )
    turtle_text = "\n\n".join(part for part in (tbox, abox) if part)
    annotation_review = _dict_payload(response_payload.get("annotation_review"))
    annotation_review_data = _dict_payload(annotation_review.get("data"))
    observed_annotation_sha256 = _annotation_review_sha256(
        annotation_review_data
    )
    annotation_matches_frozen = (
        observed_annotation_sha256 == config.frozen_annotation_sha256
        if config.frozen_annotation_sha256
        and observed_annotation_sha256 is not None
        else None
    )
    if (
        success
        and config.require_existing_annotation
        and annotation_matches_frozen is not True
    ):
        success = False
    reused_existing_data = bool(response_payload.get("reused_existing_data"))
    if success and reused_existing_data:
        success = False
    provider_run_metadata = _dict_payload(
        debug_data.get("provider_run_metadata")
        or review_data.get("provider_run_metadata")
        or failure_diagnostics.get("providerRunMetadata")
    )
    generation_budget = _stage_generation_budgets(
        provider_run_metadata=provider_run_metadata,
        config=config,
        model=model,
    )
    output_truncated = any(
        budget.get("output_truncated") is True
        for budget in generation_budget.values()
    )
    finish_reason_missing = any(
        budget.get("attempted") is True and budget.get("finish_reason") is None
        for budget in generation_budget.values()
    )
    publication_eligible = (
        success
        and not output_truncated
        and not finish_reason_missing
        and all(
            budget.get("attempted") is True
            for budget in generation_budget.values()
        )
    )
    if success and output_truncated:
        success = False
    if success and config.require_finish_reason and finish_reason_missing:
        success = False
    stage_timings = _workflow_stage_timings(
        debug_data, review_data, failure_diagnostics
    )
    provider_usage = _workflow_provider_usage_fields(provider_run_metadata)
    prompt_tokens = turtle_generation_input_tokens(
        stage1_user=str(prompts.get("user") or ""),
        stage1_output=explanation,
        stage2_system=str(
            stage_prompts.get("workflow_stage2", {}).get("system") or ""
        ),
        stage2_user=str(
            stage_prompts.get("workflow_stage2", {}).get("user") or ""
        ),
        stage2_provider_prompt_tokens=(
            generation_budget["stage2"].get("provider_prompt_tokens")
        ),
        model=model,
    )
    stage1_reduction = _stage_context_reduction(
        provider_run_metadata, stage="stage1"
    )
    stage2_reduction = _stage_context_reduction(
        provider_run_metadata, stage="stage2"
    )
    pipeline_error = _optional_text(failure_detail.get("pipeline_error"))
    failure_code = _optional_text(failure_detail.get("failure_code"))
    context_capacity_failure = _is_context_capacity_failure(
        failure_code=failure_code,
        pipeline_error=pipeline_error,
    )
    if context_capacity_failure:
        # > Older locked DMW builds can expose this deterministic failure with
        # > the generic ontology-generation code. Normalize it at the
        # > experiment boundary so the retry policy never repeats it.
        failure_code = "model_context_window_exceeded"
    error_message = None
    if not success:
        error_message = (
            "DMW reused a prior ontology result; every condition must generate "
            "a fresh ontology observation."
            if reused_existing_data
            else (
                "Haiu semantic retrieval recovered from an error; the RAG "
                "observation is invalid."
                if retrieval_status.get("status") == "recovered_error"
                else (
                    "DMW returned an annotation whose content differs from the "
                    "frozen experiment input."
                    if annotation_matches_frozen is False
                    else (
                        "Provider output ended at the length limit."
                        if output_truncated
                        else (
                            "Provider finish_reason is missing; the observation "
                            "is not publication-eligible."
                            if config.require_finish_reason
                            and finish_reason_missing
                            else _workflow_failure_message(
                                response_payload=response_payload,
                                failure_code=failure_code,
                                pipeline_error=pipeline_error,
                                raw_ttl_capture_complete=(
                                    raw_ttl_capture_complete
                                ),
                            )
                        )
                    )
                )
            )
        )
    return {
        "condition": condition,
        "regest_id": regest_id,
        "success": success,
        "http_status": status_code,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_seconds": ontology_stage_duration,
        "attempt_duration_seconds": ontology_stage_duration,
        "request_duration_seconds": request_duration_seconds,
        "ontology_stage_duration_seconds": ontology_stage_duration,
        "ontology_stage_timing_source": ontology_stage_timing_source,
        "ontology_stage_timing": ontology_stage_timing or None,
        "model": model,
        "branch_requested": config.branch,
        "annotation_model": config.annotation_model,
        "frozen_annotation_sha256": config.frozen_annotation_sha256,
        "observed_annotation_sha256": observed_annotation_sha256,
        "annotation_matches_frozen": annotation_matches_frozen,
        "include_annotations": config.include_annotations,
        "existing_data_policy_requested": config.existing_data_policy,
        "use_only_existing_ontology_terms": (
            config.use_only_existing_ontology_terms
        ),
        "allow_text_interpretation": config.allow_text_interpretation,
        "annotation_version": response_payload.get("annotation_version"),
        "ontology_record_version": response_payload.get(
            "ontology_record_version"
        ),
        "ontology_context_version": response_payload.get(
            "ontology_context_version"
        ),
        "existing_data_policy": response_payload.get("existing_data_policy"),
        "reused_existing_data": reused_existing_data,
        "context_mode_requested": (
            debug_data.get("context_mode_requested")
            or config.ontology_context_mode
        ),
        "context_mode_effective": debug_data.get("context_mode_effective"),
        "context_mode_estimated_ontology_tokens": debug_data.get(
            "context_mode_estimated_ontology_tokens"
        ),
        "context_mode_context_window_tokens": debug_data.get(
            "context_mode_context_window_tokens"
        ),
        "ontology_ref": (
            debug_data.get("ontology_ref") or review_data.get("ontology_ref")
        ),
        "ontology_context": ontology_context,
        "rag_retrieval_status": retrieval_status or None,
        "rag_retrieval_valid": rag_retrieval_valid,
        "generation_dependency": debug_data.get("dependency"),
        "provider_run_metadata": provider_run_metadata or None,
        "generation_budget": generation_budget,
        "output_constrained": any(
            budget.get("output_constrained") is True
            for budget in generation_budget.values()
        ),
        "output_truncated": output_truncated,
        "finish_reason_missing": finish_reason_missing,
        "publication_eligible": publication_eligible,
        "stage_timings": stage_timings or None,
        "annotation_override_used": bool(
            debug_data.get("annotation_override_used")
            or review_data.get("annotation_override_used")
        ),
        "ontology_examples_used": ontology_examples_used,
        "ontology_example_limit_requested": config.ontology_example_limit,
        "context_example_provenance": context_example_provenance,
        "prompt_token_report": (
            review_data.get("prompt_token_report")
            or failure_diagnostics.get("promptTokenReport")
        ),
        "prompt_observation": (
            "Full input before Turtle generation is counted, including "
            "retained Stage-1 input and plan; provider usage takes priority "
            "over local estimates."
        ),
        "explanation": explanation,
        "tbox": tbox,
        "abox": abox,
        "raw_stage1_output": raw_stage1_output,
        "raw_stage1_capture_complete": bool(raw_stage1_output),
        "raw_stage1_output_source": raw_stage1_output_source,
        "raw_ttl_output": raw_ttl_output,
        "raw_ttl_capture_complete": raw_ttl_capture_complete,
        "prompts": stage_prompts,
        "raw_response": response_payload,
        "generation_attempts": _generation_attempt_records(
            failure_detail.get("generation_attempts")
            or debug_data.get("generation_attempts")
            or [],
            config=config,
            model=model,
        ),
        "error_message": error_message,
        "pipeline_error": pipeline_error,
        "failure_code": failure_code,
        "non_retryable": (
            failure_detail.get("non_retryable") is True
            or context_capacity_failure
            or output_truncated
        ),
        "stage1_context_reduced": stage1_reduction is not None,
        "stage1_context_reduction": stage1_reduction,
        "stage2_output_reduced": stage2_reduction is not None,
        "stage2_output_reduction": stage2_reduction,
        "prompt_tokens": prompt_tokens.tokens,
        "prompt_tokens_source": prompt_tokens.source,
        "prompt_tokens_complete": prompt_tokens.source == "provider"
        or (
            bool(prompts.get("user"))
            and bool(
                stage_prompts.get("workflow_stage2", {}).get("system")
                or stage_prompts.get("workflow_stage2", {}).get("user")
            )
        ),
        "output_observation": "Stage 1 plan plus Stage 2 Turtle",
        **prompt_fields,
        **stage2_prompt_fields,
        **output_fields,
        **turtle_syntax_fields(raw_ttl_output or turtle_text),
        **provider_usage,
    }


def _dict_payload(value: Any) -> dict[str, Any]:
    """Normalize a JSON object boundary to a string-keyed dictionary.

    :param value: Parsed API payload fragment.
    :return: Dictionary when the fragment is JSON object-like, otherwise empty.
    """
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _stage_generation_budgets(
    *,
    provider_run_metadata: dict[str, Any],
    config: WorkflowRequestConfig,
    model: str,
) -> dict[str, dict[str, Any]]:
    """Normalize stable Stage-1 and Stage-2 generation budget records.

    :param provider_run_metadata: OPA provider metadata keyed by stage.
    :param config: Requested experiment controls.
    :param model: Provider model alias.
    :return: Complete stage-keyed records, including unattempted stages.
    """
    try:
        context_window_tokens = llm_spec(model).context_token_limit
    except ValueError:
        context_window_tokens = None

    budgets: dict[str, dict[str, Any]] = {}
    for stage in ("stage1", "stage2"):
        stage_metadata = _dict_payload(provider_run_metadata.get(stage))
        budget = _dict_payload(stage_metadata.get("generation_budget"))
        completion_params = _dict_payload(
            stage_metadata.get("completion_params")
        )
        usage = _dict_payload(stage_metadata.get("usage"))
        requested = budget.get(
            "requested_max_output_tokens",
            config.max_output_tokens,
        )
        effective = budget.get(
            "effective_max_output_tokens",
            completion_params.get("max_tokens"),
        )
        finish_reason = budget.get(
            "finish_reason",
            stage_metadata.get("finish_reason"),
        )
        output_truncated = budget.get(
            "output_truncated",
            stage_metadata.get("output_truncated"),
        )
        output_constrained = budget.get("output_constrained")
        if (
            output_constrained is None
            and isinstance(requested, int)
            and isinstance(effective, int)
        ):
            output_constrained = effective < requested
        adjustments = budget.get(
            "adjustments",
            stage_metadata.get("context_window_adjustments") or [],
        )
        budgets[stage] = {
            "requested_max_output_tokens": requested,
            "predicted_max_output_tokens": budget.get(
                "predicted_max_output_tokens"
            ),
            "effective_max_output_tokens": effective,
            "measured_prompt_tokens": budget.get("measured_prompt_tokens"),
            "prompt_token_source": budget.get("prompt_token_source"),
            "provider_prompt_tokens": budget.get(
                "provider_prompt_tokens",
                usage.get("prompt_tokens"),
            ),
            "context_window_tokens": budget.get(
                "context_window_tokens",
                context_window_tokens,
            ),
            "safety_margin_tokens": budget.get(
                "safety_margin_tokens",
                config.output_safety_margin_tokens,
            ),
            "output_constrained": output_constrained,
            "finish_reason": finish_reason,
            "output_truncated": output_truncated,
            "adjustments": adjustments if isinstance(adjustments, list) else [],
            "tokenizer_repo": budget.get("tokenizer_repo"),
            "tokenizer_revision": budget.get("tokenizer_revision"),
            "attempted": bool(stage_metadata),
        }
    return budgets


def _generation_attempt_records(
    value: object,
    *,
    config: WorkflowRequestConfig,
    model: str,
) -> list[dict[str, Any]]:
    """Attach stable stage budgets to every retained DMW generation attempt.

    :param value: Dynamic DMW attempt list.
    :param config: Requested experiment controls.
    :param model: Provider model alias.
    :return: Object-shaped attempts with stage-keyed generation budgets.
    """
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for raw_attempt in value:
        if not isinstance(raw_attempt, dict):
            continue
        attempt = dict(raw_attempt)
        diagnostics = _dict_payload(attempt.get("diagnostics"))
        provider_metadata = _dict_payload(
            diagnostics.get("providerRunMetadata")
            or diagnostics.get("provider_run_metadata")
        )
        attempt["generation_budget"] = _stage_generation_budgets(
            provider_run_metadata=provider_metadata,
            config=config,
            model=model,
        )
        records.append(attempt)
    return records


def _optional_text(value: object) -> str | None:
    """Normalize an optional API scalar to non-empty text.

    :param value: Parsed JSON value from a dynamic response boundary.
    :return: Stripped text, or ``None`` when no content is available.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _prompts_from(
    debug_data: dict[str, Any],
    review_data: dict[str, Any],
    failure_diagnostics: dict[str, Any],
) -> dict[str, str]:
    raw_prompts = (
        debug_data.get("prompts")
        or review_data.get("prompts")
        or failure_diagnostics.get("prompts")
        or {}
    )
    if not isinstance(raw_prompts, dict):
        return {"system": "", "user": ""}
    return {
        "system": str(raw_prompts.get("system") or ""),
        "user": str(raw_prompts.get("user") or ""),
    }


def _stage_prompts_from(
    debug_data: dict[str, Any],
    review_data: dict[str, Any],
    failure_diagnostics: dict[str, Any],
    stage1_prompts: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Capture both OPA prompt stages while retaining legacy Stage-1 fields.

    :param debug_data: DMW debug output object.
    :param review_data: Successful DMW ontology review object.
    :param failure_diagnostics: Failure-only diagnostics emitted by DMW.
    :param stage1_prompts: Legacy Stage-1 prompt bundle.
    :return: Stage-keyed prompt captures for artifact writing.
    """
    raw_stage_prompts = (
        debug_data.get("stage_prompts")
        or review_data.get("stage_prompts")
        or failure_diagnostics.get("stagePrompts")
        or {}
    )
    stage_prompts: dict[str, dict[str, str]] = {
        "workflow_stage1": stage1_prompts
    }
    if not isinstance(raw_stage_prompts, dict):
        return stage_prompts
    for stage, bundle in raw_stage_prompts.items():
        if not isinstance(stage, str) or not isinstance(bundle, dict):
            continue
        stage_prompts[f"workflow_{stage}"] = {
            "system": str(bundle.get("system") or ""),
            "user": str(bundle.get("user") or ""),
        }
    return stage_prompts


def _raw_ttl_output(
    debug_data: dict[str, Any],
    review_data: dict[str, Any],
    failure_diagnostics: dict[str, Any],
) -> str:
    """Return the Stage-2 response before DMW/OPA parsing or repair.

    :param debug_data: DMW debug output object.
    :param review_data: DMW ontology review object.
    :return: Unmodified Stage-2 Turtle response, or an empty string when absent.
    """
    for source in (debug_data, review_data, failure_diagnostics):
        for key in ("raw_ttl_output", "rawTtlOutput"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _raw_stage1_output(
    *,
    explanation: str,
    debug_data: dict[str, Any],
    review_data: dict[str, Any],
    failure_diagnostics: dict[str, Any],
) -> tuple[str, str | None]:
    """Capture the unmodified Stage-1 Designer reply when DMW exposes it.

    Successful OPA workflow responses expose the exact planner message as
    ``explanation``. Newer upstream failure diagnostics expose the same text
    as ``designerResponse``. A missing reply stays empty rather than being
    reconstructed from Stage-2 input, tokens, or Turtle output.

    :param explanation: Workflow success plan retained by DMW.
    :param debug_data: DMW debug output object.
    :param review_data: DMW ontology review object.
    :param failure_diagnostics: Failure-only diagnostics emitted by DMW.
    :return: Exact reply and its observed source, or an empty unavailable pair.
    """
    for source_name, source, keys in (
        (
            "workflow_explanation",
            {"explanation": explanation},
            ("explanation",),
        ),
        (
            "workflow_debug_designer_response",
            debug_data,
            ("designer_response",),
        ),
        ("workflow_debug_designer_response", debug_data, ("designerResponse",)),
        (
            "workflow_review_designer_response",
            review_data,
            ("designer_response",),
        ),
        (
            "workflow_review_designer_response",
            review_data,
            ("designerResponse",),
        ),
        (
            "workflow_failure_designer_response",
            failure_diagnostics,
            ("designerResponse",),
        ),
        (
            "workflow_failure_designer_response",
            failure_diagnostics,
            ("designer_response",),
        ),
    ):
        value = source
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value:
            return value, source_name
    return "", None


def _workflow_stage_timings(
    debug_data: dict[str, Any],
    review_data: dict[str, Any],
    failure_diagnostics: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Normalize OPA stage timing scopes exposed by DMW.

    :param debug_data: DMW debug output object.
    :param review_data: DMW ontology review object.
    :return: Named OPA server-wall-clock scopes, or an empty dictionary.
    """
    scopes = (
        debug_data.get("timing_scopes")
        or review_data.get("timing_scopes")
        or failure_diagnostics.get("timingScopes")
    )
    if not isinstance(scopes, dict):
        return {}
    return {
        str(name): _dict_payload(value)
        for name, value in scopes.items()
        if isinstance(value, dict)
    }


def _error_message(response_payload: dict[str, Any]) -> str:
    for key in ("message", "error", "detail"):
        value = response_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message.strip():
                return message
    return "Workflow request failed."


def _workflow_failure_message(
    *,
    response_payload: dict[str, Any],
    failure_code: str | None,
    pipeline_error: str | None,
    raw_ttl_capture_complete: bool,
) -> str:
    """Describe the terminal workflow cause before capture-side consequences.

    A failed provider call cannot produce Stage-2 Turtle. Reporting only that
    missing artifact hid context overflows and other upstream failures in the
    experiment records.

    :param response_payload: Complete DMW response.
    :param failure_code: Structured terminal DMW failure code.
    :param pipeline_error: Detailed pipeline error when supplied by DMW.
    :param raw_ttl_capture_complete: Whether DMW returned unmodified Stage-2 Turtle.
    :return: Human-readable primary failure with capture consequence when needed.
    """
    detail = pipeline_error or _error_message(response_payload)
    if failure_code == "model_context_window_exceeded":
        return f"Model context window exceeded: {detail}"
    if failure_code:
        return f"Workflow failure ({failure_code}): {detail}"
    if not raw_ttl_capture_complete:
        return (
            f"{detail} DMW/OPA did not return the exact unmodified Stage-2 "
            "Turtle response; the observation is invalid for this experiment."
        )
    return detail


def _is_context_capacity_failure(
    *,
    failure_code: str | None,
    pipeline_error: str | None,
) -> bool:
    """Recognize a deterministic model-context exhaustion response.

    The DMW API normally provides ``model_context_window_exceeded``. This
    defensive boundary check preserves the experimental retry contract when a
    previously locked API build instead returns the generic ontology failure
    code alongside the unambiguous context-capacity error text.

    :param failure_code: Structured DMW error code, when provided.
    :param pipeline_error: Detailed DMW pipeline failure text, when provided.
    :return: Whether retrying the same immutable prompt cannot succeed.
    """
    if failure_code == "model_context_window_exceeded":
        return True
    normalized_error = (pipeline_error or "").casefold()
    return "prompt and safety margin exhaust the model context window" in (
        normalized_error
    )


def _ontology_stage_timing(
    *,
    response_payload: dict[str, Any],
    debug_data: dict[str, Any],
    ontology_context: dict[str, Any],
) -> dict[str, Any]:
    """Find DMW's persisted ontology-only timing record.

    :param response_payload: Complete E2E response.
    :param debug_data: Normalized E2E debug object.
    :param ontology_context: Persisted OPA context diagnostics.
    :return: Timing record, or an empty dictionary when unavailable.
    """
    detail = _dict_payload(response_payload.get("detail"))
    for value in (
        response_payload.get("ontology_stage_timing"),
        debug_data.get("ontology_stage_timing"),
        ontology_context.get("dmw_ontology_stage_timing"),
        detail.get("ontology_stage_timing"),
    ):
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
    return {}


def _annotation_review_sha256(review_data: dict[str, Any]) -> str | None:
    """Hash annotation content returned alongside an ontology result.

    :param review_data: DMW annotation review object.
    :return: Canonical digest, or ``None`` when the response lacks content.
    """
    header_entities = review_data.get("header_entities")
    subentry_entities = review_data.get("subentry_entities")
    if not isinstance(header_entities, list) or not isinstance(
        subentry_entities, list
    ):
        return None
    if not all(isinstance(item, dict) for item in header_entities):
        return None
    if not all(isinstance(item, dict) for item in subentry_entities):
        return None
    return annotation_content_sha256(
        header_entities=[
            cast(dict[str, Any], dict(item)) for item in header_entities
        ],
        subentry_entities=[
            cast(dict[str, Any], dict(item)) for item in subentry_entities
        ],
    )


def _workflow_provider_usage_fields(
    provider_run_metadata: dict[str, Any],
) -> dict[str, int | bool | None | str]:
    """Flatten Stage 1 and Stage 2 provider token usage.

    :param provider_run_metadata: OPA metadata keyed by ontology stage.
    :return: Per-stage token counts and a completeness declaration.
    """
    fields: dict[str, int | bool | None | str] = {}
    complete = True
    stage_total_tokens: list[int] = []
    for stage in ("stage1", "stage2"):
        stage_metadata = _dict_payload(provider_run_metadata.get(stage))
        usage = _dict_payload(stage_metadata.get("usage"))
        stage_complete = True
        for token_kind in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            value = usage.get(token_kind)
            normalized = (
                int(value)
                if isinstance(value, int) and not isinstance(value, bool)
                else None
            )
            fields[f"workflow_{stage}_provider_{token_kind}"] = normalized
            stage_complete = stage_complete and normalized is not None
            if token_kind == "total_tokens" and normalized is not None:
                stage_total_tokens.append(normalized)
        fields[f"workflow_{stage}_provider_usage_complete"] = stage_complete
        complete = complete and stage_complete
    fields["ontology_provider_usage_complete"] = complete
    fields["ontology_provider_total_tokens"] = (
        sum(stage_total_tokens) if complete else None
    )
    fields["ontology_cost_observation_complete"] = False
    fields["ontology_provider_usage_scope"] = (
        "successful returned Stage 1 and Stage 2 calls only; failed or "
        "provider-internal retry calls are unavailable"
        if complete
        else "incomplete provider metadata"
    )
    return fields


def _stage_context_reduction(
    provider_run_metadata: dict[str, Any], *, stage: str
) -> dict[str, Any] | None:
    """Return one explicit OPA context-window adjustment.

    :param provider_run_metadata: OPA metadata keyed by ontology stage.
    :param stage: OPA generation stage whose adjustment is requested.
    :return: Adjustment payload, or ``None`` when no adjustment occurred.
    """
    stage_metadata = _dict_payload(provider_run_metadata.get(stage))
    adjustment = _dict_payload(stage_metadata.get("context_window_adjustment"))
    return adjustment or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
