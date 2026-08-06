"""Stable dataframe and plotting facade owned by experiment analysis."""

from haiu.utils import (
    empty_frame as empty_frame,
    frame_from_records as frame_from_records,
    numeric_column as numeric_column,
    series_column as series_column,
)

from dmw_experiments.shared.analysis.plotting import (
    DEFAULT_FIGURE_FORMATS as DEFAULT_FIGURE_FORMATS,
    DEFAULT_OVERLAY_STRIP_KWS as DEFAULT_OVERLAY_STRIP_KWS,
    add_top_band_figure_legend as add_top_band_figure_legend,
    annotate_labels as annotate_labels,
    annotate_xaxis_group_statistic as annotate_xaxis_group_statistic,
    apply_grid as apply_grid,
    collect_legend_entries as collect_legend_entries,
    configure_log_minor_ticks as configure_log_minor_ticks,
    configure_matplotlib_defaults as configure_matplotlib_defaults,
    configure_percent_axis as configure_percent_axis,
    ensure_top_text_headroom as ensure_top_text_headroom,
    export_figure as export_figure,
    refresh_above_xaxis_annotations as refresh_above_xaxis_annotations,
    remove_axis_legends as remove_axis_legends,
    restyle_overlay_strip_collections as restyle_overlay_strip_collections,
    rotate_x_ticklabels as rotate_x_ticklabels,
    set_fixed_x_ticklabels as set_fixed_x_ticklabels,
    square_legend_entries as square_legend_entries,
)
