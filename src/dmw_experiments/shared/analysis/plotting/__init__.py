"""Plot formatting primitives frozen with the experiment harness."""

from dmw_experiments.shared.analysis.plotting.annotations import (
    AboveXAxisAnnotation as AboveXAxisAnnotation,
    XAxisStatistic as XAxisStatistic,
    annotate_xaxis_group_statistic as annotate_xaxis_group_statistic,
    refresh_above_xaxis_annotations as refresh_above_xaxis_annotations,
)
from dmw_experiments.shared.analysis.plotting.axes import (
    annotate_labels as annotate_labels,
    apply as apply,
    apply_grid as apply_grid,
    configure_log_minor_ticks as configure_log_minor_ticks,
    configure_percent_axis as configure_percent_axis,
    ensure_top_text_headroom as ensure_top_text_headroom,
    format_facet_title as format_facet_title,
    iter_axes as iter_axes,
    rotate_x_ticklabels as rotate_x_ticklabels,
    set_fixed_x_ticklabels as set_fixed_x_ticklabels,
    set_fontsizes as set_fontsizes,
)
from dmw_experiments.shared.analysis.plotting.export import (
    DEFAULT_FIGURE_FORMATS as DEFAULT_FIGURE_FORMATS,
    FigureFormat as FigureFormat,
    export_figure as export_figure,
)
from dmw_experiments.shared.analysis.plotting.legend import (
    add_top_band_figure_legend as add_top_band_figure_legend,
    collect_legend_entries as collect_legend_entries,
    remove_axis_legends as remove_axis_legends,
    square_legend_entries as square_legend_entries,
)
from dmw_experiments.shared.analysis.plotting.seaborn import (
    DEFAULT_BOXPLOT_KWS as DEFAULT_BOXPLOT_KWS,
    DEFAULT_OVERLAY_STRIP_KWS as DEFAULT_OVERLAY_STRIP_KWS,
    OVERLAY_STRIP_EDGE_ALPHA as OVERLAY_STRIP_EDGE_ALPHA,
    OVERLAY_STRIP_FACE_ALPHA as OVERLAY_STRIP_FACE_ALPHA,
    restyle_collections as restyle_collections,
    restyle_overlay_strip_collections as restyle_overlay_strip_collections,
    upper_whisker_position as upper_whisker_position,
)
from dmw_experiments.shared.analysis.plotting.style import (
    DEFAULT_PAPER_FONTSIZE as DEFAULT_PAPER_FONTSIZE,
    DEFAULT_SANS_SERIF_STACK as DEFAULT_SANS_SERIF_STACK,
    configure_matplotlib_defaults as configure_matplotlib_defaults,
    ensure_matplotlib_cache_dir as ensure_matplotlib_cache_dir,
    paper_rc_context as paper_rc_context,
    paper_rc_params as paper_rc_params,
    register_repo_fonts as register_repo_fonts,
)
