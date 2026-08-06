"""Data containers for the direct Haiu ontologizer mirror."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from haiu.clients.llm.generation_budget import GenerationBudget
from haiu.clients.llm.llm_metrics import LLMCallMeta


@dataclass(frozen=True, slots=True)
class RegestText:
    """Raw regest text used by the direct LLM baseline.

    :param regest_id: Datamodel regest identifier.
    :param header: Header lemma text.
    :param subentries: Ordered subentry texts.
    """

    regest_id: str
    header: str
    subentries: tuple[str, ...] = ()

    def full_text(self) -> str:
        """:return: Header and subentries joined in prompt order."""
        return "\n".join([self.header, *self.subentries]).strip()

    def prompt_payload(self) -> dict[str, Any]:
        """Return the prompt-builder payload shape used by OPA-like prompts.

        :return: Dictionary keyed by regest id with header and subentry records.
        """
        return {
            self.regest_id: {
                "header": {"text": self.header, "entities": []},
                "subentries": [
                    {"text": subentry, "entities": []}
                    for subentry in self.subentries
                ],
            }
        }


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """System and user prompt pair for one LLM call.

    :param system: System-level instruction text.
    :param user: User-message prompt text.
    """

    system: str
    user: str


@dataclass(frozen=True, slots=True)
class DirectStageTrace:
    """Captured state for one direct Haiu LLM call.

    :param prompts: System and user prompts sent to the model.
    :param output: Model text returned for the stage.
    :param duration_seconds: Stage request duration in seconds.
    :param response: Normalized Haiu response metadata.
    :param generation_budget: Predictive and provider-completed output budget.
    :param attempted: Whether the provider request was attempted.
    """

    prompts: PromptBundle
    output: str = ""
    duration_seconds: float = 0.0
    response: LLMCallMeta | None = None
    generation_budget: GenerationBudget | None = None
    attempted: bool = False


@dataclass(frozen=True, slots=True)
class DirectRunTrace:
    """Captured direct Haiu ontologizer run before experiment normalization.

    :param regest_id: Datamodel regest identifier.
    :param success: Whether both stages completed.
    :param started_at: ISO timestamp for run start.
    :param finished_at: ISO timestamp for run completion.
    :param duration_seconds: Total run duration in seconds.
    :param model: Haiu LLM model name.
    :param allow_text_interpretation: Whether implicit text facts were allowed.
    :param stage1: Planner stage trace.
    :param stage2: Turtle stage trace.
    :param tbox: Turtle TBox section when markers were found.
    :param abox: Turtle ABox section or full output fallback.
    :param parse_warning: Optional Turtle splitting warning.
    :param error_message: Optional exception summary.
    :param retrieved_turtle: Exact Haiu context supplied to Stage 1.
    :param retrieval_snapshot: Native portable retrieval graph and metadata.
    :param retrieval_query: Raw query supplied to standalone Haiu retrieval.
    :param retrieval_duration_seconds: Observed retrieval wall-clock duration.
    :param prompt_construction_seconds: Prompt-rendering wall-clock duration.
    :param requested_max_output_tokens: Configured completion ceiling.
    :param context_window_tokens: Model context window used for prediction.
    :param output_safety_margin_tokens: Reserved context allowance.
    """

    regest_id: str
    success: bool
    started_at: str
    finished_at: str
    duration_seconds: float
    model: str
    allow_text_interpretation: bool
    stage1: DirectStageTrace
    stage2: DirectStageTrace
    tbox: str = ""
    abox: str = ""
    parse_warning: str | None = None
    error_message: str | None = None
    retrieved_turtle: str = ""
    retrieval_snapshot: dict[str, Any] | None = None
    retrieval_query: str = ""
    retrieval_duration_seconds: float = 0.0
    prompt_construction_seconds: float = 0.0
    requested_max_output_tokens: int | None = None
    context_window_tokens: int | None = None
    output_safety_margin_tokens: int = 4_096
