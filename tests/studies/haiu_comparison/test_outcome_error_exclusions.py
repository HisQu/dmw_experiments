"""Tests for the narrow LM Studio outcome-error exclusion decision."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dmw_experiments.studies.haiu_comparison.analysis.plots.results import (
    _is_configuration_invalid_outcome_error,
    _local_runtime_recovery_cells,
)


def test_excludes_only_invalid_lmstudio_configuration_attempts() -> None:
    """Keep valid outputs and capacity outcomes outside the filter."""
    common = {
        "provider_label": "LM Studio Q6",
        "local_runtime_recovery": '{"amendment_id": "lmstudio-runtime"}',
        "success": False,
        "turtle_syntax_valid": None,
        "output_truncated": False,
        "error_message": "failed to get initial ontology modeling response",
    }

    assert _is_configuration_invalid_outcome_error(pd.Series(common))
    assert not _is_configuration_invalid_outcome_error(
        pd.Series({**common, "output_truncated": True})
    )
    assert not _is_configuration_invalid_outcome_error(
        pd.Series({**common, "success": True, "turtle_syntax_valid": True})
    )
    assert not _is_configuration_invalid_outcome_error(
        pd.Series({**common, "provider_label": "AcademicCloud FP8"})
    )
    assert not _is_configuration_invalid_outcome_error(
        pd.Series({**common, "local_runtime_recovery": None})
    )
    assert _is_configuration_invalid_outcome_error(
        pd.Series(
            {
                **common,
                "local_runtime_recovery": None,
                "_outcome_error_excluded": True,
            }
        )
    )


def test_reads_local_runtime_cells_from_archived_amendment(
    tmp_path: Path,
) -> None:
    """Use archived amendment cells when a replay never wrote a new result."""
    workbook_path = tmp_path / "run" / "analysis" / "overview.xlsx"
    amendment_path = (
        tmp_path / "run" / "summaries" / "amendments" / "runtime.json"
    )
    archive_path = (
        tmp_path
        / "run"
        / "superseded"
        / "runtime"
        / "raw"
        / "workflow_rag"
        / "10400277.json"
    )
    amendment_path.parent.mkdir(parents=True)
    archive_path.parent.mkdir(parents=True)
    amendment_path.write_text(
        '{"amendment_id": "runtime", "kind": "local_runtime_recovery"}',
        encoding="utf-8",
    )
    archive_path.write_text("{}", encoding="utf-8")

    assert _local_runtime_recovery_cells(workbook_path) == {
        ("workflow_rag", "10400277")
    }
