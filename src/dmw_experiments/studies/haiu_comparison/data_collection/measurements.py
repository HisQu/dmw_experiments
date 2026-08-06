"""Token, timing, and summary helpers for experiment artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from collections import defaultdict
from statistics import mean, median
from typing import Any

import haiu
import haiu.utils as ut
from haiu.clients.llm.llm_metrics import LLMCallMeta

from dmw_experiments.studies.haiu_comparison.model.results import (
    TokenMeasurement,
    provider_prompt_token_measurement,
)
from dmw_experiments.studies.haiu_comparison.model.traces import (
    PromptBundle,
)

from dmw_experiments.studies.haiu_comparison.model.ontology import (
    TURTLE_PREFIXES,
)


def estimate_tokens(text: str, *, model: str) -> TokenMeasurement:
    """Count text tokens with Haiu's tokenizer facade.

    :param text: Text to count.
    :param model: Tokenizer model name.
    :return: Estimated token measurement.
    """
    if not text:
        return TokenMeasurement(tokens=0, source="estimated")
    try:
        return TokenMeasurement(
            tokens=int(ut.count_tokens(text=text, model=model)),
            source="estimated",
        )
    except Exception:
        return TokenMeasurement(
            tokens=max(1, (len(text) + 3) // 4), source="estimated"
        )


def turtle_generation_input_tokens(
    *,
    stage1_user: str,
    stage1_output: str,
    stage2_system: str,
    stage2_user: str,
    stage2_provider_prompt_tokens: object,
    model: str,
) -> TokenMeasurement:
    """Measure the complete input context supplied before Turtle generation.

    Stage 2 replaces the planning system prompt while retaining the original
    user input and generated plan. The final Turtle response is intentionally
    excluded because it is an output metric.

    :param stage1_user: User prompt retained from the planning call.
    :param stage1_output: Assistant plan retained for the Turtle call.
    :param stage2_system: System prompt used for Turtle generation.
    :param stage2_user: Turtle-generation instruction.
    :param stage2_provider_prompt_tokens: Provider usage for the full Stage-2
        input when available.
    :param model: Tokenizer model for the local fallback.
    :return: Exact Stage-2 provider input measurement, or a local full-context
        estimate when provider usage is unavailable.
    """
    provider_measurement = provider_prompt_token_measurement(
        stage2_provider_prompt_tokens
    )
    if provider_measurement is not None:
        return provider_measurement
    return estimate_tokens(
        "\n\n".join((stage2_system, stage1_user, stage1_output, stage2_user)),
        model=model,
    )


def prompt_token_fields(
    prompts: PromptBundle | dict[str, str], *, model: str, prefix: str
) -> dict[str, int | str]:
    """Return flattened prompt token metrics.

    :param prompts: Prompt bundle or mapping with ``system`` and ``user`` keys.
    :param model: Tokenizer model name.
    :param prefix: Metric field prefix.
    :return: Flattened token metrics.
    """
    if isinstance(prompts, PromptBundle):
        system = prompts.system
        user = prompts.user
    else:
        system = str(prompts.get("system") or "")
        user = str(prompts.get("user") or "")
    system_tokens = estimate_tokens(system, model=model)
    user_tokens = estimate_tokens(user, model=model)
    total_tokens = TokenMeasurement(
        tokens=system_tokens.tokens + user_tokens.tokens,
        source="estimated",
    )
    return {
        **system_tokens.as_dict(f"{prefix}_system_prompt"),
        **user_tokens.as_dict(f"{prefix}_user_prompt"),
        **total_tokens.as_dict(f"{prefix}_prompt"),
        f"{prefix}_system_prompt_chars": len(system),
        f"{prefix}_user_prompt_chars": len(user),
    }


def provider_usage_fields(
    response: LLMCallMeta | None, *, prefix: str
) -> dict[str, int | str | None]:
    """Extract provider usage fields from Haiu response metadata.

    :param response: Normalized Haiu response metadata.
    :param prefix: Metric field prefix.
    :return: Flattened provider usage fields.
    """
    if response is None:
        return {
            f"{prefix}_effective_model": None,
            f"{prefix}_provider_prompt_tokens": None,
            f"{prefix}_provider_completion_tokens": None,
            f"{prefix}_provider_total_tokens": None,
            f"{prefix}_provider_completion_tokens_source": None,
            f"{prefix}_provider_reasoning_tokens": None,
            f"{prefix}_provider_reasoning_tokens_source": None,
        }
    metrics = response.metrics
    return {
        f"{prefix}_effective_model": response.model,
        f"{prefix}_provider_prompt_tokens": metrics.prompt_tokens,
        f"{prefix}_provider_completion_tokens": metrics.completion_tokens,
        f"{prefix}_provider_total_tokens": metrics.total_tokens,
        f"{prefix}_provider_completion_tokens_source": (
            metrics.completion_tokens_source
        ),
        f"{prefix}_provider_reasoning_tokens": metrics.reasoning_tokens,
        f"{prefix}_provider_reasoning_tokens_source": (
            metrics.reasoning_tokens_source
        ),
    }


def output_token_fields(
    text: str, *, model: str, prefix: str
) -> dict[str, int | str]:
    """Return flattened output size metrics.

    :param text: Output text.
    :param model: Tokenizer model name.
    :param prefix: Metric field prefix.
    :return: Token and character metrics.
    """
    tokens = estimate_tokens(text, model=model)
    return {
        **tokens.as_dict(prefix),
        f"{prefix}_chars": len(text),
    }


def turtle_syntax_fields(
    turtle_text: str,
    *,
    prefix: str = "turtle",
) -> dict[str, bool | int | str | None]:
    """Parse generated Turtle and return syntax diagnostics.

    DMW stores TBox and ABox without the prompt's prefix declarations. The
    shared prompt prefix block is therefore prepended when the output has no
    declarations of its own.

    :param turtle_text: Generated Turtle document or joined TBox/ABox fragments.
    :param prefix: Metric field prefix.
    :return: Syntax status, parsed triple count, and compact parser error.
    """
    cleaned = turtle_text.strip()
    if not cleaned:
        return {
            f"{prefix}_syntax_valid": None,
            f"{prefix}_triple_count": None,
            f"{prefix}_syntax_error": None,
        }
    parse_input = (
        cleaned
        if "@prefix" in cleaned
        else "\n\n".join((TURTLE_PREFIXES, cleaned))
    )
    try:
        graph = haiu.parse_rdf_data(parse_input, format="turtle", log=False)
    except RuntimeError as exc:
        return {
            f"{prefix}_syntax_valid": False,
            f"{prefix}_triple_count": None,
            f"{prefix}_syntax_error": " ".join(str(exc).split()),
        }
    return {
        f"{prefix}_syntax_valid": True,
        f"{prefix}_triple_count": len(graph),
        f"{prefix}_syntax_error": None,
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize normalized rows by condition.

    :param rows: Normalized experiment records.
    :return: JSON-friendly summary.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("condition") or "")].append(row)

    summary: dict[str, Any] = {}
    for condition, condition_rows in grouped.items():
        successful_rows = [
            row for row in condition_rows if bool(row.get("success"))
        ]
        failed_rows = [
            row for row in condition_rows if not bool(row.get("success"))
        ]
        durations = [
            float(row["duration_seconds"])
            for row in successful_rows
            if isinstance(row.get("duration_seconds"), int | float)
        ]
        failure_durations = [
            float(row["duration_seconds"])
            for row in failed_rows
            if isinstance(row.get("duration_seconds"), int | float)
        ]
        attempt_durations = [
            float(row["attempt_duration_seconds"])
            for row in successful_rows
            if isinstance(
                row.get("attempt_duration_seconds"),
                int | float,
            )
        ]
        total_attempt_durations = [
            float(row["total_attempt_duration_seconds"])
            for row in successful_rows
            if isinstance(
                row.get("total_attempt_duration_seconds"), int | float
            )
        ]
        total_elapsed_durations = [
            float(row["total_elapsed_seconds"])
            for row in successful_rows
            if isinstance(row.get("total_elapsed_seconds"), int | float)
        ]
        failure_total_elapsed_durations = [
            float(row["total_elapsed_seconds"])
            for row in failed_rows
            if isinstance(row.get("total_elapsed_seconds"), int | float)
        ]
        complete_prompt_tokens = [
            int(row["prompt_tokens"])
            for row in successful_rows
            if isinstance(row.get("prompt_tokens"), int)
            and row.get("prompt_tokens_complete") is True
        ]
        partial_prompt_tokens = [
            int(row["prompt_tokens"])
            for row in successful_rows
            if isinstance(row.get("prompt_tokens"), int)
            and row.get("prompt_tokens_complete") is False
        ]
        output_tokens = [
            int(row["output_tokens"])
            for row in successful_rows
            if isinstance(row.get("output_tokens"), int)
        ]
        reported_ontology_provider_tokens = [
            int(row["ontology_provider_total_tokens"])
            for row in successful_rows
            if row.get("ontology_provider_usage_complete") is True
            and isinstance(row.get("ontology_provider_total_tokens"), int)
        ]
        successes = [bool(row.get("success")) for row in condition_rows]
        syntax_results = [
            value
            for row in successful_rows
            if isinstance((value := row.get("turtle_syntax_valid")), bool)
        ]
        summary[condition] = {
            "count": len(condition_rows),
            "success_count": sum(1 for value in successes if value),
            "failure_count": sum(1 for value in successes if not value),
            "duration_seconds": _number_summary(durations),
            "duration_measure": (
                "cumulative condition-attempt time excluding runner backoff"
            ),
            "attempt_duration_seconds": _number_summary(attempt_durations),
            "failure_duration_seconds": _number_summary(failure_durations),
            "total_attempt_duration_seconds": _number_summary(
                total_attempt_durations
            ),
            "total_elapsed_seconds": _number_summary(total_elapsed_durations),
            "failure_total_elapsed_seconds": _number_summary(
                failure_total_elapsed_durations
            ),
            "complete_prompt_tokens": _number_summary(complete_prompt_tokens),
            "partial_prompt_tokens": _number_summary(partial_prompt_tokens),
            "output_tokens": _number_summary(output_tokens),
            "reported_ontology_provider_total_tokens": _number_summary(
                reported_ontology_provider_tokens
            ),
            "turtle_syntax": {
                "assessed_count": len(syntax_results),
                "valid_count": sum(1 for value in syntax_results if value),
                "invalid_count": sum(
                    1 for value in syntax_results if not value
                ),
            },
        }
    return summary


def _number_summary(
    values: Sequence[int | float],
) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
        }
    return {
        "count": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }
