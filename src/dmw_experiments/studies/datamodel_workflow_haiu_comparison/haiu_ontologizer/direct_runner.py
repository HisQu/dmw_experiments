"""Direct Haiu LLM baseline execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from haiu import GenerationBudget, HaiuRC, LLMClient, resolve_generation_budget
from haiu.clients.llm.llm_metrics import LLMCallMeta
from haiu.llm_specs import llm_spec

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.models import (
    DirectRunTrace,
    DirectStageTrace,
    PromptBundle,
    RegestText,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.prompt_builder import (
    build_stage1_prompts,
    build_stage2_prompts,
    split_turtle_sections,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.haiu_ontologizer.retrieval import (
    RetrievalTrace,
    retrieve_regest_context,
)


@dataclass(frozen=True, slots=True)
class DirectRunConfig:
    """Configuration for the standalone Haiu-RAG ontologizer.

    :param model: Haiu LLM model name.
    :param historian_input: Shared ontology instruction text.
    :param annotation_guidelines: Historian-curated annotation guidance.
    :param max_tokens: Optional completion token override.
    :param temperature: Optional sampling temperature override.
    :param top_p: Nucleus sampling probability.
    :param top_k: Candidate cap sent through the provider extra body.
    :param min_p: Minimum probability sent through the provider extra body.
    :param frequency_penalty: Frequency penalty for generation.
    :param presence_penalty: Presence penalty for generation.
    :param allow_text_interpretation: Whether implicit text facts may be inferred.
    :param output_safety_margin_tokens: Context reserved outside prompt/output.
    :param require_exact_prompt_tokens: Require the pinned chat tokenizer.
    :param require_finish_reason: Reject provider responses without a stop cause.
    """

    model: str
    historian_input: str
    annotation_guidelines: str
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    allow_text_interpretation: bool = False
    output_safety_margin_tokens: int = 4_096
    require_exact_prompt_tokens: bool = False
    require_finish_reason: bool = False


def run_direct_baseline(
    *,
    regest: RegestText,
    config: DirectRunConfig,
    rc: HaiuRC,
) -> DirectRunTrace:
    """Run standalone Haiu retrieval and two-stage ontology generation.

    :param regest: Raw-only regest text.
    :param config: Direct condition configuration.
    :param rc: Resolved Haiu runtime config.
    :return: Direct Haiu run trace.
    """
    started_at = _utc_now()
    started_perf = time.perf_counter()
    empty_prompts = PromptBundle(system="", user="")
    stage1_prompts = empty_prompts
    stage2_prompts = empty_prompts
    retrieval: RetrievalTrace | None = None
    prompt_construction_seconds = 0.0
    client: LLMClient | None = None
    stage1_plan = ""
    ttl_output = ""
    stage1_duration = 0.0
    stage2_duration = 0.0
    stage1_response: LLMCallMeta | None = None
    stage2_response: LLMCallMeta | None = None
    stage1_budget: GenerationBudget | None = None
    stage2_budget: GenerationBudget | None = None
    requested_max_tokens = config.max_tokens
    context_window_tokens: int | None = None
    try:
        retrieval = retrieve_regest_context(regest=regest, rc=rc)
        prompt_started = time.perf_counter()
        stage1_prompts = build_stage1_prompts(
            regest=regest,
            historian_input=config.historian_input,
            annotation_guidelines=config.annotation_guidelines,
            retrieved_turtle=retrieval.turtle,
            allow_text_interpretation=config.allow_text_interpretation,
        )
        stage2_prompts = build_stage2_prompts(
            regest=regest,
            historian_input=config.historian_input,
            allow_text_interpretation=config.allow_text_interpretation,
        )
        prompt_construction_seconds = time.perf_counter() - prompt_started
        client = LLMClient(
            cfg=rc.client,
            model=config.model,
            system_prompt=stage1_prompts.system,
        )
        stage1_max_tokens = config.max_tokens
        if config.max_tokens is not None:
            spec = llm_spec(config.model)
            context_window_tokens = spec.context_token_limit
            if spec.context_token_limit is None:
                raise ValueError(
                    f"Model '{config.model}' has no configured context window."
                )
            resolved_stage1_budget = resolve_generation_budget(
                [
                    {"role": "system", "content": stage1_prompts.system},
                    {"role": "user", "content": stage1_prompts.user},
                ],
                model=config.model,
                requested_max_output_tokens=config.max_tokens,
                context_window_tokens=spec.context_token_limit,
                safety_margin_tokens=config.output_safety_margin_tokens,
                require_exact_prompt_tokens=config.require_exact_prompt_tokens,
            )
            stage1_budget = resolved_stage1_budget
            if resolved_stage1_budget.effective_max_output_tokens <= 0:
                raise ValueError(
                    "Stage 1 prompt and safety margin exhaust the model context."
                )
            stage1_max_tokens = (
                resolved_stage1_budget.effective_max_output_tokens
            )
        stage1_started = time.perf_counter()
        stage1_plan, stage1_response = client.prompt(
            user_input=stage1_prompts.user,
            print_chat=False,
            ignore_history=True,
            max_tokens=stage1_max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
            min_p=config.min_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
        )
        stage1_duration = time.perf_counter() - stage1_started
        if stage1_budget is not None:
            completed_stage1_budget = stage1_budget.with_provider_result(
                provider_prompt_tokens=stage1_response.metrics.prompt_tokens,
                finish_reason=stage1_response.metrics.finish_reason,
            )
            stage1_budget = completed_stage1_budget
            if completed_stage1_budget.output_truncated:
                raise RuntimeError(
                    "Stage 1 reached the provider output length limit; "
                    "Stage 2 was not attempted."
                )
        if (
            config.require_finish_reason
            and stage1_response.metrics.finish_reason is None
        ):
            raise RuntimeError(
                "Stage 1 provider response did not include finish_reason."
            )

        client.system_prompt = stage2_prompts.system
        stage2_max_tokens = config.max_tokens
        if config.max_tokens is not None:
            assert context_window_tokens is not None
            resolved_stage2_budget = resolve_generation_budget(
                [
                    {"role": "system", "content": stage2_prompts.system},
                    {"role": "user", "content": stage1_prompts.user},
                    {"role": "assistant", "content": stage1_plan},
                    {"role": "user", "content": stage2_prompts.user},
                ],
                model=config.model,
                requested_max_output_tokens=config.max_tokens,
                context_window_tokens=context_window_tokens,
                safety_margin_tokens=config.output_safety_margin_tokens,
                require_exact_prompt_tokens=config.require_exact_prompt_tokens,
            )
            stage2_budget = resolved_stage2_budget
            if resolved_stage2_budget.effective_max_output_tokens <= 0:
                raise ValueError(
                    "Stage 2 prompt and safety margin exhaust the model context."
                )
            stage2_max_tokens = (
                resolved_stage2_budget.effective_max_output_tokens
            )
        stage2_started = time.perf_counter()
        ttl_output, stage2_response = client.prompt(
            user_input=stage2_prompts.user,
            print_chat=False,
            ignore_history=False,
            max_tokens=stage2_max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
            min_p=config.min_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
        )
        stage2_duration = time.perf_counter() - stage2_started
        if stage2_budget is not None:
            completed_stage2_budget = stage2_budget.with_provider_result(
                provider_prompt_tokens=stage2_response.metrics.prompt_tokens,
                finish_reason=stage2_response.metrics.finish_reason,
            )
            stage2_budget = completed_stage2_budget
            if completed_stage2_budget.output_truncated:
                raise RuntimeError(
                    "Stage 2 reached the provider output length limit; "
                    "the Turtle response is incomplete."
                )
        if (
            config.require_finish_reason
            and stage2_response.metrics.finish_reason is None
        ):
            raise RuntimeError(
                "Stage 2 provider response did not include finish_reason."
            )

        tbox, abox, split_warning = split_turtle_sections(ttl_output)
        finished_at = _utc_now()
        duration = time.perf_counter() - started_perf
        return DirectRunTrace(
            regest_id=regest.regest_id,
            success=True,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            model=config.model,
            allow_text_interpretation=config.allow_text_interpretation,
            stage1=DirectStageTrace(
                prompts=stage1_prompts,
                output=stage1_plan,
                duration_seconds=round(stage1_duration, 3),
                response=stage1_response,
                generation_budget=stage1_budget,
                attempted=stage1_response is not None,
            ),
            stage2=DirectStageTrace(
                prompts=stage2_prompts,
                output=ttl_output,
                duration_seconds=round(stage2_duration, 3),
                response=stage2_response,
                generation_budget=stage2_budget,
                attempted=stage2_response is not None,
            ),
            tbox=tbox,
            abox=abox,
            parse_warning=split_warning,
            retrieved_turtle=retrieval.turtle,
            retrieval_snapshot=retrieval.snapshot,
            retrieval_query=retrieval.query,
            retrieval_duration_seconds=retrieval.duration_seconds,
            prompt_construction_seconds=round(prompt_construction_seconds, 3),
            requested_max_output_tokens=requested_max_tokens,
            context_window_tokens=context_window_tokens,
            output_safety_margin_tokens=config.output_safety_margin_tokens,
        )
    except Exception as exc:
        duration = time.perf_counter() - started_perf
        return DirectRunTrace(
            regest_id=regest.regest_id,
            success=False,
            started_at=started_at,
            finished_at=_utc_now(),
            duration_seconds=round(duration, 3),
            model=config.model,
            allow_text_interpretation=config.allow_text_interpretation,
            stage1=DirectStageTrace(
                prompts=stage1_prompts,
                output=stage1_plan,
                duration_seconds=round(stage1_duration, 3),
                response=stage1_response,
                generation_budget=stage1_budget,
                attempted=stage1_response is not None,
            ),
            stage2=DirectStageTrace(
                prompts=stage2_prompts,
                output=ttl_output,
                duration_seconds=round(stage2_duration, 3),
                response=stage2_response,
                generation_budget=stage2_budget,
                attempted=stage2_response is not None,
            ),
            error_message=f"{type(exc).__name__}: {exc}",
            retrieved_turtle=retrieval.turtle if retrieval else "",
            retrieval_snapshot=retrieval.snapshot if retrieval else None,
            retrieval_query=retrieval.query if retrieval else "",
            retrieval_duration_seconds=(
                retrieval.duration_seconds if retrieval else 0.0
            ),
            prompt_construction_seconds=round(prompt_construction_seconds, 3),
            requested_max_output_tokens=requested_max_tokens,
            context_window_tokens=context_window_tokens,
            output_safety_margin_tokens=config.output_safety_margin_tokens,
        )
    finally:
        if client is not None:
            client.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
