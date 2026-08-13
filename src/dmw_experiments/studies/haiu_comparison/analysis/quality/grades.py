"""Calculate descriptive and matched analyses for historian quality grades."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import cast

import numpy as np
import pandas as pd

import haiu.utils as ut
from dmw_experiments.studies.haiu_comparison.analysis.quality.changes import (
    build_pooled_change_magnitude_distribution,
)

CONDITION_ORDER = (
    "workflow_full_ontology",
    "workflow_rag",
    "haiu_rag_ontologizer",
)
CONDITION_LABELS = {
    "workflow_full_ontology": "DMW + Full Ontology",
    "workflow_rag": "DMW + Haiu RAG",
    "haiu_rag_ontologizer": "Standalone Haiu RAG",
}
FALSE_ASSIGNMENT_GRADE_MINIMUM = 4
WILSON_95_Z_SCORE = 1.959963984540054
PROVIDER_INTERACTION_BOOTSTRAP_RESAMPLES = 10_000
PROVIDER_INTERACTION_BOOTSTRAP_SEED = 20260804
GRADE_CHANGE_DIRECTIONS = ("improved", "unchanged", "worsened")


@dataclass(frozen=True, slots=True)
class QualityComparison:
    """Name one ordered, matched two-condition quality comparison.

    :param key: Stable comparison identifier used in derived tables.
    :param first: Condition displayed on the left side of the comparison.
    :param second: Condition displayed on the right side of the comparison.
    """

    key: str
    first: str
    second: str


QUALITY_COMPARISONS = (
    QualityComparison(
        key="DMW full ontology vs DMW RAG",
        first="workflow_full_ontology",
        second="workflow_rag",
    ),
    QualityComparison(
        key="DMW RAG vs standalone Haiu RAG",
        first="workflow_rag",
        second="haiu_rag_ontologizer",
    ),
)


@dataclass(frozen=True, slots=True)
class QualityGradeAnalysis:
    """Keep auditable quality-grade calculations in presentation-ready tables.

    :param observations: One validated, unmasked grade per
        provider/regest/condition.
    :param study_overview: Population and complete-triplet counts.
    :param condition_summary: Condition-level descriptive statistics.
    :param grade_distribution: Count and share for every grade 1 through 6.
    :param paired_grade_distribution: Count and share for every grade 1
        through 6 at each planned direct-comparison endpoint. The DMW + Haiu
        RAG condition is intentionally represented twice because each copy
        uses the valid provider–regest pairs of its adjacent comparison.
    :param false_assignment_pair_summary: Provider-, comparison-, and
        condition-specific incidence of grades 4–6 among matched direct pairs,
        including 95% Wilson score intervals.
    :param direct_duel_summary: Win, tie, and loss totals for each comparison.
    :param direct_duel_pairs: Per-regest evidence behind direct-duel totals.
    :param pooled_grade_change_distribution: Pooled provider-local direct
        pairs classified by whether the right condition improved, was
        unchanged, or worsened on the ordinal grade scale.
    :param pooled_grade_change_magnitude_distribution: The same paired
        population divided into exact one-grade, exact two-grade, and
        greater-than-two-grade changes on either side of unchanged.
    :param complete_triplets: Provider/regest rows with every condition graded.
    :param complete_triplet_grades: Long-form grades for complete triplets.
    :param provider_summary: Descriptive statistics grouped by provider.
    :param provider_interaction_summary: Condition-specific, shared-regest
        provider comparisons.
    :param provider_interaction_pairs: Per-regest evidence for provider
        interaction comparisons.
    :param provider_interaction_trend_summary: Matched-provider arithmetic
        grade means and paired-bootstrap 95% intervals for visual context.
    :param provider_false_assignment_interaction_summary: Matched-provider
        grade-4–6 rates with Wilson 95% intervals and exact McNemar tests.
    :param friedman_summary: Exploratory repeated-measures Friedman statistic.
    """

    observations: pd.DataFrame
    study_overview: pd.DataFrame
    condition_summary: pd.DataFrame
    grade_distribution: pd.DataFrame
    paired_grade_distribution: pd.DataFrame
    false_assignment_pair_summary: pd.DataFrame
    direct_duel_summary: pd.DataFrame
    direct_duel_pairs: pd.DataFrame
    pooled_grade_change_distribution: pd.DataFrame
    pooled_grade_change_magnitude_distribution: pd.DataFrame
    complete_triplets: pd.DataFrame
    complete_triplet_grades: pd.DataFrame
    provider_summary: pd.DataFrame
    provider_interaction_summary: pd.DataFrame
    provider_interaction_pairs: pd.DataFrame
    provider_interaction_trend_summary: pd.DataFrame
    provider_false_assignment_interaction_summary: pd.DataFrame
    friedman_summary: pd.DataFrame


def build_quality_grade_analysis(
    observations: pd.DataFrame,
) -> QualityGradeAnalysis:
    """Build all descriptive and matched tables from unmasked review grades.

    Each grade is an ordinal whole number where 1 is best and 6 is worst.
    Calculations deliberately retain the provider/regest pairing rather than
    pooling repeated observations as independent models.

    :param observations: Unmasked grade rows with ``provider_label``,
        ``regest_id``, ``condition``, and ``grade`` columns.
    :return: Validated source rows and all audit tables derived from them.
    :raises ValueError: If a grade row is incomplete, duplicated, outside the
        documented scale, or uses an unsupported condition.
    """
    prepared = _prepare_observations(observations)
    complete_triplets = _complete_triplets(prepared)
    complete_triplet_grades = _complete_triplet_grades(complete_triplets)
    outright_best_counts = _outright_best_counts(complete_triplets)
    direct_duel_pairs = _direct_duel_pairs(prepared)
    provider_interaction_pairs = _provider_interaction_pairs(complete_triplets)
    return QualityGradeAnalysis(
        observations=prepared,
        study_overview=_study_overview(prepared, complete_triplets),
        condition_summary=_condition_summary(
            prepared,
            outright_best_counts=outright_best_counts,
        ),
        grade_distribution=_grade_distribution(prepared),
        paired_grade_distribution=_paired_grade_distribution(direct_duel_pairs),
        false_assignment_pair_summary=_false_assignment_pair_summary(
            direct_duel_pairs
        ),
        direct_duel_summary=_direct_duel_summary(direct_duel_pairs),
        direct_duel_pairs=direct_duel_pairs,
        pooled_grade_change_distribution=_pooled_grade_change_distribution(
            direct_duel_pairs
        ),
        pooled_grade_change_magnitude_distribution=(
            _pooled_grade_change_magnitude_distribution(direct_duel_pairs)
        ),
        complete_triplets=complete_triplets,
        complete_triplet_grades=complete_triplet_grades,
        provider_summary=_provider_summary(prepared),
        provider_interaction_summary=_provider_interaction_summary(
            provider_interaction_pairs
        ),
        provider_interaction_pairs=provider_interaction_pairs,
        provider_interaction_trend_summary=_provider_interaction_trend_summary(
            provider_interaction_pairs
        ),
        provider_false_assignment_interaction_summary=(
            _provider_false_assignment_interaction_summary(
                provider_interaction_pairs
            )
        ),
        friedman_summary=_friedman_summary(complete_triplets),
    )


def _prepare_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the narrow grade-input table.

    :param observations: Candidate unmasked grade rows.
    :return: Sorted, uniquely keyed grade observations.
    :raises ValueError: If the input cannot support an auditable grade analysis.
    """
    required = {"provider_label", "regest_id", "condition", "grade"}
    missing = sorted(required.difference(observations.columns))
    if missing:
        raise ValueError(
            "Historian grade observations are missing columns: "
            f"{', '.join(missing)}"
        )
    prepared = observations.loc[:, sorted(required)].copy()
    for column in ("provider_label", "regest_id", "condition"):
        prepared[column] = prepared[column].astype(str).str.strip()
        if (prepared[column] == "").any():
            raise ValueError(
                f"Historian grade observations contain an empty {column}."
            )
    unsupported = sorted(set(prepared["condition"]).difference(CONDITION_ORDER))
    if unsupported:
        raise ValueError(
            "Historian grade observations contain unsupported conditions: "
            f"{', '.join(unsupported)}"
        )
    grades = ut.numeric_series(prepared["grade"], errors="raise")
    if grades.isna().any() or (~grades.between(1, 6)).any():
        raise ValueError(
            "Historian grades must be numeric values from 1 through 6."
        )
    if any(not float(grade).is_integer() for grade in grades.to_list()):
        raise ValueError(
            "Historian grades must use whole values from 1 through 6."
        )
    prepared["grade"] = grades.astype(int)
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
            "Historian grade observations must be unique per "
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


def _study_overview(
    observations: pd.DataFrame,
    complete_triplets: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize the available and complete historian-grade populations.

    :param observations: Validated individual grades.
    :param complete_triplets: Rows with all three condition grades.
    :return: Named count table for the reader-facing workbook.
    """
    records = (
        {"measure": "graded_models", "value": len(observations)},
        {
            "measure": "provider_regest_triplets",
            "value": observations.groupby(
                ["provider_label", "regest_id"]
            ).ngroups,
        },
        {
            "measure": "unique_regesta",
            "value": observations["regest_id"].nunique(),
        },
        {
            "measure": "providers",
            "value": observations["provider_label"].nunique(),
        },
        {
            "measure": "complete_three_condition_triplets",
            "value": len(complete_triplets),
        },
    )
    return ut.frame_from_records(records, columns=("measure", "value"))


def _complete_triplets(observations: pd.DataFrame) -> pd.DataFrame:
    """Pivot only provider/regest blocks containing all three conditions.

    :param observations: Validated individual grades.
    :return: Wide triplet rows with the strict winner retained separately.
    """
    columns = ["provider_label", "regest_id", *CONDITION_ORDER]
    if observations.empty:
        return ut.empty_frame(
            [*columns, "best_grade", "outright_best_condition"]
        )
    wide = observations.pivot(
        index=["provider_label", "regest_id"],
        columns="condition",
        values="grade",
    ).reset_index()
    for condition in CONDITION_ORDER:
        if condition not in wide.columns:
            wide[condition] = pd.NA
    complete = wide.dropna(subset=list(CONDITION_ORDER)).loc[:, columns].copy()
    complete[list(CONDITION_ORDER)] = complete[list(CONDITION_ORDER)].astype(
        int
    )
    best_grades = complete.loc[:, CONDITION_ORDER].min(axis="columns")
    best_counts = (
        complete.loc[:, CONDITION_ORDER]
        .eq(
            best_grades,
            axis="rows",
        )
        .sum(axis="columns")
    )
    complete["best_grade"] = best_grades.astype(int)
    complete["outright_best_condition"] = [
        (
            next(
                condition
                for condition in CONDITION_ORDER
                if row[condition] == best_grade
            )
            if count == 1
            else "tie"
        )
        for (_, row), best_grade, count in zip(
            complete.iterrows(),
            best_grades,
            best_counts,
            strict=True,
        )
    ]
    return complete.sort_values(["provider_label", "regest_id"]).reset_index(
        drop=True
    )


def _complete_triplet_grades(complete_triplets: pd.DataFrame) -> pd.DataFrame:
    """Return complete triplets in long format for paired trajectories.

    :param complete_triplets: Wide, complete provider/regest triplets.
    :return: Ordered provider/regest/condition/grade records.
    """
    if complete_triplets.empty:
        return ut.empty_frame(
            ["provider_label", "regest_id", "condition", "grade"]
        )
    grades = complete_triplets.melt(
        id_vars=("provider_label", "regest_id"),
        value_vars=CONDITION_ORDER,
        var_name="condition",
        value_name="grade",
    )
    grades["condition"] = pd.Categorical(
        grades["condition"],
        categories=CONDITION_ORDER,
        ordered=True,
    )
    return grades.sort_values(
        ["provider_label", "regest_id", "condition"]
    ).reset_index(drop=True)


def _outright_best_counts(complete_triplets: pd.DataFrame) -> dict[str, int]:
    """Count strict three-condition winners without allocating tied minima.

    :param complete_triplets: Wide triplet grades with winner labels.
    :return: Number of strict wins keyed by condition.
    """
    winners = complete_triplets["outright_best_condition"]
    return {
        condition: int((winners == condition).sum())
        for condition in CONDITION_ORDER
    }


def _condition_summary(
    observations: pd.DataFrame,
    *,
    outright_best_counts: dict[str, int],
) -> pd.DataFrame:
    """Calculate condition-level descriptive quality statistics.

    :param observations: Validated individual grades.
    :param outright_best_counts: Strict winner totals from complete triplets.
    :return: One audit row for each experimental condition.
    """
    records: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        values = observations.loc[
            observations["condition"] == condition,
            "grade",
        ]
        count = len(values)
        grade_1_2 = int(values.between(1, 2).sum())
        grade_3_4 = int(values.between(3, 4).sum())
        grade_5_6 = int(values.between(5, 6).sum())
        records.append(
            {
                "condition": condition,
                "condition_label": CONDITION_LABELS[condition],
                "models": count,
                "unique_regesta": int(
                    observations.loc[
                        observations["condition"] == condition,
                        "regest_id",
                    ].nunique()
                ),
                "mean_grade": float(values.mean()) if count else None,
                "median_grade": float(values.median()) if count else None,
                "sample_sd_grade": (
                    float(values.std(ddof=1)) if count > 1 else None
                ),
                "grade_1_count": int((values == 1).sum()),
                "grade_1_2_count": grade_1_2,
                "grade_1_2_share": grade_1_2 / count if count else None,
                "grade_3_4_count": grade_3_4,
                "grade_3_4_share": grade_3_4 / count if count else None,
                "grade_5_6_count": grade_5_6,
                "grade_5_6_share": grade_5_6 / count if count else None,
                "grade_6_count": int((values == 6).sum()),
                "outright_best_count": outright_best_counts[condition],
            }
        )
    return pd.DataFrame(records)


def _grade_distribution(observations: pd.DataFrame) -> pd.DataFrame:
    """Count every ordinal grade for every condition, including zeroes.

    :param observations: Validated individual grades.
    :return: Long-form count and share rows for grades 1 through 6.
    """
    records: list[dict[str, object]] = []
    for condition in CONDITION_ORDER:
        values = observations.loc[
            observations["condition"] == condition,
            "grade",
        ]
        count = len(values)
        for grade in range(1, 7):
            grade_count = int((values == grade).sum())
            records.append(
                {
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "grade": grade,
                    "models": grade_count,
                    "share": grade_count / count if count else None,
                }
            )
    return pd.DataFrame(records)


def _paired_grade_distribution(direct_duel_pairs: pd.DataFrame) -> pd.DataFrame:
    """Calculate grade bands at the endpoints of each matched comparison.

    The same DMW + Haiu RAG condition participates in both planned direct
    comparisons. It must therefore retain one distribution per comparison
    rather than pooling distinct pairable populations into one bar.

    :param direct_duel_pairs: Complete provider-local grade pairs for the two
        planned comparisons.
    :return: Grade counts and shares for every direct-comparison endpoint.
    """
    columns = (
        "comparison",
        "pair_side",
        "condition",
        "condition_label",
        "grade",
        "models",
        "count",
        "share",
    )
    records: list[dict[str, object]] = []
    for comparison in QUALITY_COMPARISONS:
        pairs = direct_duel_pairs.loc[
            direct_duel_pairs["comparison"] == comparison.key
        ]
        models = len(pairs)
        if not models:
            continue
        for pair_side, condition, grade_column in (
            ("first", comparison.first, "first_grade"),
            ("second", comparison.second, "second_grade"),
        ):
            grades = pairs[grade_column]
            for grade in range(1, 7):
                count = int((grades == grade).sum())
                records.append(
                    {
                        "comparison": comparison.key,
                        "pair_side": pair_side,
                        "condition": condition,
                        "condition_label": CONDITION_LABELS[condition],
                        "grade": grade,
                        "models": models,
                        "count": count,
                        "share": count / models,
                    }
                )
    return ut.frame_from_records(records, columns=columns)


def _false_assignment_pair_summary(
    direct_duel_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate false-assignment incidence within matched direct comparisons.

    The documented rubric permits grades 1–3 only when no clearly false
    assignment is present. Grades 4–6 therefore operationalize the incidence
    of one or more false assignments. Each provider/comparison denominator is
    taken directly from the complete direct pairs, so its two condition bars
    describe exactly the same provider–regest population. Wilson score
    intervals describe the binomial uncertainty without producing impossible
    bounds near zero or one.

    :param direct_duel_pairs: Per-regest rows with both condition grades.
    :return: Two endpoint rows per provider/direct comparison, with shared
        matched-pair denominators, counts, shares, and Wilson 95% bounds.
    """
    records: list[dict[str, object]] = []
    for comparison in QUALITY_COMPARISONS:
        comparison_pairs = direct_duel_pairs.loc[
            direct_duel_pairs["comparison"] == comparison.key
        ]
        provider_order = list(dict.fromkeys(comparison_pairs["provider_label"]))
        for provider_label in provider_order:
            provider_pairs = comparison_pairs.loc[
                comparison_pairs["provider_label"] == provider_label
            ]
            models = len(provider_pairs)
            for pair_side, condition, grade_column in (
                ("left", comparison.first, "first_grade"),
                ("right", comparison.second, "second_grade"),
            ):
                grades = provider_pairs[grade_column]
                false_assignment_count = int(
                    (grades >= FALSE_ASSIGNMENT_GRADE_MINIMUM).sum()
                )
                lower, upper = _wilson_95_interval(
                    successes=false_assignment_count,
                    trials=models,
                )
                records.append(
                    {
                        "comparison": comparison.key,
                        "provider_label": provider_label,
                        "first_condition": comparison.first,
                        "second_condition": comparison.second,
                        "pair_side": pair_side,
                        "condition": condition,
                        "condition_label": CONDITION_LABELS[condition],
                        "models": models,
                        "false_assignment_count": false_assignment_count,
                        "false_assignment_share": (
                            false_assignment_count / models if models else None
                        ),
                        "wilson_95_lower_share": lower,
                        "wilson_95_upper_share": upper,
                    }
                )
    columns = (
        "comparison",
        "provider_label",
        "first_condition",
        "second_condition",
        "pair_side",
        "condition",
        "condition_label",
        "models",
        "false_assignment_count",
        "false_assignment_share",
        "wilson_95_lower_share",
        "wilson_95_upper_share",
    )
    return (
        ut.frame_from_records(records, columns=columns)
        .sort_values(["comparison", "provider_label", "pair_side"])
        .reset_index(drop=True)
    )


def _wilson_95_interval(
    *,
    successes: int,
    trials: int,
) -> tuple[float | None, float | None]:
    """Calculate the two-sided 95% Wilson score interval for one proportion.

    :param successes: Number of analyses containing a false assignment.
    :param trials: Number of graded analyses in the same cell.
    :return: Inclusive lower and upper proportion bounds, or two missing values
        when no analyses are available.
    :raises ValueError: If the count lies outside the valid binomial range.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Wilson interval requires 0 <= successes <= trials")
    if trials == 0:
        return None, None
    proportion = successes / trials
    z_squared = WILSON_95_Z_SCORE**2
    denominator = 1.0 + (z_squared / trials)
    centre = (proportion + (z_squared / (2.0 * trials))) / denominator
    half_width = (
        WILSON_95_Z_SCORE
        * math.sqrt(
            (proportion * (1.0 - proportion) / trials)
            + (z_squared / (4.0 * trials**2))
        )
        / denominator
    )
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def _direct_duel_pairs(observations: pd.DataFrame) -> pd.DataFrame:
    """Create one ordered comparison record for each complete grade duel.

    :param observations: Validated individual grades.
    :return: Per-provider/regest direct-duel evidence, including its winner.
    """
    records: list[dict[str, object]] = []
    index_columns = ["provider_label", "regest_id"]
    for comparison in QUALITY_COMPARISONS:
        selected = observations.loc[
            observations["condition"].isin(
                (comparison.first, comparison.second)
            ),
            [*index_columns, "condition", "grade"],
        ]
        wide = selected.pivot(
            index=index_columns,
            columns="condition",
            values="grade",
        ).reset_index()
        if (
            comparison.first not in wide.columns
            or comparison.second not in wide.columns
        ):
            continue
        complete = wide.dropna(subset=[comparison.first, comparison.second])
        for row in complete.to_dict(orient="records"):
            first_grade = int(row[comparison.first])
            second_grade = int(row[comparison.second])
            winner = (
                "first_better"
                if first_grade < second_grade
                else "second_better"
                if second_grade < first_grade
                else "tie"
            )
            records.append(
                {
                    "comparison": comparison.key,
                    "first_condition": comparison.first,
                    "first_condition_label": CONDITION_LABELS[comparison.first],
                    "second_condition": comparison.second,
                    "second_condition_label": CONDITION_LABELS[
                        comparison.second
                    ],
                    "provider_label": row["provider_label"],
                    "regest_id": row["regest_id"],
                    "first_grade": first_grade,
                    "second_grade": second_grade,
                    "first_minus_second_grade": first_grade - second_grade,
                    "winner": winner,
                }
            )
    columns = (
        "comparison",
        "first_condition",
        "first_condition_label",
        "second_condition",
        "second_condition_label",
        "provider_label",
        "regest_id",
        "first_grade",
        "second_grade",
        "first_minus_second_grade",
        "winner",
    )
    return (
        ut.frame_from_records(records, columns=columns)
        .sort_values(["comparison", "provider_label", "regest_id"])
        .reset_index(drop=True)
    )


def _direct_duel_summary(direct_duel_pairs: pd.DataFrame) -> pd.DataFrame:
    """Summarize first wins, ties, and second wins for every duel.

    :param direct_duel_pairs: Per-regest direct-duel evidence.
    :return: One count and share row per ordered comparison.
    """
    records: list[dict[str, object]] = []
    for comparison in QUALITY_COMPARISONS:
        pairs = direct_duel_pairs.loc[
            direct_duel_pairs["comparison"] == comparison.key
        ]
        count = len(pairs)
        first_wins = int((pairs["winner"] == "first_better").sum())
        ties = int((pairs["winner"] == "tie").sum())
        second_wins = int((pairs["winner"] == "second_better").sum())
        records.append(
            {
                "comparison": comparison.key,
                "first_condition": comparison.first,
                "first_condition_label": CONDITION_LABELS[comparison.first],
                "second_condition": comparison.second,
                "second_condition_label": CONDITION_LABELS[comparison.second],
                "complete_pairs": count,
                "first_better_count": first_wins,
                "first_better_share": first_wins / count if count else None,
                "tie_count": ties,
                "tie_share": ties / count if count else None,
                "second_better_count": second_wins,
                "second_better_share": second_wins / count if count else None,
            }
        )
    return pd.DataFrame(records)


def _pooled_grade_change_distribution(
    direct_duel_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Pool already matched provider-local grade changes by direction.

    The right condition is the candidate change. A lower right-hand grade is
    an improvement, an equal grade is unchanged, and a higher right-hand grade
    is a worsening. Each row in ``direct_duel_pairs`` was formed within one
    provider and regest, so pooling never treats outputs from two providers as
    a matched pair.

    :param direct_duel_pairs: Complete provider/regest pairs for each planned
        ordered comparison.
    :return: Counts and shares for improved, unchanged, and worsened pairs.
    """
    columns = (
        "comparison",
        "change_direction",
        "matched_pairs",
        "count",
        "share",
    )
    records: list[dict[str, object]] = []
    winner_to_direction = {
        "first_better": "worsened",
        "tie": "unchanged",
        "second_better": "improved",
    }
    for comparison in QUALITY_COMPARISONS:
        pairs = direct_duel_pairs.loc[
            direct_duel_pairs["comparison"] == comparison.key
        ]
        matched_pairs = len(pairs)
        if not matched_pairs:
            continue
        directions = pairs["winner"].map(winner_to_direction)
        for direction in GRADE_CHANGE_DIRECTIONS:
            count = int((directions == direction).sum())
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


def _pooled_grade_change_magnitude_distribution(
    direct_duel_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Divide matched grade changes into seven signed-magnitude bins.

    The right condition is the candidate change, so its grade minus the left
    condition's grade is negative for an improvement. The existing
    three-direction distribution remains available for coarse summaries.

    :param direct_duel_pairs: Complete provider/regest grade pairs for every
        planned ordered comparison.
    :return: Counts and shares for exact one-grade, exact two-grade, and
        greater-than-two-grade changes around unchanged.
    """
    pairs = direct_duel_pairs.assign(
        right_minus_left_grade=(
            direct_duel_pairs["second_grade"] - direct_duel_pairs["first_grade"]
        )
    )
    return build_pooled_change_magnitude_distribution(
        pairs,
        difference_column="right_minus_left_grade",
        comparison_order=tuple(
            comparison.key for comparison in QUALITY_COMPARISONS
        ),
    )


def _provider_summary(observations: pd.DataFrame) -> pd.DataFrame:
    """Calculate descriptive statistics by provider without pooling them.

    :param observations: Validated individual grades.
    :return: Provider-level descriptive summary.
    """
    records: list[dict[str, object]] = []
    for provider_label, rows in observations.groupby(
        "provider_label",
        sort=False,
    ):
        grades = rows["grade"]
        count = len(rows)
        grade_1_2 = int(grades.between(1, 2).sum())
        grade_5_6 = int(grades.between(5, 6).sum())
        records.append(
            {
                "provider_label": provider_label,
                "models": count,
                "unique_regesta": int(rows["regest_id"].nunique()),
                "mean_grade": float(grades.mean()) if count else None,
                "median_grade": float(grades.median()) if count else None,
                "grade_1_2_count": grade_1_2,
                "grade_1_2_share": grade_1_2 / count if count else None,
                "grade_5_6_count": grade_5_6,
                "grade_5_6_share": grade_5_6 / count if count else None,
            }
        )
    return pd.DataFrame(records)


def _provider_interaction_pairs(
    complete_triplets: pd.DataFrame,
) -> pd.DataFrame:
    """Pair provider grades only for regesta complete in both providers.

    :param complete_triplets: Wide complete condition triplets.
    :return: Per-regest and condition provider comparisons.
    """
    provider_labels = list(dict.fromkeys(complete_triplets["provider_label"]))
    records: list[dict[str, object]] = []
    for first_provider, second_provider in combinations(provider_labels, 2):
        first = complete_triplets.loc[
            complete_triplets["provider_label"] == first_provider,
            ["regest_id", *CONDITION_ORDER],
        ].set_index("regest_id")
        second = complete_triplets.loc[
            complete_triplets["provider_label"] == second_provider,
            ["regest_id", *CONDITION_ORDER],
        ].set_index("regest_id")
        shared_regesta = first.index.intersection(second.index).sort_values()
        for regest_id in shared_regesta:
            for condition in CONDITION_ORDER:
                first_grade = int(first.loc[regest_id, condition])
                second_grade = int(second.loc[regest_id, condition])
                better_provider = (
                    first_provider
                    if first_grade < second_grade
                    else second_provider
                    if second_grade < first_grade
                    else "tie"
                )
                records.append(
                    {
                        "first_provider": first_provider,
                        "second_provider": second_provider,
                        "regest_id": regest_id,
                        "condition": condition,
                        "condition_label": CONDITION_LABELS[condition],
                        "first_provider_grade": first_grade,
                        "second_provider_grade": second_grade,
                        "first_minus_second_grade": first_grade - second_grade,
                        "better_provider": better_provider,
                    }
                )
    columns = (
        "first_provider",
        "second_provider",
        "regest_id",
        "condition",
        "condition_label",
        "first_provider_grade",
        "second_provider_grade",
        "first_minus_second_grade",
        "better_provider",
    )
    return (
        ut.frame_from_records(records, columns=columns)
        .sort_values(
            ["first_provider", "second_provider", "regest_id", "condition"]
        )
        .reset_index(drop=True)
    )


def _provider_interaction_summary(
    provider_interaction_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize provider differences within each condition and shared sample.

    :param provider_interaction_pairs: Per-regest paired provider grades.
    :return: Condition-level matched provider comparison table.
    """
    if provider_interaction_pairs.empty:
        return ut.empty_frame(
            [
                "first_provider",
                "second_provider",
                "condition",
                "condition_label",
                "shared_regesta",
                "first_provider_mean_grade",
                "second_provider_mean_grade",
                "first_provider_better_count",
                "tie_count",
                "second_provider_better_count",
                "exact_sign_test_non_tied_pairs",
                "exact_sign_test_p_value",
            ]
        )
    records: list[dict[str, object]] = []
    grouped = provider_interaction_pairs.groupby(
        ["first_provider", "second_provider", "condition"],
        observed=True,
        sort=False,
    )
    for group_key, rows in grouped:
        first_provider, second_provider, condition = cast(
            tuple[str, str, str],
            group_key,
        )
        records.append(
            {
                "first_provider": first_provider,
                "second_provider": second_provider,
                "condition": condition,
                "condition_label": CONDITION_LABELS[str(condition)],
                "shared_regesta": len(rows),
                "first_provider_mean_grade": float(
                    rows["first_provider_grade"].mean()
                ),
                "second_provider_mean_grade": float(
                    rows["second_provider_grade"].mean()
                ),
                "first_provider_better_count": int(
                    (rows["better_provider"] == first_provider).sum()
                ),
                "tie_count": int((rows["better_provider"] == "tie").sum()),
                "second_provider_better_count": int(
                    (rows["better_provider"] == second_provider).sum()
                ),
                "exact_sign_test_non_tied_pairs": int(
                    (rows["better_provider"] != "tie").sum()
                ),
                "exact_sign_test_p_value": _two_sided_exact_sign_test_p_value(
                    first_better_count=int(
                        (rows["better_provider"] == first_provider).sum()
                    ),
                    second_better_count=int(
                        (rows["better_provider"] == second_provider).sum()
                    ),
                ),
            }
        )
    return ut.frame_from_records(
        records,
        columns=(
            "first_provider",
            "second_provider",
            "condition",
            "condition_label",
            "shared_regesta",
            "first_provider_mean_grade",
            "second_provider_mean_grade",
            "first_provider_better_count",
            "tie_count",
            "second_provider_better_count",
            "exact_sign_test_non_tied_pairs",
            "exact_sign_test_p_value",
        ),
    )


def _provider_interaction_trend_summary(
    provider_interaction_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate paired-bootstrap grade intervals for interaction overlays.

    Arithmetic grade means remain descriptive because the grading scale is
    ordinal. The paired bootstrap resamples shared regesta jointly across both
    providers, so the two plotted mean intervals retain the matched study
    population. Exact paired sign tests remain the inferential result.

    :param provider_interaction_pairs: Complete provider/regest grade pairs.
    :return: One visual-summary row per provider and condition, including a
        95% paired-bootstrap interval for the descriptive mean grade.
    """
    columns = (
        "first_provider",
        "second_provider",
        "condition",
        "condition_label",
        "provider_label",
        "models",
        "mean_grade",
        "bootstrap_95_lower_mean_grade",
        "bootstrap_95_upper_mean_grade",
    )
    if provider_interaction_pairs.empty:
        return ut.empty_frame(columns)
    records: list[dict[str, object]] = []
    generator = np.random.default_rng(PROVIDER_INTERACTION_BOOTSTRAP_SEED)
    grouped = provider_interaction_pairs.groupby(
        ["first_provider", "second_provider", "condition"],
        observed=True,
        sort=False,
    )
    for group_key, rows in grouped:
        first_provider, second_provider, condition = cast(
            tuple[str, str, str],
            group_key,
        )
        first_values = rows["first_provider_grade"].to_numpy(dtype=float)
        second_values = rows["second_provider_grade"].to_numpy(dtype=float)
        (
            first_lower,
            first_upper,
            second_lower,
            second_upper,
        ) = _paired_bootstrap_mean_intervals(
            first_values,
            second_values,
            generator=generator,
        )
        models = len(rows)
        for provider_label, values, lower, upper in (
            (first_provider, first_values, first_lower, first_upper),
            (second_provider, second_values, second_lower, second_upper),
        ):
            records.append(
                {
                    "first_provider": first_provider,
                    "second_provider": second_provider,
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[str(condition)],
                    "provider_label": provider_label,
                    "models": models,
                    "mean_grade": float(values.mean()),
                    "bootstrap_95_lower_mean_grade": lower,
                    "bootstrap_95_upper_mean_grade": upper,
                }
            )
    return ut.frame_from_records(records, columns=columns)


def _paired_bootstrap_mean_intervals(
    first_values: np.ndarray,
    second_values: np.ndarray,
    *,
    generator: np.random.Generator,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Resample paired grade margins jointly to bound descriptive means.

    :param first_values: First-provider grades for the shared regesta.
    :param second_values: Corresponding second-provider grades in the same
        regest order.
    :param generator: Reproducible random source shared by the calculation.
    :return: First and second provider lower/upper 95% percentile bounds.
    :raises ValueError: If the pair arrays do not have identical lengths.
    """
    if len(first_values) != len(second_values):
        raise ValueError("Paired bootstrap requires equally long margins.")
    if not len(first_values):
        return None, None, None, None
    indices = generator.integers(
        0,
        len(first_values),
        size=(PROVIDER_INTERACTION_BOOTSTRAP_RESAMPLES, len(first_values)),
    )
    first_means = first_values[indices].mean(axis=1)
    second_means = second_values[indices].mean(axis=1)
    first_lower, first_upper = np.quantile(first_means, (0.025, 0.975))
    second_lower, second_upper = np.quantile(second_means, (0.025, 0.975))
    return (
        float(first_lower),
        float(first_upper),
        float(second_lower),
        float(second_upper),
    )


def _provider_false_assignment_interaction_summary(
    provider_interaction_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Measure matched grade-4–6 rates and provider discordance.

    A grade of 4–6 means that the review identified at least one false
    assignment. Wilson intervals summarize each provider's marginal rate;
    the paired provider contrast uses the two-sided exact McNemar test on the
    discordant regesta.

    :param provider_interaction_pairs: Complete provider/regest grade pairs.
    :return: One condition summary with matched rates, Wilson intervals, and
        exact McNemar evidence.
    """
    columns = (
        "first_provider",
        "second_provider",
        "condition",
        "condition_label",
        "shared_regesta",
        "first_provider_false_assignment_count",
        "first_provider_false_assignment_share",
        "first_provider_wilson_95_lower_share",
        "first_provider_wilson_95_upper_share",
        "second_provider_false_assignment_count",
        "second_provider_false_assignment_share",
        "second_provider_wilson_95_lower_share",
        "second_provider_wilson_95_upper_share",
        "both_false_assignment_count",
        "both_factually_safe_count",
        "first_provider_only_false_assignment_count",
        "second_provider_only_false_assignment_count",
        "exact_mcnemar_discordant_pairs",
        "exact_mcnemar_p_value",
    )
    if provider_interaction_pairs.empty:
        return ut.empty_frame(columns)
    records: list[dict[str, object]] = []
    grouped = provider_interaction_pairs.groupby(
        ["first_provider", "second_provider", "condition"],
        observed=True,
        sort=False,
    )
    for group_key, rows in grouped:
        first_provider, second_provider, condition = cast(
            tuple[str, str, str],
            group_key,
        )
        first_false = (
            rows["first_provider_grade"] >= FALSE_ASSIGNMENT_GRADE_MINIMUM
        )
        second_false = (
            rows["second_provider_grade"] >= FALSE_ASSIGNMENT_GRADE_MINIMUM
        )
        shared_regesta = len(rows)
        first_count = int(first_false.sum())
        second_count = int(second_false.sum())
        first_lower, first_upper = _wilson_95_interval(
            successes=first_count,
            trials=shared_regesta,
        )
        second_lower, second_upper = _wilson_95_interval(
            successes=second_count,
            trials=shared_regesta,
        )
        first_only = int((first_false & ~second_false).sum())
        second_only = int((~first_false & second_false).sum())
        records.append(
            {
                "first_provider": first_provider,
                "second_provider": second_provider,
                "condition": condition,
                "condition_label": CONDITION_LABELS[str(condition)],
                "shared_regesta": shared_regesta,
                "first_provider_false_assignment_count": first_count,
                "first_provider_false_assignment_share": (
                    first_count / shared_regesta
                ),
                "first_provider_wilson_95_lower_share": first_lower,
                "first_provider_wilson_95_upper_share": first_upper,
                "second_provider_false_assignment_count": second_count,
                "second_provider_false_assignment_share": (
                    second_count / shared_regesta
                ),
                "second_provider_wilson_95_lower_share": second_lower,
                "second_provider_wilson_95_upper_share": second_upper,
                "both_false_assignment_count": int(
                    (first_false & second_false).sum()
                ),
                "both_factually_safe_count": int(
                    (~first_false & ~second_false).sum()
                ),
                "first_provider_only_false_assignment_count": first_only,
                "second_provider_only_false_assignment_count": second_only,
                "exact_mcnemar_discordant_pairs": first_only + second_only,
                "exact_mcnemar_p_value": _two_sided_exact_sign_test_p_value(
                    first_better_count=second_only,
                    second_better_count=first_only,
                ),
            }
        )
    return ut.frame_from_records(records, columns=columns)


def _two_sided_exact_sign_test_p_value(
    *,
    first_better_count: int,
    second_better_count: int,
) -> float | None:
    """Calculate the tie-excluding exact paired sign-test probability.

    The grade scale is ordinal, so the test uses only which provider receives
    the lower grade in each non-tied matched regest. Under the null hypothesis,
    either provider is equally likely to receive the lower grade.

    :param first_better_count: Non-tied regesta favoring the first provider.
    :param second_better_count: Non-tied regesta favoring the second provider.
    :return: Two-sided exact binomial probability, or ``None`` for all ties.
    """
    non_tied_pairs = first_better_count + second_better_count
    if not non_tied_pairs:
        return None
    less_frequent_count = min(first_better_count, second_better_count)
    lower_tail = (
        sum(
            math.comb(non_tied_pairs, wins)
            for wins in range(less_frequent_count + 1)
        )
        / 2**non_tied_pairs
    )
    return min(1.0, 2.0 * lower_tail)


def _friedman_summary(complete_triplets: pd.DataFrame) -> pd.DataFrame:
    """Calculate a tie-corrected exploratory Friedman statistic.

    The χ² survival function for two degrees of freedom is ``exp(-χ² / 2)``.
    This result is descriptive only because provider/regest observations are not
    an independent random sample and the ordinal grade scale is small.

    :param complete_triplets: Wide triplets to rank within provider/regest.
    :return: One-row statistic table or an explicit unavailable row.
    """
    if len(complete_triplets) < 2:
        return pd.DataFrame(
            [
                {
                    "complete_triplets": len(complete_triplets),
                    "conditions": len(CONDITION_ORDER),
                    "chi_square": None,
                    "degrees_of_freedom": len(CONDITION_ORDER) - 1,
                    "asymptotic_p_value": None,
                    "tie_correction": None,
                    "interpretation": "Unavailable: fewer than two complete triplets.",
                }
            ]
        )
    rank_sums = [0.0] * len(CONDITION_ORDER)
    tie_term = 0
    for row in complete_triplets.loc[:, CONDITION_ORDER].itertuples(
        index=False,
        name=None,
    ):
        ranks, block_tie_term = _average_ranks(row)
        rank_sums = [
            total + rank for total, rank in zip(rank_sums, ranks, strict=True)
        ]
        tie_term += block_tie_term
    blocks = len(complete_triplets)
    conditions = len(CONDITION_ORDER)
    uncorrected = 12.0 / (blocks * conditions * (conditions + 1)) * sum(
        rank_sum**2 for rank_sum in rank_sums
    ) - 3.0 * blocks * (conditions + 1)
    tie_correction = 1.0 - tie_term / (
        blocks * conditions * (conditions**2 - 1)
    )
    statistic = uncorrected / tie_correction if tie_correction else 0.0
    return pd.DataFrame(
        [
            {
                "complete_triplets": blocks,
                "conditions": conditions,
                "chi_square": statistic,
                "degrees_of_freedom": conditions - 1,
                "asymptotic_p_value": math.exp(-statistic / 2.0),
                "tie_correction": tie_correction,
                "interpretation": "Exploratory only; do not treat as publication-grade inference.",
            }
        ]
    )


def _average_ranks(values: tuple[int, ...]) -> tuple[list[float], int]:
    """Rank one ordinal block with average ranks for tied grades.

    :param values: Grade values where smaller values are better.
    :return: Average rank for every original position and Friedman tie term.
    """
    ranked_indices = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    tie_term = 0
    start = 0
    while start < len(ranked_indices):
        end = start + 1
        value = values[ranked_indices[start]]
        while (
            end < len(ranked_indices) and values[ranked_indices[end]] == value
        ):
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for index in ranked_indices[start:end]:
            ranks[index] = average_rank
        tie_size = end - start
        tie_term += tie_size**3 - tie_size
        start = end
    return ranks, tie_term
