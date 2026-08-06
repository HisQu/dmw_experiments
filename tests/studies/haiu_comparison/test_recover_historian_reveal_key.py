import pandas as pd
import pytest

from dmw_experiments.studies.haiu_comparison.export_results_workbook import (
    HISTORIAN_REVIEW_HEADERS,
)
from dmw_experiments.studies.haiu_comparison.recover_historian_reveal_key import (
    _recover_reveal_key_from_sheets,
)


def _review_sheet(*rows: dict[str, object]) -> pd.DataFrame:
    """Build one minimal provider worksheet with every review column."""
    defaults = {
        "review_id": "",
        "regest_id": "",
        "regest_text": "Header\nSublemma",
        "grade_1_best_6_worst": "",
        "historian_verdict_and_notes": "",
        "false_assertions": "",
        "false_interpretations": "",
        "classes": "Event",
        "object_properties": "has participant",
        "individuals": "Alice",
        "relationships": "• Alice — participates in → Event",
        "datatype_properties": "",
        "annotation_properties": "",
        "rdf_properties": "",
        "other_resources": "",
    }
    return pd.DataFrame(
        [{**defaults, **row} for row in rows],
        columns=HISTORIAN_REVIEW_HEADERS,
    )


def test_recover_reveal_key_matches_only_immutable_review_content() -> None:
    """Recover evaluation IDs while ignoring manually entered review fields."""
    evaluated = _review_sheet(
        {
            "review_id": "R0001",
            "regest_id": "1001",
            "grade_1_best_6_worst": 5,
            "historian_verdict_and_notes": "Manual assessment.",
            "false_assertions": 3,
            "false_interpretations": "2",
        }
    )
    reference = _review_sheet(
        {
            "review_id": "R0099",
            "regest_id": "1001",
        }
    )

    recovery = _recover_reveal_key_from_sheets(
        evaluated_sheets={"AcademicCloud": evaluated},
        reference_sheets={"AcademicCloud": reference},
        reference_key={
            "AcademicCloud": {
                "R0099": {
                    "regest_id": "1001",
                    "condition": "workflow_rag",
                    "raw_ttl_artifact_path": "raw_ttl/workflow_rag/1001.ttl",
                }
            }
        },
    )

    assert recovery.recovered_rows == 1
    assert recovery.reveal_key == {
        "AcademicCloud": {
            "R0001": {
                "regest_id": "1001",
                "condition": "workflow_rag",
                "raw_ttl_artifact_path": "raw_ttl/workflow_rag/1001.ttl",
            }
        }
    }


def test_recover_reveal_key_rejects_ambiguous_content_match() -> None:
    """Never assign a condition when two trusted models look identical."""
    evaluated = _review_sheet({"review_id": "R0001", "regest_id": "1001"})
    reference = _review_sheet(
        {"review_id": "R0099", "regest_id": "1001"},
        {"review_id": "R0100", "regest_id": "1001"},
    )
    key = {
        "AcademicCloud": {
            "R0099": {
                "regest_id": "1001",
                "condition": "workflow_rag",
            },
            "R0100": {
                "regest_id": "1001",
                "condition": "haiu_rag_ontologizer",
            },
        }
    }

    with pytest.raises(ValueError, match="ambiguous reference fingerprint"):
        _recover_reveal_key_from_sheets(
            evaluated_sheets={"AcademicCloud": evaluated},
            reference_sheets={"AcademicCloud": reference},
            reference_key=key,
        )
