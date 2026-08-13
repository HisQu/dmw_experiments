"""Classify paired quality changes by direction and magnitude."""

from __future__ import annotations

from typing import Sequence, cast

import pandas as pd

import dmw_experiments.shared.analysis as ut

CHANGE_CATEGORY_ORDER = (
    "improved_by_more_than_2",
    "improved_by_2",
    "improved_by_1",
    "unchanged",
    "worsened_by_1",
    "worsened_by_2",
    "worsened_by_more_than_2",
)
CHANGE_CATEGORY_DIRECTION = {
    "improved_by_more_than_2": "improved",
    "improved_by_2": "improved",
    "improved_by_1": "improved",
    "unchanged": "unchanged",
    "worsened_by_1": "worsened",
    "worsened_by_2": "worsened",
    "worsened_by_more_than_2": "worsened",
}
CHANGE_CATEGORY_MAGNITUDE_BAND = {
    "improved_by_more_than_2": ">2",
    "improved_by_2": "2",
    "improved_by_1": "1",
    "unchanged": "0",
    "worsened_by_1": "1",
    "worsened_by_2": "2",
    "worsened_by_more_than_2": ">2",
}


def build_pooled_change_magnitude_distribution(
    pairs: pd.DataFrame,
    *,
    difference_column: str,
    comparison_order: Sequence[str],
) -> pd.DataFrame:
    """Count signed right-minus-left differences in seven stable bins.

    Negative differences improve the right condition and positive differences
    worsen it. Every represented comparison receives all seven categories,
    including zero-count rows, so plots and audit tables retain a stable shape.

    :param pairs: Provider-local direct pairs with one signed difference.
    :param difference_column: Column containing the right-minus-left value.
    :param comparison_order: Stable comparison keys to aggregate and order.
    :return: Counts and shares by direction and magnitude category.
    """
    columns = (
        "comparison",
        "change_category",
        "change_direction",
        "change_magnitude_band",
        "matched_pairs",
        "count",
        "share",
    )
    records: list[dict[str, object]] = []
    for comparison in comparison_order:
        comparison_rows = pairs.loc[pairs["comparison"] == comparison]
        matched_pairs = len(comparison_rows)
        if not matched_pairs:
            continue
        categories = comparison_rows[difference_column].map(
            _change_magnitude_category
        )
        for category in CHANGE_CATEGORY_ORDER:
            count = int((categories == category).sum())
            records.append(
                {
                    "comparison": comparison,
                    "change_category": category,
                    "change_direction": CHANGE_CATEGORY_DIRECTION[category],
                    "change_magnitude_band": (
                        CHANGE_CATEGORY_MAGNITUDE_BAND[category]
                    ),
                    "matched_pairs": matched_pairs,
                    "count": count,
                    "share": count / matched_pairs,
                }
            )
    return ut.frame_from_records(records, columns=columns)


def _change_magnitude_category(value: object) -> str:
    """Map one signed difference to its direction-and-magnitude category.

    :param value: Right endpoint minus left endpoint, with lower being better.
    :return: Stable category name from :data:`CHANGE_CATEGORY_ORDER`.
    """
    difference = int(cast(int, value))
    if difference < -2:
        return "improved_by_more_than_2"
    if difference == -2:
        return "improved_by_2"
    if difference == -1:
        return "improved_by_1"
    if difference == 0:
        return "unchanged"
    if difference == 1:
        return "worsened_by_1"
    if difference == 2:
        return "worsened_by_2"
    return "worsened_by_more_than_2"
