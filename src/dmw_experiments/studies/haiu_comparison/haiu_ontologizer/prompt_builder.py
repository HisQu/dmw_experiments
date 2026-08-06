"""Standalone prompt entry points and raw Stage-2 section parsing."""

from __future__ import annotations

from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.models import (
    PromptBundle,
    RegestText,
)
from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.opa_prompt_renderer import (
    build_stage1_prompts as _render_opa_stage1,
)
from dmw_experiments.studies.haiu_comparison.haiu_ontologizer.opa_prompt_renderer import (
    build_stage2_prompts as _render_opa_stage2,
)


def build_stage1_prompts(
    *,
    regest: RegestText,
    historian_input: str,
    annotation_guidelines: str = "",
    retrieved_turtle: str = "",
    allow_text_interpretation: bool = False,
) -> PromptBundle:
    """Build the local renderer's OPA-parity standalone planner prompt.

    :param regest: Raw source text for the standalone condition.
    :param historian_input: Shared historian ontology instruction.
    :param annotation_guidelines: Historian-curated annotation guidelines.
    :param retrieved_turtle: Exact Haiu-retrieved Turtle context.
    :param allow_text_interpretation: Whether implicit text facts may be inferred.
    :return: System and user prompt for Stage 1.
    """
    return _render_opa_stage1(
        regest=regest,
        historian_input=historian_input,
        annotation_guidelines=annotation_guidelines,
        retrieved_turtle=retrieved_turtle,
        allow_text_interpretation=allow_text_interpretation,
    )


def build_stage2_prompts(
    *,
    regest: RegestText,
    historian_input: str,
    allow_text_interpretation: bool = False,
) -> PromptBundle:
    """Build same-thread OPA-parity Turtle-coder instructions.

    ``historian_input`` is intentionally not repeated: Stage 2 remains in the
    Stage-1 thread, like OPA's default Turtle-coder prompt construction.

    :param regest: Raw source identifier used as the Stage-2 context anchor.
    :param historian_input: Retained API argument; context remains in the thread.
    :param allow_text_interpretation: Whether implicit text facts may be inferred.
    :return: System and user prompt for Stage 2.
    """
    del historian_input
    return _render_opa_stage2(
        regest=regest,
        allow_text_interpretation=allow_text_interpretation,
    )


def split_turtle_sections(ttl_output: str) -> tuple[str, str, str | None]:
    """Split a direct raw Stage-2 response into TBox and ABox sections.

    :param ttl_output: Unmodified Stage-2 model response.
    :return: TBox text, ABox text, and an optional parsing warning.
    """
    cleaned_output = _strip_outer_turtle_fence(ttl_output)
    lines = cleaned_output.splitlines()
    tbox_index = _marker_index(lines, "# --- TBOX ---")
    abox_index = _marker_index(lines, "# --- ABOX ---")
    if tbox_index is None or abox_index is None or abox_index <= tbox_index:
        return "", cleaned_output, "Could not split TTL into TBOX/ABOX markers."
    tbox = "\n".join(lines[:abox_index]).strip()
    abox = "\n".join(lines[abox_index:]).strip()
    return tbox, abox, None


def _strip_outer_turtle_fence(ttl: str) -> str:
    """Remove one optional Markdown fence while retaining all other raw text.

    :param ttl: Raw model response.
    :return: Response without one recognized outer code fence.
    """
    lines = ttl.strip().splitlines()
    opening_fences = {"```", "```ttl", "```turtle"}
    if (
        len(lines) >= 2
        and lines[0].strip().lower() in opening_fences
        and lines[-1].strip() == "```"
    ):
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def _marker_index(lines: list[str], marker: str) -> int | None:
    """Find one case-insensitive Turtle section-marker line.

    :param lines: Candidate response lines.
    :param marker: Required section-marker string.
    :return: Marker line index, or ``None`` when absent.
    """
    normalized_marker = marker.strip().lower()
    for index, line in enumerate(lines):
        if line.strip().lower() == normalized_marker:
            return index
    return None
