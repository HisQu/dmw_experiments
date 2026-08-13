"""Stable dataframe and plotting facade owned by experiment analysis."""

# ruff: noqa: F401

from dmw_experiments.shared.analysis.entity_spans import (
    EntityMention,
    EntitySpanCandidate,
    EntitySpanResolver,
    ResolvedEntityMention,
)

from haiu.utils import (
    empty_frame,
    frame_from_records,
    numeric_column,
    series_column,
)

from dmw_experiments.shared.analysis.plotting import (
    DEFAULT_FIGURE_FORMATS,
    DEFAULT_OVERLAY_STRIP_KWS,
    add_top_band_figure_legend,
    annotate_labels,
    annotate_xaxis_group_statistic,
    apply_grid,
    collect_legend_entries,
    configure_log_minor_ticks,
    configure_matplotlib_defaults,
    configure_percent_axis,
    ensure_top_text_headroom,
    export_figure,
    refresh_above_xaxis_annotations,
    remove_axis_legends,
    restyle_overlay_strip_collections,
    rotate_x_ticklabels,
    set_fixed_x_ticklabels,
    square_legend_entries,
)
