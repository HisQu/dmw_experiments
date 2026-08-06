"""Calculate auditable false-assignment count summaries for historian review."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import cast

import pandas as pd

import haiu.utils as ut
from dmw_experiments.studies.haiu_comparison.analysis.quality.grades import (
    CONDITION_LABELS,
    CONDITION_ORDER,
    QUALITY_COMPARISONS,
)

FALSE_INTERPRETATION_BANDS = ("0", "1", "2", "3+")
FALSE_ASSERTION_BANDS = ("0", "1", "2", "3", "4+")
PAIR_CHANGE_DIRECTIONS = ("improved", "unchanged", "worsened")


@dataclass(frozen=True, slots=True)
class QualityErrorAnalysis:
    """Keep review-count calculations separate from quality-grade analysis.

    :param observations: Validated reviewer-entered count rows, retaining a
        row when either optional count has a value.
    :param study_overview: Coverage counts for each optional review measure.
    :param matched_interpretation_pairs: Direct condition pairs with an
        independent-false-interpretation count for both models.
    :param matched_assertion_pairs: Direct condition pairs with an exact
        false-assertion count for both models.
    :param pooled_interpretation_incidence: Comparison- and condition-specific
        shares in the ``0``, ``1``, ``2``, and ``3+`` interpretation-error
        bands after provider-local direct pairs are pooled.
    :param pooled_assertion_incidence: Comparison- and condition-specific
        shares in the ``0``, ``1``, ``2``, ``3``, and ``4+`` atomic-assertion
        bands after provider-local direct pairs are pooled.
    :param interpretation_pair_differences: Provider-local paired change in
        independent false-interpretation counts, where the right condition
        minus the left condition is negative for an improvement.
    :param assertion_pair_differences: Provider-local paired change in exact
        false-assertion counts, using the same direction convention.
    :param pooled_interpretation_change_distribution: Pooled counts and shares
        of improved, unchanged, and worsened direct interpretation pairs.
    :param pooled_assertion_change_distribution: Pooled counts and shares of
        improved, unchanged, and worsened direct assertion pairs.
    """

    observations: pd.DataFrame
    study_overview: pd.DataFrame
    matched_interpretation_pairs: pd.DataFrame
    matched_assertion_pairs: pd.DataFrame
    pooled_interpretation_incidence: pd.DataFrame
    pooled_assertion_incidence: pd.DataFrame
    interpretation_pair_differences: pd.DataFrame
    assertion_pair_differences: pd.DataFrame
    pooled_interpretation_change_distribution: pd.DataFrame
    pooled_assertion_change_distribution: pd.DataFrame


def build_quality_error_analysis(
    observations: pd.DataFrame,
) -> QualityErrorAnalysis:
    """Derive error-count tables without treating empty optional cells as zero.

    The optional assertion count and the bounded interpretation count have
    separate denominators. This preserves the distinction between a reviewer
    recording zero errors and a reviewer not yet entering that measure.

    :param observations: Unmasked review rows with provider, regest,
        condition, ``false_assertions``, and ``false_interpretations``.
    :return: Validated reviewer inputs and plot-ready count tables.
    :raises ValueError: If identities are invalid or a populated count does
        not use its documented scale.
    """
    prepared = _prepare_error_observations(observations)
    matched_interpretation_pairs = _matched_error_pairs(
        prepared,
        value_column="false_interpretations",
        band_column="false_interpretations_band",
    )
    matched_assertion_pairs = _matched_error_pairs(
        prepared,
        value_column="false_assertions",
    )
    interpretation_pair_differences = _pair_count_differences(
        matched_interpretation_pairs,
        value_column="false_interpretations",
    )
    assertion_pair_differences = _pair_count_differences(
        matched_assertion_pairs,
        value_column="false_assertions",
    )
    return QualityErrorAnalysis(
        observations=prepared,
        study_overview=_study_overview(
            prepared,
            matched_interpretation_pairs=matched_interpretation_pairs,
            matched_assertion_pairs=matched_assertion_pairs,
        ),
        matched_interpretation_pairs=matched_interpretation_pairs,
        matched_assertion_pairs=matched_assertion_pairs,
        pooled_interpretation_incidence=_pooled_error_count_incidence(
            matched_interpretation_pairs,
            value_column="false_interpretations",
            band_column="false_interpretations_band",
        ),
        pooled_assertion_incidence=_pooled_error_count_incidence(
            matched_assertion_pairs,
            value_column="false_assertions",
            bands=FALSE_ASSERTION_BANDS,
        ),
        interpretation_pair_differences=interpretation_pair_differences,
        assertion_pair_differences=assertion_pair_differences,
        pooled_interpretation_change_distribution=(
            _pooled_pair_change_distribution(
                interpretation_pair_differences,
            )
        ),
        pooled_assertion_change_distribution=_pooled_pair_change_distribution(
            assertion_pair_differences,
        ),
    )


def _prepare_error_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Validate count entries and keep each populated review measurement.

    :param observations: Candidate unmasked error-count records.
    :return: Sorted rows with normalized optional count fields.
    :raises ValueError: If an identity, count, or condition is invalid.
    """
    required = {
        "provider_label",
        "regest_id",
        "condition",
        "false_assertions",
        "false_interpretations",
    }
    missing = sorted(required.difference(observations.columns))
    if missing:
        raise ValueError(
            "Historian error observations are missing columns: "
            f"{', '.join(missing)}"
        )
    prepared = observations.loc[:, sorted(required)].copy()
    for column in ("provider_label", "regest_id", "condition"):
        prepared[column] = prepared[column].astype(str).str.strip()
        if (prepared[column] == "").any():
            raise ValueError(
                f"Historian error observations contain an empty {column}."
            )
    unsupported = sorted(set(prepared["condition"]).difference(CONDITION_ORDER))
    if unsupported:
        raise ValueError(
            "Historian error observations contain unsupported conditions: "
            f"{', '.join(unsupported)}"
        )

    normalized_assertions: list[int | None] = []
    normalized_interpretations: list[int | None] = []
    interpretation_bands: list[str | None] = []
    for row in prepared.to_dict(orient="records"):
        normalized_assertions.append(
            _normalize_false_assertions(row["false_assertions"])
        )
        interpretation_count, interpretation_band = (
            _normalize_false_interpretations(row["false_interpretations"])
        )
        normalized_interpretations.append(interpretation_count)
        interpretation_bands.append(interpretation_band)
    prepared["false_assertions"] = pd.Series(
        normalized_assertions,
        index=prepared.index,
        dtype="Int64",
    )
    prepared["false_interpretations"] = pd.Series(
        normalized_interpretations,
        index=prepared.index,
        dtype="Int64",
    )
    prepared["false_interpretations_band"] = interpretation_bands
    prepared = prepared.loc[
        prepared["false_assertions"].notna()
        | prepared["false_interpretations"].notna()
    ].copy()
    duplicate_keys = prepared.duplicated(
        subset=["provider_label", "regest_id", "condition"],
        keep=False,
    )
    if duplicate_keys.any():
        duplicate_text = prepared.loc[
            duplicate_keys,
            ["provider_label", "regest_id", "condition"],
        ].to_dict(orient="records")
        raise ValueError(
            "Historian error observations must be unique per "
            f"provider/regest/condition: {duplicate_text}"
        )
    prepared["condition"] = pd.Categorical(
        prepared["condition"],
        categories=CONDITION_ORDER,
        ordered=True,
    )
    return prepared.sort_values(
        ["provider_label", "regest_id", "condition"]
    ).reset_index(drop=True)


def _normalize_false_assertions(value: object) -> int | None:
    """Normalize an optional non-negative atomic-assertion count.

    :param value: Candidate scalar from a review workbook or test table.
    :return: Whole non-negative count, or ``None`` for an empty value.
    :raises ValueError: If a populated value is not a whole non-negative count.
    """
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        raise ValueError(
            "false_assertions must be a non-negative whole number."
        )
    try:
        numeric = float(cast(float | str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "false_assertions must be a non-negative whole number."
        ) from exc
    if numeric < 0 or not numeric.is_integer():
        raise ValueError(
            "false_assertions must be a non-negative whole number."
        )
    return int(numeric)


def _normalize_false_interpretations(
    value: object,
) -> tuple[int | None, str | None]:
    """Normalize the bounded independent-interpretation count scale.

    :param value: Candidate scalar from a review workbook or test table.
    :return: Numeric lower bound and visible error band, or two ``None``
        values for an empty field.
    :raises ValueError: If a populated value is not ``0``, ``1``, ``2``, or
        ``3+``.
    """
    if _is_blank(value):
        return None, None
    if isinstance(value, bool):
        raise ValueError("false_interpretations must be 0, 1, 2, or 3+.")
    if isinstance(value, str):
        normalized = value.strip()
        if normalized == "3+":
            return 3, normalized
        if normalized in {"0", "1", "2"}:
            return int(normalized), normalized
    elif isinstance(value, Real):
        numeric = float(value)
        if numeric.is_integer() and int(numeric) in {0, 1, 2}:
            return int(numeric), str(int(numeric))
    raise ValueError("false_interpretations must be 0, 1, 2, or 3+.")


def _is_blank(value: object) -> bool:
    """Identify a missing optional review field without treating zero as blank.

    :param value: Candidate scalar from a review workbook or test table.
    :return: Whether the field has no evaluation value.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def _study_overview(
    observations: pd.DataFrame,
    *,
    matched_interpretation_pairs: pd.DataFrame,
    matched_assertion_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Count available values for each optional error measure.

    :param observations: Validated review rows with either count populated.
    :param matched_interpretation_pairs: Direct pairs with two populated
        interpretation counts.
    :param matched_assertion_pairs: Direct pairs with two populated assertion
        counts.
    :return: Named coverage counts for the audit workbook.
    """
    return pd.DataFrame(
        (
            {
                "measure": "reviews_with_any_error_count",
                "models": len(observations),
            },
            {
                "measure": "reviews_with_interpretation_count",
                "models": int(
                    observations["false_interpretations"].notna().sum()
                ),
            },
            {
                "measure": "reviews_with_assertion_count",
                "models": int(observations["false_assertions"].notna().sum()),
            },
            {
                "measure": "matched_interpretation_pairs",
                "models": len(matched_interpretation_pairs),
            },
            {
                "measure": "matched_assertion_pairs",
                "models": len(matched_assertion_pairs),
            },
        )
    )


def _matched_error_pairs(
    observations: pd.DataFrame,
    *,
    value_column: str,
    band_column: str | None = None,
) -> pd.DataFrame:
    """Keep only direct pairs with a populated value at both endpoints.

    Each metric has its own pairing rule because a reviewer may enter an
    independent-interpretation band but not an exact atomic-assertion count.
    This prevents unmatched regesta from being compared in the error-profile
    figures.

    :param observations: Validated optional review-count rows.
    :param value_column: Numeric count field to require at both pair endpoints.
    :param band_column: Optional visible band field that travels with the
        numeric count.
    :return: One direct-pair row per provider and regest with the endpoint
        values held in separate columns.
    """
    pair_columns = [
        "provider_label",
        "regest_id",
        "comparison",
        "first_condition",
        "second_condition",
        f"first_{value_column}",
        f"second_{value_column}",
    ]
    if band_column is not None:
        pair_columns.extend((f"first_{band_column}", f"second_{band_column}"))
    source_columns = ["provider_label", "regest_id", value_column]
    if band_column is not None:
        source_columns.append(band_column)
    source = observations.loc[
        observations[value_column].notna(), source_columns
    ].copy()
    frames: list[pd.DataFrame] = []
    for comparison in QUALITY_COMPARISONS:
        first = source.loc[
            observations.loc[source.index, "condition"] == comparison.first
        ].rename(
            columns={
                value_column: f"first_{value_column}",
                **(
                    {band_column: f"first_{band_column}"}
                    if band_column is not None
                    else {}
                ),
            }
        )
        second = source.loc[
            observations.loc[source.index, "condition"] == comparison.second
        ].rename(
            columns={
                value_column: f"second_{value_column}",
                **(
                    {band_column: f"second_{band_column}"}
                    if band_column is not None
                    else {}
                ),
            }
        )
        pairs = first.merge(
            second,
            on=("provider_label", "regest_id"),
            how="inner",
            validate="one_to_one",
        )
        if pairs.empty:
            continue
        pairs.insert(2, "comparison", comparison.key)
        pairs.insert(3, "first_condition", comparison.first)
        pairs.insert(4, "second_condition", comparison.second)
        frames.append(pairs.loc[:, pair_columns])
    if not frames:
        return ut.empty_frame(pair_columns)
    comparison_order = {
        comparison.key: index
        for index, comparison in enumerate(QUALITY_COMPARISONS)
    }
    result = pd.concat(frames, ignore_index=True)
    result["_comparison_order"] = result["comparison"].map(
        lambda comparison: comparison_order[str(comparison)]
    )
    return (
        result.sort_values(
            ["provider_label", "_comparison_order", "regest_id"],
            kind="stable",
        )
        .drop(columns="_comparison_order")
        .reset_index(drop=True)
    )


def _pooled_error_count_incidence(
    pairs: pd.DataFrame,
    *,
    value_column: str,
    band_column: str | None = None,
    bands: tuple[str, ...] = FALSE_INTERPRETATION_BANDS,
) -> pd.DataFrame:
    """Summarize direct-pair error bands after pooling provider-local pairs.

    Pairs are formed within one provider and regest before this aggregation.
    Pooling therefore combines comparable provider-local model pairs without
    constructing any cross-provider comparison.

    :param pairs: Direct provider–regest pairs with the selected count at both
        endpoints.
    :param value_column: Numeric count field stored in the direct-pair table.
    :param band_column: Optional preformatted band field, used for the bounded
        ``0``, ``1``, ``2``, ``3+`` interpretation measure.
    :param bands: Ordered, mutually exclusive display bands. The final band
        may use a ``+`` suffix to group counts at its numeric lower bound.
    :return: One row per direct comparison, endpoint, and error-count band.
    """
    columns = (
        "comparison",
        "pair_side",
        "condition",
        "condition_label",
        "error_count_band",
        "models",
        "count",
        "share",
        "any_error_count",
        "any_error_share",
    )
    records: list[dict[str, object]] = []
    for comparison in QUALITY_COMPARISONS:
        comparison_rows = pairs.loc[pairs["comparison"] == comparison.key]
        for side, condition in (
            ("first", comparison.first),
            ("second", comparison.second),
        ):
            if band_column is None:
                values = comparison_rows[f"{side}_{value_column}"].map(
                    lambda value: _error_count_band(value, bands=bands)
                )
            else:
                values = comparison_rows[f"{side}_{band_column}"]
            models = len(values)
            if not models:
                continue
            any_error_count = int((values != "0").sum())
            for band in bands:
                count = int((values == band).sum())
                records.append(
                    {
                        "comparison": comparison.key,
                        "pair_side": side,
                        "condition": condition,
                        "condition_label": CONDITION_LABELS[condition],
                        "error_count_band": band,
                        "models": models,
                        "count": count,
                        "share": count / models,
                        "any_error_count": any_error_count,
                        "any_error_share": any_error_count / models,
                    }
                )
    return ut.frame_from_records(records, columns=columns)


def _error_count_band(value: object, *, bands: tuple[str, ...]) -> str:
    """Map an exact non-negative count to a configured display band.

    :param value: Validated false atomic-assertion count.
    :param bands: Ordered display bands ending in an overflow band such as
        ``3+`` or ``4+``.
    :return: The exact count band or the configured overflow band.
    """
    count = int(cast(int, value))
    overflow_band = bands[-1]
    if not overflow_band.endswith("+"):
        raise ValueError("The final error-count band must use a '+' suffix.")
    overflow_threshold = int(overflow_band.removesuffix("+"))
    return str(count) if count < overflow_threshold else overflow_band


def _pair_count_differences(
    pairs: pd.DataFrame,
    *,
    value_column: str,
) -> pd.DataFrame:
    """Calculate right-minus-left count changes for direct provider pairs.

    The interpretation ``3+`` band enters its numeric lower bound of three.
    Consequently, an interpretation-count difference involving that band is a
    conservative lower-bound difference rather than an exact count change.

    :param pairs: Direct provider–regest pairs with both selected counts.
    :param value_column: Numeric count field stored in the pair table.
    :return: Pair rows with signed change and reader-facing direction label.
    """
    columns = (
        "provider_label",
        "regest_id",
        "comparison",
        "first_condition",
        "second_condition",
        "first_error_count",
        "second_error_count",
        "error_count_difference",
        "change_direction",
    )
    if pairs.empty:
        return ut.empty_frame(columns)
    result = pairs.loc[
        :,
        (
            "provider_label",
            "regest_id",
            "comparison",
            "first_condition",
            "second_condition",
            f"first_{value_column}",
            f"second_{value_column}",
        ),
    ].rename(
        columns={
            f"first_{value_column}": "first_error_count",
            f"second_{value_column}": "second_error_count",
        }
    )
    result["first_error_count"] = pd.to_numeric(
        result["first_error_count"],
        errors="raise",
    )
    result["second_error_count"] = pd.to_numeric(
        result["second_error_count"],
        errors="raise",
    )
    result["error_count_difference"] = (
        result["second_error_count"] - result["first_error_count"]
    )
    result["change_direction"] = result["error_count_difference"].map(
        _error_count_change_direction
    )
    comparison_order = {
        comparison.key: index
        for index, comparison in enumerate(QUALITY_COMPARISONS)
    }
    result["_comparison_order"] = result["comparison"].map(
        lambda comparison: comparison_order[str(comparison)]
    )
    return (
        result.sort_values(
            ["_comparison_order", "provider_label", "regest_id"],
            kind="stable",
        )
        .drop(columns="_comparison_order")
        .reset_index(drop=True)
        .loc[:, columns]
    )


def _error_count_change_direction(value: object) -> str:
    """Name the practical direction of a right-minus-left error difference.

    :param value: Signed difference between direct-pair endpoint counts.
    :return: ``improved``, ``worsened``, or ``unchanged``.
    """
    difference = int(cast(int, value))
    if difference < 0:
        return "improved"
    if difference > 0:
        return "worsened"
    return "unchanged"


def _pooled_pair_change_distribution(differences: pd.DataFrame) -> pd.DataFrame:
    """Summarize provider-local direct-pair changes after pooling them.

    Pairs are established within provider and regest before aggregation. The
    resulting shares therefore compare direct model changes without treating
    outputs from different providers as paired observations.

    :param differences: Direct provider–regest pairs with a change direction.
    :return: One row per direct comparison and change direction.
    """
    columns = (
        "comparison",
        "change_direction",
        "matched_pairs",
        "count",
        "share",
    )
    records: list[dict[str, object]] = []
    for comparison in QUALITY_COMPARISONS:
        comparison_rows = differences.loc[
            differences["comparison"] == comparison.key
        ]
        matched_pairs = len(comparison_rows)
        if not matched_pairs:
            continue
        for direction in PAIR_CHANGE_DIRECTIONS:
            count = int(
                (comparison_rows["change_direction"] == direction).sum()
            )
            records.append(
                {
                    "comparison": comparison.key,
                    "change_direction": direction,
                    "matched_pairs": matched_pairs,
                    "count": count,
                    "share": count / matched_pairs,
                }
            )
    return ut.frame_from_records(records, columns=columns)
