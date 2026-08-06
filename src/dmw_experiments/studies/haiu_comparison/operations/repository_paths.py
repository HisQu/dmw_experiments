"""Resolve repository and run-template paths for the Haiu comparison."""

from __future__ import annotations

from pathlib import Path

STUDY_ID = "haiu_comparison"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
RUN_TEMPLATES_ROOT = REPOSITORY_ROOT / "studies_run_templates"
STUDY_TEMPLATE_ROOT = RUN_TEMPLATES_ROOT / STUDY_ID
RUN_TEMPLATE_ROOT = STUDY_TEMPLATE_ROOT / "template"
TEMPLATE_INPUT_ROOT = RUN_TEMPLATE_ROOT / "INPUTS"
FULL_RUNS_ROOT = REPOSITORY_ROOT / "studies_runs" / STUDY_ID
PROMOTED_RUNS_ROOT = FULL_RUNS_ROOT / "git_tracked"
SMOKE_RUNS_ROOT = REPOSITORY_ROOT / "studies_runs_smoketests" / STUDY_ID


def require_run_template() -> Path:
    """Return the complete tracked template after checking the checkout.

    :return: Copyable Haiu comparison run template.
    :raises RuntimeError: If package code is detached from its data checkout.
    """
    if not RUN_TEMPLATE_ROOT.is_dir():
        raise RuntimeError(
            "The Haiu comparison requires its tracked run template. Missing: "
            f"{RUN_TEMPLATE_ROOT}"
        )
    return RUN_TEMPLATE_ROOT
