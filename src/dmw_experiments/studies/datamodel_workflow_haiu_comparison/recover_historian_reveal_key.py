#!/usr/bin/env python3
"""Recover a lost historian-review reveal key from an equivalent masked review."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.export_results_workbook import (
    HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER,
    HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER,
    HISTORIAN_REVIEW_HEADERS,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.quality_grade_inputs import (
    load_json_object,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.quality_grade_analysis import (
    CONDITION_ORDER,
)

REVIEW_ID_COLUMN = "review_id"
REVIEW_MANUAL_COLUMNS = frozenset(
    {
        REVIEW_ID_COLUMN,
        "grade_1_best_6_worst",
        "historian_verdict_and_notes",
        HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER,
        HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER,
    }
)
REVIEW_FINGERPRINT_COLUMNS = tuple(
    column
    for column in HISTORIAN_REVIEW_HEADERS
    if column not in REVIEW_MANUAL_COLUMNS
)
MERGED_REVIEW_COLUMNS = ("regest_id", "regest_text")


@dataclass(frozen=True, slots=True)
class RevealKeyRecovery:
    """Keep the recovered condition mapping and its validated row count.

    :param reveal_key: Provider-scoped hidden mappings keyed by evaluation
        review ID.
    :param recovered_rows: Number of evaluation rows matched exactly once.
    """

    reveal_key: dict[str, dict[str, dict[str, Any]]]
    recovered_rows: int


def recover_reveal_key(
    *,
    evaluated_workbook: Path,
    reference_workbook: Path,
    reference_reveal_key: Path,
) -> RevealKeyRecovery:
    """Rebuild one lost key by matching immutable rendered model content.

    The evaluation workbook must retain its unedited model-content columns.
    Grade, notes, and false-assignment fields are intentionally excluded so
    normal historian review work cannot affect a match. A reference workbook
    and its reveal key must originate from the same experiment output.

    :param evaluated_workbook: Completed masked review with the lost key.
    :param reference_workbook: Equivalent masked review that still has a key.
    :param reference_reveal_key: Valid key for ``reference_workbook``.
    :return: Exact provider/review-ID mapping for ``evaluated_workbook``.
    :raises ValueError: If a workbook lacks required columns, a reference key
        does not agree with its visible row, or a model fingerprint is missing
        or ambiguous.
    """
    reference_key = load_json_object(reference_reveal_key)
    evaluated_sheets = pd.read_excel(evaluated_workbook, sheet_name=None)
    reference_sheets = pd.read_excel(reference_workbook, sheet_name=None)
    return _recover_reveal_key_from_sheets(
        evaluated_sheets=evaluated_sheets,
        reference_sheets=reference_sheets,
        reference_key=reference_key,
    )


def _recover_reveal_key_from_sheets(
    *,
    evaluated_sheets: Mapping[str, pd.DataFrame],
    reference_sheets: Mapping[str, pd.DataFrame],
    reference_key: Mapping[str, Any],
) -> RevealKeyRecovery:
    """Match normalized reviewer rows to one trusted provider-key mapping.

    This in-memory boundary allows tests to exercise recovery without creating
    Excel files. The output format remains identical to a normal reveal key.

    :param evaluated_sheets: Provider worksheets from the completed review.
    :param reference_sheets: Equivalent provider worksheets with a known key.
    :param reference_key: Provider-scoped known condition mappings.
    :return: Recovered key and exact-match row count.
    :raises ValueError: If the source surfaces cannot support a unique match.
    """
    recovered_key: dict[str, dict[str, dict[str, Any]]] = {}
    recovered_rows = 0
    for provider, entries in reference_key.items():
        if not isinstance(entries, dict):
            raise ValueError(
                "Reference reveal key must map provider names to review IDs."
            )
        evaluated = _review_rows(
            evaluated_sheets,
            provider=provider,
            workbook_role="evaluation",
        )
        reference = _review_rows(
            reference_sheets,
            provider=provider,
            workbook_role="reference",
        )
        reference_index = _reference_fingerprint_index(
            reference,
            entries=entries,
            provider=provider,
        )
        provider_key: dict[str, dict[str, Any]] = {}
        for review in evaluated.to_dict(orient="records"):
            review_id = str(review[REVIEW_ID_COLUMN])
            fingerprint = _review_fingerprint(review)
            matches = reference_index.get(fingerprint, ())
            if len(matches) != 1:
                issue = "missing" if not matches else "ambiguous"
                raise ValueError(
                    "Evaluation review row has a "
                    f"{issue} reference fingerprint: {provider}/{review_id}."
                )
            provider_key[review_id] = matches[0]
            recovered_rows += 1
        recovered_key[provider] = provider_key
    return RevealKeyRecovery(
        reveal_key=recovered_key,
        recovered_rows=recovered_rows,
    )


def _review_rows(
    sheets: Mapping[str, pd.DataFrame],
    *,
    provider: str,
    workbook_role: str,
) -> pd.DataFrame:
    """Validate and normalize one provider worksheet for fingerprinting.

    Merged regest cells become blanks when Excel is read as a table. Forward
    filling only the documented merged columns restores their visible value
    for every model row without changing any resource-list content.

    :param sheets: Workbook worksheets keyed by title.
    :param provider: Required provider worksheet name.
    :param workbook_role: Reader-facing source name used in diagnostics.
    :return: Non-empty review rows with normalized merged values.
    :raises ValueError: If the worksheet or required model columns are absent.
    """
    if provider not in sheets:
        raise ValueError(
            f"{workbook_role.capitalize()} workbook is missing provider sheet: "
            f"{provider}."
        )
    rows = sheets[provider].copy()
    required_columns = set(HISTORIAN_REVIEW_HEADERS)
    missing_columns = sorted(required_columns.difference(rows.columns))
    if missing_columns:
        raise ValueError(
            f"{workbook_role.capitalize()} workbook {provider!r} is missing "
            f"review columns: {', '.join(missing_columns)}"
        )
    rows = rows.loc[rows[REVIEW_ID_COLUMN].notna()].copy()
    for column in MERGED_REVIEW_COLUMNS:
        rows[column] = rows[column].ffill()
    return rows


def _reference_fingerprint_index(
    reference_rows: pd.DataFrame,
    *,
    entries: Mapping[str, Any],
    provider: str,
) -> dict[tuple[str | None, ...], list[dict[str, Any]]]:
    """Index trusted masked rows after validating their visible regest IDs.

    :param reference_rows: Normalized reference provider rows.
    :param entries: Trusted key entries for the same provider.
    :param provider: Provider name used in integrity-error messages.
    :return: Content fingerprint mapped to one or more trusted key entries.
    :raises ValueError: If a trusted mapping is absent or disagrees with the
        visible reference regest identifier.
    """
    index: dict[tuple[str | None, ...], list[dict[str, Any]]] = {}
    for review in reference_rows.to_dict(orient="records"):
        review_id = str(review[REVIEW_ID_COLUMN])
        hidden = entries.get(review_id)
        if not isinstance(hidden, dict):
            raise ValueError(
                "Reference reveal key has no entry for visible review row: "
                f"{provider}/{review_id}."
            )
        visible_regest_id = _normalize_fingerprint_value(review["regest_id"])
        hidden_regest_id = _normalize_fingerprint_value(hidden.get("regest_id"))
        condition = str(hidden.get("condition") or "")
        if (
            not hidden_regest_id
            or visible_regest_id != hidden_regest_id
            or condition not in CONDITION_ORDER
        ):
            raise ValueError(
                "Reference reveal key disagrees with its visible review row: "
                f"{provider}/{review_id}."
            )
        fingerprint = _review_fingerprint(review)
        index.setdefault(fingerprint, []).append(dict(hidden))
    return index


def _review_fingerprint(review: Mapping[str, Any]) -> tuple[str | None, ...]:
    """Build the immutable model-content identity used to recover a mapping.

    :param review: One normalized masked review row.
    :return: Stable tuple of the visible source and resource-list values.
    """
    return tuple(
        _normalize_fingerprint_value(review[column])
        for column in REVIEW_FINGERPRINT_COLUMNS
    )


def _normalize_fingerprint_value(value: Any) -> str | None:
    """Normalize Excel scalar differences without weakening content matching.

    :param value: Cell value read from a reviewer workbook.
    :return: ``None`` for a blank cell or a canonical text representation.
    """
    if pd.isna(value):
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    return str(value).replace("\r\n", "\n")


def _parser() -> argparse.ArgumentParser:
    """Build the recovery command-line interface.

    :return: Parser for the completed review, trusted review/key, and output.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Recover a lost historian-review reveal key by exact matching "
            "against an equivalent masked review with a trusted key."
        )
    )
    parser.add_argument("evaluated_workbook", type=Path)
    parser.add_argument("reference_workbook", type=Path)
    parser.add_argument("reference_reveal_key", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only the requested recovered-key output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Recover and write a normal reveal-key JSON artifact.

    :param argv: Optional command-line arguments for tests and embedding.
    :return: Process status after writing the validated recovered key.
    :raises FileExistsError: If output exists without explicit replacement.
    """
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(
            f"Recovered reveal-key output already exists: {output}"
        )
    recovery = recover_reveal_key(
        evaluated_workbook=args.evaluated_workbook.expanduser().resolve(),
        reference_workbook=args.reference_workbook.expanduser().resolve(),
        reference_reveal_key=args.reference_reveal_key.expanduser().resolve(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(recovery.reveal_key, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Recovered review rows: {recovery.recovered_rows}")
    print(f"Recovered reveal key: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
