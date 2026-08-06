"""Load unmasked historian-review inputs without editing review workbooks."""

from __future__ import annotations

import json
from numbers import Real
from pathlib import Path
from typing import Any, cast

import pandas as pd

import haiu.utils as ut
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.quality_grade_analysis import (
    CONDITION_ORDER,
)

QUALITY_REVIEW_GRADE_COLUMN = "grade_1_best_6_worst"
QUALITY_REVIEW_FALSE_ASSERTIONS_COLUMN = "false_assertions"
QUALITY_REVIEW_FALSE_INTERPRETATIONS_COLUMN = "false_interpretations"


def load_historian_quality_grades(
    *,
    workbook_path: Path,
    reveal_key_path: Path,
    provider_order: list[str],
) -> pd.DataFrame:
    """Unmask completed historian grades while preserving the review source.

    The review workbook deliberately hides condition identities. Its separate
    reveal key restores only provider, regest, and condition identifiers needed
    for matched statistics; historian verdict text remains unused.

    :param workbook_path: Completed historian-review workbook with grades.
    :param reveal_key_path: JSON mapping masked review IDs to conditions.
    :param provider_order: Fully qualified provider labels available in plots.
    :return: One unmasked row per populated, validated historian grade.
    :raises ValueError: If a grade cannot be safely joined to the reveal key or
        does not use the documented whole-number 1–6 scale.
    """
    reviews = _load_unmasked_historian_quality_review_rows(
        workbook_path=workbook_path,
        reveal_key_path=reveal_key_path,
        provider_order=provider_order,
        required_review_columns={"review_id", QUALITY_REVIEW_GRADE_COLUMN},
    )
    records: list[dict[str, object]] = []
    for review in reviews.to_dict(orient="records"):
        raw_grade = review[QUALITY_REVIEW_GRADE_COLUMN]
        if _is_blank_review_value(raw_grade):
            continue
        records.append(
            {
                "review_id": str(review["review_id"]),
                "provider_label": str(review["provider_label"]),
                "regest_id": str(review["regest_id"]),
                "condition": str(review["condition"]),
                "grade": _normalize_grade(
                    raw_grade,
                    review_id=review["review_id"],
                ),
            }
        )
    return ut.frame_from_records(
        records,
        columns=(
            "review_id",
            "provider_label",
            "regest_id",
            "condition",
            "grade",
        ),
    )


def load_historian_quality_error_counts(
    *,
    workbook_path: Path,
    reveal_key_path: Path,
    provider_order: list[str],
) -> pd.DataFrame:
    """Unmask optional false-assignment counts from a completed review.

    ``false_assertions`` records literal incorrect atomic class, property, or
    value assertions. ``false_interpretations`` records independent historical
    misunderstandings on the ``0``, ``1``, ``2``, ``3+`` review scale. Older
    grade-only workbooks deliberately produce an empty table so their existing
    analysis remains usable.

    :param workbook_path: Completed historian-review workbook.
    :param reveal_key_path: JSON mapping masked review IDs to conditions.
    :param provider_order: Fully qualified provider labels available in plots.
    :return: One unmasked row per review with either optional count populated.
    :raises ValueError: If a populated count does not use its documented scale
        or cannot be safely joined to the reveal key.
    """
    reviews = _load_unmasked_historian_quality_review_rows(
        workbook_path=workbook_path,
        reveal_key_path=reveal_key_path,
        provider_order=provider_order,
        required_review_columns={"review_id"},
    )
    if not {
        QUALITY_REVIEW_FALSE_ASSERTIONS_COLUMN,
        QUALITY_REVIEW_FALSE_INTERPRETATIONS_COLUMN,
    }.intersection(reviews.columns):
        return _empty_quality_error_counts()

    records: list[dict[str, object]] = []
    for review in reviews.to_dict(orient="records"):
        raw_assertions = review.get(QUALITY_REVIEW_FALSE_ASSERTIONS_COLUMN)
        raw_interpretations = review.get(
            QUALITY_REVIEW_FALSE_INTERPRETATIONS_COLUMN
        )
        if _is_blank_review_value(raw_assertions) and _is_blank_review_value(
            raw_interpretations
        ):
            continue
        _, interpretation_band = _normalize_false_interpretations(
            raw_interpretations,
            review_id=review["review_id"],
        )
        records.append(
            {
                "review_id": str(review["review_id"]),
                "provider_label": str(review["provider_label"]),
                "regest_id": str(review["regest_id"]),
                "condition": str(review["condition"]),
                "false_assertions": _normalize_false_assertions(
                    raw_assertions,
                    review_id=review["review_id"],
                ),
                "false_interpretations": interpretation_band,
            }
        )
    return ut.frame_from_records(
        records,
        columns=(
            "review_id",
            "provider_label",
            "regest_id",
            "condition",
            "false_assertions",
            "false_interpretations",
        ),
    )


def _load_unmasked_historian_quality_review_rows(
    *,
    workbook_path: Path,
    reveal_key_path: Path,
    provider_order: list[str],
    required_review_columns: set[str],
) -> pd.DataFrame:
    """Join visible review rows to their condition mapping exactly once.

    The grade and error-count loaders use the same masked review and reveal
    key. Keeping the join here prevents the two derived analyses from
    accepting different provider, regest, or condition identities.

    :param workbook_path: Completed historian-review workbook.
    :param reveal_key_path: Condition mapping keyed by masked review ID.
    :param provider_order: Fully qualified plot-provider labels.
    :param required_review_columns: Visible worksheet fields mandatory for the
        calling analysis.
    :return: Unmasked workbook rows with their original review fields.
    :raises FileNotFoundError: If the workbook does not exist.
    :raises ValueError: If sheets, fields, or reveal-key mappings are invalid.
    """
    resolved_workbook = workbook_path.expanduser().resolve()
    resolved_key = reveal_key_path.expanduser().resolve()
    if not resolved_workbook.is_file():
        raise FileNotFoundError(
            f"Historian quality workbook not found: {resolved_workbook}"
        )
    reveal_key = load_json_object(resolved_key)
    review_sheets = pd.read_excel(resolved_workbook, sheet_name=None)
    records: list[dict[str, object]] = []
    review_columns: set[str] = set()
    for review_provider, entries in reveal_key.items():
        if not isinstance(entries, dict):
            raise ValueError(
                "Historian reveal key must map provider names to review IDs."
            )
        if review_provider not in review_sheets:
            raise ValueError(
                "Historian quality workbook is missing provider sheet: "
                f"{review_provider}"
            )
        sheet = review_sheets[review_provider]
        required_columns = {"review_id", *required_review_columns}
        _require_columns(
            sheet,
            required_columns,
            workbook_path=resolved_workbook,
            sheet_name=review_provider,
        )
        provider_label = match_review_provider_label(
            review_provider,
            provider_order=provider_order,
        )
        review_columns.update(str(column) for column in sheet.columns)
        review_rows = sheet.loc[sheet["review_id"].notna()]
        for review in review_rows.to_dict(orient="records"):
            review_id = str(review["review_id"])
            hidden = entries.get(review_id)
            if not isinstance(hidden, dict):
                raise ValueError(
                    "Historian review has no reveal-key entry: "
                    f"{review_provider}/{review_id}"
                )
            regest_id = str(hidden.get("regest_id") or "")
            condition = str(hidden.get("condition") or "")
            if not regest_id or condition not in CONDITION_ORDER:
                raise ValueError(
                    "Historian reveal key has invalid condition mapping: "
                    f"{review_provider}/{review_id}"
                )
            visible_regest_id = review.get("regest_id")
            if pd.notna(visible_regest_id) and (
                normalize_review_regest_id(visible_regest_id) != regest_id
            ):
                raise ValueError(
                    "Historian review regest ID disagrees with reveal key: "
                    f"{review_provider}/{review_id}"
                )
            records.append(
                {
                    **review,
                    "review_id": review_id,
                    "provider_label": provider_label,
                    "regest_id": regest_id,
                    "condition": condition,
                }
            )
    identity_columns = (
        "review_id",
        "provider_label",
        "regest_id",
        "condition",
    )
    other_columns = tuple(
        column
        for column in sorted(review_columns)
        if column not in identity_columns
    )
    return ut.frame_from_records(
        records, columns=(*identity_columns, *other_columns)
    )


def _empty_quality_error_counts() -> pd.DataFrame:
    """Return the stable empty schema used by optional error-count plotting.

    :return: Empty rows with all columns required by error-count processing.
    """
    return ut.empty_frame(
        (
            "review_id",
            "provider_label",
            "regest_id",
            "condition",
            "false_assertions",
            "false_interpretations",
        )
    )


def load_json_object(path: Path) -> dict[str, Any]:
    """Read one mandatory JSON mapping with a precise structural error.

    :param path: JSON document expected to contain an object at its root.
    :return: Decoded mapping.
    :raises FileNotFoundError: If the declared document is absent.
    :raises ValueError: If the decoded root is not an object.
    """
    if not path.is_file():
        raise FileNotFoundError(f"JSON artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def match_review_provider_label(
    review_provider: str,
    *,
    provider_order: list[str],
) -> str:
    """Match a review-sheet provider title to one plotted provider label.

    :param review_provider: Provider title written into the review workbook.
    :param provider_order: Fully qualified provider labels from experiment data.
    :return: The unique legend label associated with the review sheet.
    :raises ValueError: If the title is ambiguous or missing from plotted data.
    """
    normalized_review = normalize_provider_name(review_provider)
    matches = [
        provider_label
        for provider_label in provider_order
        if normalized_review in normalize_provider_name(provider_label)
    ]
    if len(matches) != 1:
        raise ValueError(
            "Historian review provider could not be matched to one plotted "
            f"provider: {review_provider!r}"
        )
    return matches[0]


def normalize_provider_name(value: str) -> str:
    """Normalize one provider title for conservative display-name matching.

    :param value: Human-readable provider title or legend label.
    :return: Lowercase alphanumeric comparison key.
    """
    return "".join(
        character for character in value.lower() if character.isalnum()
    )


def normalize_review_regest_id(value: object) -> str:
    """Preserve integral Excel identifiers while comparing reveal-key rows.

    :param value: Workbook cell value for a regest identifier.
    :return: String form without Excel's artificial trailing decimal part.
    """
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    return str(value)


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    *,
    workbook_path: Path,
    sheet_name: str,
) -> None:
    """Reject a review worksheet that cannot identify and grade packets.

    :param frame: Parsed review worksheet.
    :param required: Required column names.
    :param workbook_path: Source workbook for the error message.
    :param sheet_name: Review provider worksheet identifier.
    :return: ``None`` after validation.
    """
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(
            f"{workbook_path} worksheet {sheet_name} is missing columns: "
            f"{', '.join(missing)}"
        )


def _normalize_grade(raw_grade: object, *, review_id: object) -> int:
    """Validate one ordinal reviewer grade before unmasking its condition.

    :param raw_grade: Workbook cell value.
    :param review_id: Masked review identifier for a precise error message.
    :return: Integer grade from 1 through 6.
    :raises ValueError: If the reviewer entered an invalid scale value.
    """
    try:
        grade = float(cast(float | str, raw_grade))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Historian grade must be a whole number between 1 (best) and 6 "
            f"(worst): {review_id!r} has {raw_grade!r}."
        ) from exc
    if not 1.0 <= grade <= 6.0 or not grade.is_integer():
        raise ValueError(
            "Historian grade must be a whole number between 1 (best) and 6 "
            f"(worst): {review_id!r} has {raw_grade!r}."
        )
    return int(grade)


def _normalize_false_assertions(
    raw_assertions: object,
    *,
    review_id: object,
) -> int | None:
    """Validate one optional exact count of incorrect atomic assertions.

    :param raw_assertions: Workbook cell value for ``false_assertions``.
    :param review_id: Masked review identifier for a precise error message.
    :return: Non-negative whole count, or ``None`` for an intentionally blank
        optional field.
    :raises ValueError: If a populated count is negative or non-integral.
    """
    if _is_blank_review_value(raw_assertions):
        return None
    if isinstance(raw_assertions, bool):
        raise ValueError(
            "false_assertions must be a non-negative whole number: "
            f"{review_id!r} has {raw_assertions!r}."
        )
    try:
        assertions = float(cast(float | str, raw_assertions))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "false_assertions must be a non-negative whole number: "
            f"{review_id!r} has {raw_assertions!r}."
        ) from exc
    if assertions < 0 or not assertions.is_integer():
        raise ValueError(
            "false_assertions must be a non-negative whole number: "
            f"{review_id!r} has {raw_assertions!r}."
        )
    return int(assertions)


def _normalize_false_interpretations(
    raw_interpretations: object,
    *,
    review_id: object,
) -> tuple[int | None, str | None]:
    """Validate the bounded independent-interpretation review scale.

    The ``3+`` band remains an open-ended category. Downstream plots receive
    its lower bound of three and retain the visible ``3+`` label, rather than
    pretending that every such review contains exactly three misunderstandings.

    :param raw_interpretations: Workbook cell value for
        ``false_interpretations``.
    :param review_id: Masked review identifier for a precise error message.
    :return: Numeric lower bound and display band, or two ``None`` values for
        an intentionally blank field.
    :raises ValueError: If a populated value is outside ``0``, ``1``, ``2``,
        or ``3+``.
    """
    if _is_blank_review_value(raw_interpretations):
        return None, None
    if isinstance(raw_interpretations, bool):
        raise ValueError(
            "false_interpretations must be 0, 1, 2, or 3+: "
            f"{review_id!r} has {raw_interpretations!r}."
        )
    if isinstance(raw_interpretations, str):
        value = raw_interpretations.strip()
        if value == "3+":
            return 3, value
        if value in {"0", "1", "2"}:
            return int(value), value
    elif isinstance(raw_interpretations, Real):
        value = float(raw_interpretations)
        if value.is_integer() and int(value) in {0, 1, 2}:
            return int(value), str(int(value))
    raise ValueError(
        "false_interpretations must be 0, 1, 2, or 3+: "
        f"{review_id!r} has {raw_interpretations!r}."
    )


def _is_blank_review_value(value: object) -> bool:
    """Identify a genuinely unfilled Excel review cell.

    :param value: Scalar value parsed from the review workbook.
    :return: Whether the cell is blank or whitespace-only.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))
