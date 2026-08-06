"""Resolve repository-owned paths for the DMW--Haiu comparison study."""

from __future__ import annotations

from pathlib import Path

STUDY_ID = "haiu_comparison"
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
STUDY_ROOT = REPOSITORY_ROOT / "studies" / STUDY_ID
INPUT_ROOT = STUDY_ROOT / "inputs"
SPEC_ROOT = STUDY_ROOT / "specs"
LOCK_ROOT = STUDY_ROOT / "locks"


def require_study_root() -> Path:
    """Return the tracked study directory after validating the checkout.

    :return: Directory containing the study inputs and run specifications.
    :raises RuntimeError: If the installed package is not attached to its
        research checkout.
    """
    if not STUDY_ROOT.is_dir():
        raise RuntimeError(
            "The DMW--Haiu study requires its repository checkout. "
            f"Missing study directory: {STUDY_ROOT}"
        )
    return STUDY_ROOT
