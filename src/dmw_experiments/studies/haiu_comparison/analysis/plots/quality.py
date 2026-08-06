"""Historian quality-review figures for the Haiu comparison."""

from __future__ import annotations

from typing import Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text

import dmw_experiments.shared.analysis as ut
from dmw_experiments.studies.haiu_comparison.analysis.quality.errors import (
    QualityErrorAnalysis,
)
from dmw_experiments.studies.haiu_comparison.analysis.quality.grades import (
    CONDITION_ORDER,
    QUALITY_COMPARISONS,
    QualityGradeAnalysis,
)
from dmw_experiments.studies.haiu_comparison.analysis.plots.results import (
    DIRECT_PAIR_ENDPOINTS,
    DIRECT_PAIR_ENDPOINT_LABELS,
    ERROR_ASSERTION_BAND_COLORS,
    ERROR_COUNT_CHANGE_COLORS,
    ERROR_COUNT_CHANGE_LABELS,
    ERROR_COUNT_SEGMENT_ANNOTATION_MINIMUM_SHARE,
    ERROR_INTERPRETATION_BAND_COLORS,
    ERROR_PROFILE_FIGURE_SIZE,
    FALSE_ASSIGNMENT_BAR_WIDTH,
    FIGURE_FONTSIZE,
    GRADE_CHANGE_LABELS,
    GRADE_COLORS,
    GRADE_LEGEND_LABELS,
    OUTCOME_COMPARISON_TICK_LABELS,
    PAIRED_COMPARISON_ENDPOINT_ORDER,
    PAIRED_COMPARISON_ENDPOINTS,
    PAIRED_GRADE_FIGURE_SIZE,
    PAIR_TRAJECTORY_LINE_ALPHA,
    PROVIDER_INTERACTION_FIGURE_SIZE,
    QUALITY_PAIR_SHEETS,
    _bar_rows,
    _configure_paired_comparison_axis,
    _empty_panel,
    _finish_figure,
    _plot_paired_trajectory_points,
    _trajectory_jitter,
    _trajectory_unit_column,
    _with_trajectory_jitter,
)


def _plot_quality_grade_overview(
    analysis: QualityGradeAnalysis,
    *,
    status_text: str,
) -> Figure:
    """Plot the grade distribution and pooled paired grade changes.

    :param analysis: Validated and pre-calculated historian-grade tables.
    :param status_text: Evidence-status subtitle retained by figure formatting.
    :return: Two-panel historian-quality figure.
    """
    figure, axes = plt.subplots(
        1,
        2,
        figsize=PAIRED_GRADE_FIGURE_SIZE,
        squeeze=False,
    )
    flat_axes = axes.ravel()
    _plot_grade_distribution(
        flat_axes[0],
        analysis=analysis,
        title="A. Grade distribution",
    )
    _plot_pair_change_distribution(
        flat_axes[1],
        distribution=analysis.pooled_grade_change_distribution,
        pair_data=analysis.direct_duel_pairs,
        sample_value_column="first_grade",
        title="B. Paired grade changes",
        ylabel="Share of matched pairs",
    )
    _finish_figure(
        figure,
        flat_axes,
        status_text=f"{status_text} · completed grades only; direct pairs only",
        provider_count=0,
        layout_top=0.55,
        layout_bottom=0.1245,
        subplot_wspace=0.4,
        show_legend=False,
    )
    # > ``tight_layout`` reserves extra space for the shared n annotations.
    # > Restore the specified 2 in panel height after those annotations settle.
    figure.subplots_adjust(
        left=0.12,
        right=0.98,
        bottom=0.1245,
        top=0.55,
        wspace=0.4,
    )
    _add_grade_distribution_legend(figure)
    _add_paired_change_legend(figure)
    for axis in flat_axes:
        ut.ensure_top_text_headroom(axis, axis.texts)
    return figure


def _plot_pairwise_quality_grade_trajectories(
    ax: Axes,
    *,
    analysis: QualityGradeAnalysis,
    provider_order: list[str],
    palette: dict[str, str],
) -> None:
    """Draw one trajectory for every valid planned quality comparison.

    DMW versus DMW + Haiu RAG and DMW + Haiu RAG versus standalone Haiu RAG
    occupy independent endpoint pairs. A complete three-condition review group
    contributes one line to each direct comparison; it never creates a DMW
    versus standalone-Haiu trajectory.

    :param ax: Axis receiving the matched grade trajectories.
    :param analysis: Validated historian-grade calculation tables.
    :param provider_order: Provider labels in display order.
    :param palette: Provider colors keyed by display label.
    :return: None after rendering the panel.
    """
    panel_data = _quality_pair_grade_panel_data(analysis.direct_duel_pairs)
    if panel_data.empty:
        _empty_panel(ax, "A. Pairwise matched quality grades")
        return
    plotted_providers = [
        provider_label
        for provider_label in provider_order
        if provider_label in set(panel_data["provider_label"].astype(str))
    ]
    sns.lineplot(
        data=panel_data,
        x="plot_x",
        y="grade",
        hue="provider_label",
        units=_trajectory_unit_column(panel_data),
        estimator=None,
        sort=True,
        hue_order=plotted_providers,
        palette=palette,
        alpha=PAIR_TRAJECTORY_LINE_ALPHA,
        linewidth=0.5,
        ax=ax,
    )
    _plot_paired_trajectory_points(
        ax,
        panel_data=panel_data,
        metric="grade",
        provider_order=plotted_providers,
        palette=palette,
    )
    ax.set_title("A. Pairwise matched quality grades")
    ax.set_xlabel("")
    ax.set_ylabel("Grade (1 best, 6 worst)")
    _configure_paired_comparison_axis(
        ax,
        tick_labels=OUTCOME_COMPARISON_TICK_LABELS,
    )
    ax.set_ylim(0.5, 6.5)
    ax.set_yticks(range(1, 7))
    ax.set_box_aspect(0.95)
    ut.apply_grid(ax)
    _annotate_grade_trajectory_panel(
        ax,
        panel_data=panel_data,
        provider_order=plotted_providers,
        palette=palette,
    )


def _quality_pair_grade_panel_data(
    direct_duel_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Expand quality duels into independent, two-endpoint trajectories.

    :param direct_duel_pairs: Auditable paired-grade rows for the two planned
        comparisons.
    :return: Jittered endpoint rows ready for Seaborn lines and centralized
        annotations. A regest may contribute to both planned comparisons.
    """
    columns = (
        "provider_label",
        "regest_id",
        "comparison",
        "pair_side",
        "grade",
        "plot_x",
        "endpoint_label",
        "trajectory_id",
    )
    frames: list[pd.DataFrame] = []
    for (
        first_condition,
        second_condition,
    ), comparison in QUALITY_PAIR_SHEETS.items():
        pair_rows = direct_duel_pairs.loc[
            (direct_duel_pairs["first_condition"] == first_condition)
            & (direct_duel_pairs["second_condition"] == second_condition)
        ]
        if pair_rows.empty:
            continue
        left = pair_rows.loc[
            :, ["provider_label", "regest_id", "first_grade"]
        ].rename(columns={"first_grade": "grade"})
        left["comparison"] = comparison
        left["pair_side"] = "left"
        right = pair_rows.loc[
            :, ["provider_label", "regest_id", "second_grade"]
        ].rename(columns={"second_grade": "grade"})
        right["comparison"] = comparison
        right["pair_side"] = "right"
        frames.extend((left, right))
    if not frames:
        return ut.empty_frame(columns)
    panel_data = pd.concat(frames, ignore_index=True)
    endpoint_mapping = panel_data.apply(
        lambda row: PAIRED_COMPARISON_ENDPOINTS[
            (row["comparison"], row["pair_side"])
        ],
        axis="columns",
    )
    panel_data["plot_x"] = endpoint_mapping.map(lambda value: value[0])
    panel_data["endpoint_label"] = endpoint_mapping.map(lambda value: value[1])
    panel_data["trajectory_id"] = (
        ut.series_column(panel_data, "provider_label").astype(str)
        + "\x00"
        + ut.series_column(panel_data, "regest_id").astype(str)
        + "\x00"
        + ut.series_column(panel_data, "comparison").astype(str)
    )
    return _with_trajectory_jitter(
        panel_data,
        trajectory_column="trajectory_id",
    )


def _annotate_grade_trajectory_panel(
    ax: Axes,
    *,
    panel_data: pd.DataFrame,
    provider_order: list[str],
    palette: dict[str, str],
) -> None:
    """Add the shared mean and denominator annotations to grade trajectories.

    :param ax: Axis receiving the centralized annotation bands.
    :param panel_data: Long-form grade trajectories with paired endpoints.
    :param provider_order: Provider labels in display order.
    :param palette: Provider colors keyed by display label.
    :return: None after adding mean and count annotations.
    """
    annotation_data = panel_data.copy()
    annotation_data["endpoint_label"] = annotation_data[
        "endpoint_label"
    ].astype(str)
    annotation_base_ylim = ax.get_ylim()
    for line_index, provider_label in enumerate(provider_order):
        provider_data = annotation_data.loc[
            ut.series_column(annotation_data, "provider_label")
            == provider_label
        ]
        ut.annotate_xaxis_group_statistic(
            ax,
            data=provider_data,
            x="endpoint_label",
            y="grade",
            x_order=PAIRED_COMPARISON_ENDPOINT_ORDER,
            statistic="mean",
            color=palette[provider_label],
            label="µ:",
            label_color=palette[provider_label],
            value_formatter=lambda value: f"{value:.2f}",
            base_ylim=annotation_base_ylim,
            clearance_anchor=1.0,
            line_index=line_index,
            line_spacing_points=8.0,
            fontsize=FIGURE_FONTSIZE,
            minimum_visible_y=0.5,
        )
    ut.annotate_xaxis_group_statistic(
        ax,
        data=annotation_data,
        x="endpoint_label",
        y="grade",
        x_order=PAIRED_COMPARISON_ENDPOINT_ORDER,
        statistic="count",
        hue="provider_label",
        hue_order=provider_order,
        palette=palette,
        label="n:",
        value_formatter=lambda value: str(int(value)),
        base_ylim=(ax.get_ylim()[0], annotation_base_ylim[1]),
        placement="top",
        box_width=0.5,
        fontsize=FIGURE_FONTSIZE,
    )


def _plot_grade_distribution(
    ax: Axes,
    *,
    analysis: QualityGradeAnalysis,
    title: str,
) -> None:
    """Render the ordinal grade distribution at paired-comparison endpoints.

    :param ax: Axis receiving stacked grade-share bars.
    :param analysis: Validated historian-grade calculation tables. The paired
        distribution repeats DMW + Haiu RAG because its two direct
        comparisons have distinct valid populations.
    :param title: Lettered reader-facing panel title.
    :return: None after rendering the panel.
    """
    distribution = analysis.paired_grade_distribution
    if distribution.empty:
        _empty_panel(ax, title)
        return
    panel_data = _direct_pair_endpoint_data(distribution)
    endpoint_order = tuple(
        endpoint
        for endpoint in DIRECT_PAIR_ENDPOINT_LABELS
        if endpoint in set(panel_data["endpoint_label"])
    )
    positions = np.array(
        [
            float(
                panel_data.loc[
                    panel_data["endpoint_label"] == endpoint,
                    "plot_x",
                ].iloc[0]
            )
            for endpoint in endpoint_order
        ]
    )
    cumulative = np.zeros(len(endpoint_order))
    for grade in range(1, 7):
        shares = np.array(
            [
                float(
                    panel_data.loc[
                        (panel_data["endpoint_label"] == endpoint)
                        & (panel_data["grade"] == grade),
                        "share",
                    ].iloc[0]
                )
                for endpoint in endpoint_order
            ]
        )
        counts = np.array(
            [
                int(
                    panel_data.loc[
                        (panel_data["endpoint_label"] == endpoint)
                        & (panel_data["grade"] == grade),
                        "count",
                    ].iloc[0]
                )
                for endpoint in endpoint_order
            ]
        )
        bars = ax.bar(
            positions,
            shares,
            bottom=cumulative,
            color=GRADE_COLORS[grade],
            edgecolor="white",
            linewidth=0.45,
            width=0.68,
        )
        ax.bar_label(
            bars,
            labels=[
                str(count)
                if share >= ERROR_COUNT_SEGMENT_ANNOTATION_MINIMUM_SHARE
                else ""
                for count, share in zip(counts, shares, strict=True)
            ],
            label_type="center",
            color=("#1F1F1F" if grade in {2, 3, 4} else "white"),
            fontsize=FIGURE_FONTSIZE - 1,
            fontweight="bold",
            padding=0,
        )
        cumulative += shares
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("Share of paired models")
    ut.configure_percent_axis(ax, ymin=0, ymax=1.0, major_max=1.0)
    ut.apply_grid(ax)
    _configure_direct_pair_endpoint_axis(ax)
    paired_grades = _quality_pair_grade_panel_data(analysis.direct_duel_pairs)
    ut.annotate_xaxis_group_statistic(
        ax,
        data=paired_grades,
        x="endpoint_label",
        y="grade",
        x_order=PAIRED_COMPARISON_ENDPOINT_ORDER,
        statistic="count",
        label="n:",
        value_formatter=lambda value: str(int(value)),
        base_ylim=(0.0, 1.0),
        placement="top",
        box_width=0.6,
        fontsize=FIGURE_FONTSIZE,
    )


def _add_grade_distribution_legend(figure: Figure) -> None:
    """Add the six-row ordinal-grade color key above Panel A.

    :param figure: Two-panel grade figure receiving the reserved top-band key.
    :return: None after adding the local grade key.
    """
    legend_axis = figure.add_axes((0.04, 0.60, 0.48, 0.36))
    legend = ut.add_top_band_figure_legend(
        figure,
        legend_axis,
        handles=[
            Rectangle(
                (0, 0),
                1,
                1,
                facecolor=GRADE_COLORS[grade],
                edgecolor="none",
            )
            for grade in range(1, 7)
        ],
        labels=[GRADE_LEGEND_LABELS[grade] for grade in range(1, 7)],
        ncol=1,
        frameon=False,
        show_handles=True,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.0),
    )
    for text in legend.get_texts():
        text.set_fontsize(FIGURE_FONTSIZE - 1)


def _add_paired_change_legend(figure: Figure) -> None:
    """Place the pooled improved/unchanged/worsened key above Panel B.

    :param figure: Two-panel grade figure receiving the shared direction key.
    :return: None after adding the compact top-band legend.
    """
    legend_axis = figure.add_axes((0.58, 0.80, 0.38, 0.05))
    handles = [
        Rectangle(
            (0, 0),
            1,
            1,
            facecolor=ERROR_COUNT_CHANGE_COLORS[direction],
            edgecolor="none",
        )
        for direction in ERROR_COUNT_CHANGE_COLORS
    ]
    ut.add_top_band_figure_legend(
        figure,
        legend_axis,
        handles=handles,
        labels=[
            GRADE_CHANGE_LABELS[direction]
            for direction in ERROR_COUNT_CHANGE_COLORS
        ],
        ncol=3,
        frameon=False,
        show_handles=True,
    )


def _plot_false_assignment_incidence(
    ax: Axes,
    *,
    analysis: QualityGradeAnalysis,
    provider_order: list[str],
    palette: dict[str, str],
) -> list[Text]:
    """Compare provider-specific incidence of rubric-defined false assignments.

    Grades 4–6 contain at least one false assignment under the historian
    rubric. DMW + Haiu RAG is deliberately repeated at the two direct-pair
    endpoints so the bar plot matches Panel A's paired-comparison layout.

    :param ax: Axis receiving the provider-hued incidence bars.
    :param analysis: Validated historian-grade calculation tables.
    :param provider_order: Provider labels in display order.
    :param palette: Provider colors keyed by display label.
    :return: Numerator/denominator annotation artists for final headroom.
    """
    panel_data = _false_assignment_incidence_panel_data(
        analysis.false_assignment_pair_summary
    )
    if panel_data.empty:
        _empty_panel(ax, "C. False-assignment incidence")
        return []
    plotted_providers = [
        provider_label
        for provider_label in provider_order
        if provider_label
        in set(ut.series_column(panel_data, "provider_label").astype(str))
    ]
    sns.barplot(
        data=panel_data,
        x="endpoint_label",
        y="false_assignment_share",
        hue="provider_label",
        order=PAIRED_COMPARISON_ENDPOINT_ORDER,
        hue_order=plotted_providers,
        palette=palette,
        errorbar=None,
        width=FALSE_ASSIGNMENT_BAR_WIDTH,
        ax=ax,
    )
    bar_rows = _bar_rows(
        panel_data,
        category_column="endpoint_label",
        category_order=list(PAIRED_COMPARISON_ENDPOINT_ORDER),
        provider_order=plotted_providers,
    )
    annotation_specs: list[tuple[float, float, str]] = []
    bar_patches = [
        patch
        for patch in ax.patches
        if isinstance(patch, Rectangle) and patch.get_width() > 0
    ]
    for patch, row in zip(bar_patches, bar_rows, strict=True):
        incidence = float(row["false_assignment_share"])
        lower = float(row["wilson_95_lower_share"])
        upper = float(row["wilson_95_upper_share"])
        ax.errorbar(
            patch.get_x() + (patch.get_width() / 2.0),
            incidence,
            yerr=[[incidence - lower], [upper - incidence]],
            fmt="none",
            ecolor="#4D4D4D",
            elinewidth=0.8,
            capsize=2.0,
            capthick=0.8,
            alpha=1.0,
            zorder=3.0,
        )
        bar_center = patch.get_x() + (patch.get_width() / 2.0)
        annotation_specs.append(
            (
                bar_center,
                upper,
                f"{int(row['false_assignment_count'])}/{int(row['models'])}",
            )
        )
    label_texts = ut.annotate_labels(
        ax,
        annotation_specs,
        fontsize=FIGURE_FONTSIZE - 1,
        fontweight="bold",
        colors=["#333333"] * len(annotation_specs),
    )
    for text in label_texts:
        text.set_zorder(3.2)
    ax.set_title("C. False-assignment incidence")
    ax.set_xlabel("")
    ax.set_ylabel("Share of analyses\nwith ≥1 false assignment")
    _configure_paired_comparison_axis(ax)
    ut.configure_percent_axis(
        ax,
        ymin=0,
        ymax=1.0,
        major_max=1.0,
        major_step=0.1,
        major_step_for_label=1,
    )
    ut.apply_grid(ax)
    return label_texts


def _false_assignment_incidence_panel_data(
    false_assignment_pair_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Place matched false-assignment rates at paired-comparison endpoints.

    :param false_assignment_pair_summary: Provider-, comparison-, and
        condition-specific false-assignment calculations with Wilson bounds.
    :return: Long-form endpoint rows for a four-position paired bar plot.
    """
    if false_assignment_pair_summary.empty:
        return ut.empty_frame(
            [
                "provider_label",
                "condition",
                "endpoint_label",
                "models",
                "false_assignment_count",
                "false_assignment_share",
                "wilson_95_lower_share",
                "wilson_95_upper_share",
            ]
        )
    panel_data = false_assignment_pair_summary.copy()
    endpoint_mapping = panel_data.apply(
        lambda row: PAIRED_COMPARISON_ENDPOINTS[
            (
                QUALITY_PAIR_SHEETS[
                    (row["first_condition"], row["second_condition"])
                ],
                row["pair_side"],
            )
        ],
        axis="columns",
    )
    panel_data["plot_x"] = endpoint_mapping.map(lambda value: value[0])
    panel_data["endpoint_label"] = endpoint_mapping.map(lambda value: value[1])
    return panel_data


def _plot_false_assignment_error_profile(
    analysis: QualityErrorAnalysis,
) -> Figure:
    """Plot pooled matched false-assignment profiles and paired changes.

    Every pair is first formed within the same provider and regest. The figure
    then pools those valid provider-local pairs, which improves readability
    without creating an invalid AcademicCloud-to-LM-Studio comparison. Exact
    atomic assertions and independent false interpretations retain separate
    pair populations because the review fields are optional.

    :param analysis: Validated historian false-assignment count tables.
    :return: Four-panel pooled direct-pair false-assignment figure.
    """
    figure = plt.figure(figsize=ERROR_PROFILE_FIGURE_SIZE)
    grid = figure.add_gridspec(1, 4)
    axes = (
        figure.add_subplot(grid[0, 0]),
        figure.add_subplot(grid[0, 1]),
        figure.add_subplot(grid[0, 2]),
        figure.add_subplot(grid[0, 3]),
    )
    _plot_error_count_incidence(
        axes[0],
        incidence=analysis.pooled_interpretation_incidence,
        pairs=analysis.matched_interpretation_pairs,
        value_column="false_interpretations",
        ylabel="Share of matched models",
        title="A. Independent false\ninterpretations",
    )
    _plot_error_count_incidence(
        axes[1],
        incidence=analysis.pooled_assertion_incidence,
        pairs=analysis.matched_assertion_pairs,
        value_column="false_assertions",
        ylabel=None,
        title="B. False atomic\nassertions",
        band_colors=ERROR_ASSERTION_BAND_COLORS,
    )
    _plot_pair_change_distribution(
        axes[2],
        distribution=analysis.pooled_interpretation_change_distribution,
        pair_data=analysis.interpretation_pair_differences,
        sample_value_column="error_count_difference",
        title="C. Paired interpretation\nchanges",
        ylabel="Share of matched pairs",
    )
    _plot_pair_change_distribution(
        axes[3],
        distribution=analysis.pooled_assertion_change_distribution,
        pair_data=analysis.assertion_pair_differences,
        sample_value_column="error_count_difference",
        title="D. Paired false-assertion\nchanges",
        ylabel=None,
    )
    figure.subplots_adjust(
        left=0.065,
        right=0.99,
        bottom=0.18,
        top=0.67,
        wspace=0.46,
    )
    _add_error_profile_legends(figure)
    return figure


def _has_error_profile_pairs(analysis: QualityErrorAnalysis) -> bool:
    """Check whether either count measure has a valid direct pair to plot.

    :param analysis: Validated historian false-assignment count tables.
    :return: Whether a pooled profile has at least one provider-local pair.
    """
    return any(
        not pairs.empty
        for pairs in (
            analysis.matched_interpretation_pairs,
            analysis.matched_assertion_pairs,
        )
    )


def _plot_error_count_incidence(
    ax: Axes,
    *,
    incidence: pd.DataFrame,
    pairs: pd.DataFrame,
    value_column: str,
    ylabel: str | None,
    title: str,
    band_colors: Mapping[str, str] = ERROR_INTERPRETATION_BAND_COLORS,
) -> None:
    """Render pooled direct-pair count bands as stacked endpoint bars.

    :param ax: Axis receiving four paired-comparison endpoint bars.
    :param incidence: Pooled direct-pair rows in the four error-count bands.
    :param pairs: Raw direct provider–regest pairs for sample-size annotation.
    :param value_column: Numeric pair field counted by the n annotation.
    :param ylabel: Optional reader-facing share-axis title.
    :param title: Lettered panel title.
    :param band_colors: Display color keyed by every count band in incidence.
    :return: None after drawing the stacked distributions.
    """
    if incidence.empty:
        _empty_panel(ax, title)
        return
    panel_data = _direct_pair_endpoint_data(incidence)
    endpoint_order = tuple(
        endpoint
        for endpoint in DIRECT_PAIR_ENDPOINT_LABELS
        if endpoint in set(panel_data["endpoint_label"])
    )
    positions = np.array(
        [
            float(
                panel_data.loc[
                    panel_data["endpoint_label"] == endpoint,
                    "plot_x",
                ].iloc[0]
            )
            for endpoint in endpoint_order
        ]
    )
    cumulative = np.zeros(len(endpoint_order), dtype=float)
    for band, color in band_colors.items():
        shares = np.array(
            [
                float(
                    panel_data.loc[
                        (panel_data["endpoint_label"] == endpoint)
                        & (panel_data["error_count_band"] == band),
                        "share",
                    ].iloc[0]
                )
                for endpoint in endpoint_order
            ]
        )
        counts = np.array(
            [
                int(
                    panel_data.loc[
                        (panel_data["endpoint_label"] == endpoint)
                        & (panel_data["error_count_band"] == band),
                        "count",
                    ].iloc[0]
                )
                for endpoint in endpoint_order
            ]
        )
        bars = ax.bar(
            positions,
            shares,
            bottom=cumulative,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            width=0.68,
        )
        ax.bar_label(
            bars,
            labels=[
                str(count)
                if share >= ERROR_COUNT_SEGMENT_ANNOTATION_MINIMUM_SHARE
                else ""
                for count, share in zip(counts, shares, strict=True)
            ],
            label_type="center",
            color=("#1F1F1F" if band in {"1", "2"} else "white"),
            fontsize=FIGURE_FONTSIZE - 1,
            fontweight="bold",
            padding=0,
        )
        cumulative += shares
    raw_panel_data = _error_profile_pair_panel_data(
        pairs,
        value_column=value_column,
    )
    ax.set_title(title)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ut.configure_percent_axis(ax, ymin=0.0, ymax=1.0, major_max=1.0)
    ut.apply_grid(ax)
    _configure_direct_pair_endpoint_axis(ax)
    ut.annotate_xaxis_group_statistic(
        ax,
        data=raw_panel_data,
        x="endpoint_label",
        y=value_column,
        x_order=tuple(DIRECT_PAIR_ENDPOINT_LABELS),
        statistic="count",
        label="n:",
        value_formatter=lambda value: str(int(value)),
        base_ylim=ax.get_ylim(),
        placement="top",
        fontsize=FIGURE_FONTSIZE - 1,
        minimum_visible_y=0.0,
    )


def _plot_pair_change_distribution(
    ax: Axes,
    *,
    distribution: pd.DataFrame,
    pair_data: pd.DataFrame,
    sample_value_column: str,
    title: str,
    ylabel: str | None,
) -> None:
    """Render pooled direct-pair improvements, ties, and deteriorations.

    :param ax: Axis receiving two planned direct-comparison bars.
    :param distribution: Precalculated pooled pair counts and shares by change
        direction.
    :param pair_data: Raw direct pairs used for the matched n annotations.
    :param sample_value_column: Populated pair field used only to count the
        direct matched denominator above each comparison.
    :param title: Lettered panel title.
    :param ylabel: Optional reader-facing share-axis title.
    :return: None after drawing the mutually exclusive paired-change bars.
    """
    if distribution.empty:
        _empty_panel(ax, title)
        return
    comparison_order = tuple(
        comparison.key
        for comparison in QUALITY_COMPARISONS
        if comparison.key in set(distribution["comparison"])
    )
    positions = np.arange(len(comparison_order), dtype=float)
    cumulative = np.zeros(len(comparison_order), dtype=float)
    for direction, color in ERROR_COUNT_CHANGE_COLORS.items():
        shares: list[float] = []
        counts: list[int] = []
        for comparison in comparison_order:
            row = distribution.loc[
                (distribution["comparison"] == comparison)
                & (distribution["change_direction"] == direction)
            ].iloc[0]
            shares.append(float(row["share"]))
            counts.append(int(row["count"]))
        share_values = np.array(shares)
        ax.bar(
            positions,
            share_values,
            bottom=cumulative,
            width=0.62,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            label=ERROR_COUNT_CHANGE_LABELS[direction],
        )
        for position, count, share, bottom in zip(
            positions,
            counts,
            share_values,
            cumulative,
            strict=True,
        ):
            if count:
                ax.text(
                    position,
                    bottom + (share / 2.0),
                    str(count),
                    ha="center",
                    va="center",
                    fontsize=FIGURE_FONTSIZE - 1,
                    fontweight="bold",
                    color=("#1F1F1F" if direction == "unchanged" else "white"),
                    zorder=4,
                )
        cumulative += share_values
    ax.set_title(title)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ut.configure_percent_axis(ax, ymin=0.0, ymax=1.0, major_max=1.0)
    ut.set_fixed_x_ticklabels(
        ax,
        tuple(
            OUTCOME_COMPARISON_TICK_LABELS[index]
            for index, comparison in enumerate(QUALITY_COMPARISONS)
            if comparison.key in comparison_order
        ),
        positions=tuple(positions),
    )
    ut.apply_grid(ax)
    ut.annotate_xaxis_group_statistic(
        ax,
        data=pair_data,
        x="comparison",
        y=sample_value_column,
        x_order=comparison_order,
        statistic="count",
        label="n:",
        value_formatter=lambda value: str(int(value)),
        base_ylim=ax.get_ylim(),
        placement="top",
        fontsize=FIGURE_FONTSIZE - 1,
        minimum_visible_y=0.0,
    )


def _error_profile_pair_panel_data(
    pairs: pd.DataFrame,
    *,
    value_column: str,
) -> pd.DataFrame:
    """Expand direct pair values into jittered two-endpoint trajectories.

    :param pairs: Direct pair rows for one count metric.
    :param value_column: Count field stored as ``first_<field>`` and
        ``second_<field>`` in ``pairs``.
    :return: Long-form endpoints, one connected trajectory per provider,
        direct comparison, and regest.
    """
    columns = (
        "provider_label",
        "regest_id",
        "comparison",
        "pair_side",
        "condition",
        value_column,
        "plot_x",
        "endpoint_label",
        "trajectory_id",
    )
    if pairs.empty:
        return ut.empty_frame(columns)
    frames: list[pd.DataFrame] = []
    for side in ("first", "second"):
        frame = pairs.loc[
            :,
            (
                "provider_label",
                "regest_id",
                "comparison",
                f"{side}_condition",
                f"{side}_{value_column}",
            ),
        ].rename(
            columns={
                f"{side}_condition": "condition",
                f"{side}_{value_column}": value_column,
            }
        )
        frame["pair_side"] = side
        frames.append(frame)
    panel_data = pd.concat(frames, ignore_index=True)
    endpoint_mapping = panel_data.apply(
        lambda row: DIRECT_PAIR_ENDPOINTS[
            (str(row["comparison"]), str(row["pair_side"]))
        ],
        axis="columns",
    )
    panel_data["plot_x"] = endpoint_mapping.map(lambda value: value[0])
    panel_data["endpoint_label"] = endpoint_mapping.map(lambda value: value[1])
    panel_data["trajectory_id"] = (
        panel_data["provider_label"].astype(str)
        + "\x00"
        + panel_data["regest_id"].astype(str)
        + "\x00"
        + panel_data["comparison"].astype(str)
    )
    return _with_trajectory_jitter(
        panel_data,
        trajectory_column="trajectory_id",
    ).loc[:, columns]


def _direct_pair_endpoint_data(panel_data: pd.DataFrame) -> pd.DataFrame:
    """Attach common direct-comparison positions to summary endpoints.

    :param panel_data: Direct-pair summary rows with comparison and pair side.
    :return: Rows with their stable endpoint positions and display identities.
    """
    result = panel_data.copy()
    endpoint_mapping = result.apply(
        lambda row: DIRECT_PAIR_ENDPOINTS[
            (str(row["comparison"]), str(row["pair_side"]))
        ],
        axis="columns",
    )
    result["plot_x"] = endpoint_mapping.map(lambda value: value[0])
    result["endpoint_label"] = endpoint_mapping.map(lambda value: value[1])
    return result


def _configure_direct_pair_endpoint_axis(ax: Axes) -> None:
    """Show four direct-pair endpoints without redundant comparison labels.

    :param ax: Subplot receiving the shared direct-pair endpoint axis.
    :return: None after adding endpoint labels and the comparison divider.
    """
    endpoint_order = tuple(DIRECT_PAIR_ENDPOINT_LABELS)
    positions = tuple(range(len(endpoint_order)))
    ax.set_xlim(-0.5, 3.5)
    ax.set_xticks(
        positions,
        [DIRECT_PAIR_ENDPOINT_LABELS[endpoint] for endpoint in endpoint_order],
        fontsize=FIGURE_FONTSIZE - 2,
    )
    ax.axvline(
        1.5,
        color="#B0B0B0",
        linewidth=0.5,
        linestyle=":",
        zorder=0,
    )


def _add_error_profile_legends(figure: Figure) -> None:
    """Add one shared count-band key and a paired-change key above the figure.

    :param figure: Figure receiving compact reader-facing legends.
    :return: None after adding the two top-band legends.
    """
    count_legend_axis = figure.add_axes((0.12, 0.90, 0.76, 0.045))
    count_handles = [
        Rectangle(
            (0, 0),
            1,
            1,
            facecolor=color,
            edgecolor="none",
        )
        for color in (
            ERROR_INTERPRETATION_BAND_COLORS["0"],
            ERROR_INTERPRETATION_BAND_COLORS["1"],
            ERROR_INTERPRETATION_BAND_COLORS["2"],
            ERROR_INTERPRETATION_BAND_COLORS["3+"],
            ERROR_ASSERTION_BAND_COLORS["4+"],
        )
    ]
    ut.add_top_band_figure_legend(
        figure,
        count_legend_axis,
        handles=count_handles,
        labels=(
            "0 errors",
            "1 error",
            "2 errors",
            "3/3+ errors",
            "4+ errors",
        ),
        ncol=5,
        frameon=False,
        show_handles=True,
    )
    direction_legend_axis = figure.add_axes((0.55, 0.80, 0.41, 0.045))
    direction_handles = [
        Rectangle(
            (0, 0),
            1,
            1,
            facecolor=ERROR_COUNT_CHANGE_COLORS[direction],
            edgecolor="none",
        )
        for direction in ERROR_COUNT_CHANGE_COLORS
    ]
    ut.add_top_band_figure_legend(
        figure,
        direction_legend_axis,
        handles=direction_handles,
        labels=[
            ERROR_COUNT_CHANGE_LABELS[direction]
            for direction in ERROR_COUNT_CHANGE_COLORS
        ],
        ncol=3,
        frameon=False,
        show_handles=True,
    )


def _plot_quality_grade_provider_interaction(
    analysis: QualityGradeAnalysis,
    *,
    provider_order: list[str],
    palette: dict[str, str],
    status_text: str,
) -> Figure | None:
    """Plot matched grade and false-assignment provider interactions.

    :param analysis: Validated historian-grade calculation tables.
    :param provider_order: Provider labels in display order.
    :param palette: Provider colors keyed by display label.
    :param status_text: Evidence-status subtitle retained by figure formatting.
    :return: Exploratory two-row interaction figure, or ``None`` when no
        two-provider complete regesta are available.
    """
    pairs = analysis.provider_interaction_pairs
    if pairs.empty:
        return None
    provider_pairs = pairs.loc[
        :, ["first_provider", "second_provider"]
    ].drop_duplicates()
    if len(provider_pairs) != 1:
        return None
    first_provider, second_provider = provider_pairs.iloc[0]
    display_order = [
        provider_label
        for provider_label in provider_order
        if provider_label in {first_provider, second_provider}
    ]
    if len(display_order) != 2:
        display_order = [str(first_provider), str(second_provider)]
    figure, axes = plt.subplots(
        2,
        len(CONDITION_ORDER),
        figsize=PROVIDER_INTERACTION_FIGURE_SIZE,
        sharey="row",
        squeeze=False,
    )
    for condition_index, condition in enumerate(CONDITION_ORDER):
        condition_pairs = pairs.loc[pairs["condition"] == condition]
        grade_axis = axes[0, condition_index]
        grade_panel_data = _provider_interaction_panel_data(
            condition_pairs,
            provider_order=display_order,
        )
        _plot_provider_interaction_trajectories(
            grade_axis,
            panel_data=grade_panel_data,
            provider_order=display_order,
            palette=palette,
        )
        _plot_provider_interaction_central_trend(
            grade_axis,
            trend_data=_provider_grade_trend_panel_data(
                analysis.provider_interaction_trend_summary,
                condition=condition,
            ),
            provider_order=display_order,
            estimate_column="mean_grade",
            lower_column="bootstrap_95_lower_mean_grade",
            upper_column="bootstrap_95_upper_mean_grade",
        )
        grade_axis.set_title(
            {
                "workflow_full_ontology": "DMW full",
                "workflow_rag": "DMW + Haiu",
                "haiu_rag_ontologizer": "Standalone Haiu",
            }[condition]
        )
        _configure_provider_interaction_axis(
            grade_axis,
            provider_order=display_order,
        )
        grade_axis.set_ylim(0.5, 6.5)
        grade_axis.set_yticks(range(1, 7))
        ut.apply_grid(grade_axis)
        grade_summary = analysis.provider_interaction_summary.loc[
            analysis.provider_interaction_summary["condition"] == condition
        ]
        _annotate_provider_interaction_test(
            grade_axis,
            summary=grade_summary,
            p_value_column="exact_sign_test_p_value",
            tested_pairs_column="exact_sign_test_non_tied_pairs",
            tested_pairs_name="non-tied",
            test_name="sign test",
        )

        false_assignment_axis = axes[1, condition_index]
        false_assignment_panel_data = _provider_false_assignment_panel_data(
            condition_pairs,
            provider_order=display_order,
        )
        _plot_provider_interaction_trajectories(
            false_assignment_axis,
            panel_data=false_assignment_panel_data,
            provider_order=display_order,
            palette=palette,
        )
        _plot_provider_interaction_central_trend(
            false_assignment_axis,
            trend_data=_provider_false_assignment_trend_panel_data(
                analysis.provider_false_assignment_interaction_summary,
                condition=condition,
                provider_order=display_order,
            ),
            provider_order=display_order,
            estimate_column="false_assignment_share",
            lower_column="wilson_95_lower_share",
            upper_column="wilson_95_upper_share",
        )
        _configure_provider_interaction_axis(
            false_assignment_axis,
            provider_order=display_order,
        )
        false_assignment_axis.set_ylim(-0.12, 1.12)
        false_assignment_axis.set_yticks((0, 1), ("No", "≥1 false\nassignment"))
        ut.apply_grid(false_assignment_axis)
        false_assignment_summary = (
            analysis.provider_false_assignment_interaction_summary.loc[
                analysis.provider_false_assignment_interaction_summary[
                    "condition"
                ]
                == condition
            ]
        )
        _annotate_provider_interaction_test(
            false_assignment_axis,
            summary=false_assignment_summary,
            p_value_column="exact_mcnemar_p_value",
            tested_pairs_column="exact_mcnemar_discordant_pairs",
            tested_pairs_name="discordant",
            test_name="McNemar test",
        )
    axes[0, 0].set_ylabel("A. Grade\n(1 best, 6 worst)")
    axes[1, 0].set_ylabel("B. False-assignment\nindicator and rate")
    _finish_figure(
        figure,
        axes,
        status_text=f"{status_text} · shared complete regesta only",
        provider_count=0,
        layout_top=0.99,
        layout_bottom=0.10,
        subplot_wspace=0.28,
        subplot_hspace=0.65,
        show_legend=False,
    )
    return figure


def _plot_provider_interaction_trajectories(
    ax: Axes,
    *,
    panel_data: pd.DataFrame,
    provider_order: list[str],
    palette: dict[str, str],
) -> None:
    """Draw low-emphasis paired regest trajectories behind a trend overlay.

    :param ax: Provider-interaction axis receiving individual trajectories.
    :param panel_data: Jittered two-provider values for one condition.
    :param provider_order: Provider labels in the displayed x-axis order.
    :param palette: Provider colors keyed by display label.
    :return: None after plotting individual paired evidence.
    """
    for _regest_id, regest_data in panel_data.groupby(
        "regest_id",
        sort=False,
    ):
        ax.plot(
            regest_data["plot_x"],
            regest_data["grade"],
            color="#7F7F7F",
            linewidth=0.5,
            alpha=PAIR_TRAJECTORY_LINE_ALPHA,
            zorder=1,
        )
    _plot_paired_trajectory_points(
        ax,
        panel_data=panel_data,
        metric="grade",
        provider_order=provider_order,
        palette=palette,
    )


def _provider_interaction_panel_data(
    pairs: pd.DataFrame,
    *,
    provider_order: list[str],
) -> pd.DataFrame:
    """Expand wide provider pairs into transparent-overlay point records.

    :param pairs: One-condition provider pair rows.
    :param provider_order: Two provider labels in x-axis order.
    :return: Long-form grade points with one shared jitter offset per regest.
    """
    positions = {
        provider_label: float(index)
        for index, provider_label in enumerate(provider_order)
    }
    records: list[dict[str, object]] = []
    for pair in pairs.to_dict(orient="records"):
        grades = {
            str(pair["first_provider"]): int(pair["first_provider_grade"]),
            str(pair["second_provider"]): int(pair["second_provider_grade"]),
        }
        regest_id = str(pair["regest_id"])
        offset = _trajectory_jitter("provider-interaction", regest_id)
        for provider_label in provider_order:
            records.append(
                {
                    "provider_label": provider_label,
                    "regest_id": regest_id,
                    "grade": grades[provider_label],
                    "plot_x": positions[provider_label] + offset,
                }
            )
    return ut.frame_from_records(
        records,
        columns=("provider_label", "regest_id", "grade", "plot_x"),
    ).sort_values(["regest_id", "plot_x"])


def _provider_false_assignment_panel_data(
    pairs: pd.DataFrame,
    *,
    provider_order: list[str],
) -> pd.DataFrame:
    """Convert paired grades into the rubric's binary false-assignment field.

    :param pairs: One-condition provider grade pairs.
    :param provider_order: Two provider labels in x-axis order.
    :return: Jittered binary endpoint records where one means at least one
        false assignment under the grade rubric.
    """
    false_assignment_pairs = pairs.copy()
    false_assignment_pairs["first_provider_grade"] = (
        false_assignment_pairs["first_provider_grade"] >= 4
    ).astype(int)
    false_assignment_pairs["second_provider_grade"] = (
        false_assignment_pairs["second_provider_grade"] >= 4
    ).astype(int)
    return _provider_interaction_panel_data(
        false_assignment_pairs,
        provider_order=provider_order,
    )


def _provider_grade_trend_panel_data(
    summary: pd.DataFrame,
    *,
    condition: str,
) -> pd.DataFrame:
    """Select one condition's paired-bootstrap grade trend endpoints.

    :param summary: All matched-provider grade trend calculations.
    :param condition: Canonical condition identifier shown in one panel.
    :return: Provider endpoint rows with descriptive mean-grade intervals.
    """
    return summary.loc[summary["condition"] == condition].copy()


def _provider_false_assignment_trend_panel_data(
    summary: pd.DataFrame,
    *,
    condition: str,
    provider_order: list[str],
) -> pd.DataFrame:
    """Expand one matched false-assignment summary into provider endpoints.

    :param summary: One-row-per-condition matched provider rate calculations.
    :param condition: Canonical condition identifier shown in one panel.
    :param provider_order: Provider labels in x-axis order.
    :return: Provider endpoint rows with Wilson 95% rate intervals.
    """
    rows = summary.loc[summary["condition"] == condition]
    if rows.empty:
        return ut.empty_frame(
            [
                "provider_label",
                "false_assignment_share",
                "wilson_95_lower_share",
                "wilson_95_upper_share",
            ]
        )
    row = rows.iloc[0]
    first_provider = str(row["first_provider"])
    second_provider = str(row["second_provider"])
    values = {
        first_provider: (
            row["first_provider_false_assignment_share"],
            row["first_provider_wilson_95_lower_share"],
            row["first_provider_wilson_95_upper_share"],
        ),
        second_provider: (
            row["second_provider_false_assignment_share"],
            row["second_provider_wilson_95_lower_share"],
            row["second_provider_wilson_95_upper_share"],
        ),
    }
    return ut.frame_from_records(
        [
            {
                "provider_label": provider_label,
                "false_assignment_share": values[provider_label][0],
                "wilson_95_lower_share": values[provider_label][1],
                "wilson_95_upper_share": values[provider_label][2],
            }
            for provider_label in provider_order
            if provider_label in values
        ],
        columns=(
            "provider_label",
            "false_assignment_share",
            "wilson_95_lower_share",
            "wilson_95_upper_share",
        ),
    )


def _plot_provider_interaction_central_trend(
    ax: Axes,
    *,
    trend_data: pd.DataFrame,
    provider_order: list[str],
    estimate_column: str,
    lower_column: str,
    upper_column: str,
) -> None:
    """Overlay a high-emphasis matched-provider trend and its 95% intervals.

    :param ax: Provider-interaction axis receiving the central trend.
    :param trend_data: One estimate and interval per provider endpoint.
    :param provider_order: Provider labels in x-axis order.
    :param estimate_column: Central estimate field in ``trend_data``.
    :param lower_column: Inclusive 95% lower-bound field.
    :param upper_column: Inclusive 95% upper-bound field.
    :return: None after drawing the central line above individual trajectories.
    """
    if trend_data.empty:
        return
    indexed = trend_data.set_index("provider_label")
    plotted_providers = [
        provider_label
        for provider_label in provider_order
        if provider_label in indexed.index
    ]
    positions = np.arange(len(plotted_providers), dtype=float)
    estimates = np.array(
        [
            float(indexed.loc[provider_label, estimate_column])
            for provider_label in plotted_providers
        ]
    )
    lower = np.array(
        [
            float(indexed.loc[provider_label, lower_column])
            for provider_label in plotted_providers
        ]
    )
    upper = np.array(
        [
            float(indexed.loc[provider_label, upper_column])
            for provider_label in plotted_providers
        ]
    )
    ax.errorbar(
        positions,
        estimates,
        yerr=np.vstack((estimates - lower, upper - estimates)),
        fmt="none",
        ecolor="#3A3A3A",
        elinewidth=0.8,
        capsize=2.0,
        capthick=0.8,
        zorder=4,
    )
    ax.plot(
        positions,
        estimates,
        color="#202020",
        linewidth=2.8,
        alpha=0.45,
        marker="o",
        markersize=3.2,
        zorder=5,
    )


def _configure_provider_interaction_axis(
    ax: Axes,
    *,
    provider_order: list[str],
) -> None:
    """Apply compact provider labels to one interaction subplot.

    :param ax: Interaction subplot with provider positions zero and one.
    :param provider_order: Provider labels in display order.
    :return: None after configuring the shared x-axis.
    """
    ut.set_fixed_x_ticklabels(
        ax,
        provider_order,
        positions=range(len(provider_order)),
    )
    ut.rotate_x_ticklabels(ax, rotation=20, ha="right")
    ax.set_xlim(-0.25, len(provider_order) - 0.75)


def _annotate_provider_interaction_test(
    ax: Axes,
    *,
    summary: pd.DataFrame,
    p_value_column: str,
    tested_pairs_column: str,
    tested_pairs_name: str,
    test_name: str,
) -> None:
    """Add the correct paired exact-test result beneath one subplot.

    :param ax: Axis receiving the reader-facing test label.
    :param summary: One matched provider-comparison summary row.
    :param p_value_column: Exact-test p-value column in ``summary``.
    :param tested_pairs_column: Number of non-tied or discordant pairs.
    :param tested_pairs_name: Reader-facing description of those pairs.
    :param test_name: Concise exact paired test name.
    :return: None after adding the exact paired-test annotation.
    """
    if summary.empty:
        return
    row = summary.iloc[0]
    p_value = row[p_value_column]
    tested_pairs = int(row[tested_pairs_column])
    shared_regesta = int(row["shared_regesta"])
    if pd.isna(p_value):
        ax.set_xlabel(
            f"Exact paired {test_name}:\nunavailable (no {tested_pairs_name} pairs)",
            fontsize=FIGURE_FONTSIZE - 1,
        )
        return
    ax.set_xlabel(
        f"Exact paired {test_name}:\n"
        f"p = {float(p_value):.3f} "
        f"({tested_pairs} {tested_pairs_name} of {shared_regesta})",
        fontsize=FIGURE_FONTSIZE - 1,
    )
