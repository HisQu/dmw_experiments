"""Reusable annotation helpers for grouped x-axis statistics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import math

import pandas as pd
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.colors import to_rgba
from matplotlib.path import Path as MplPath
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator
from matplotlib.transforms import Bbox, IdentityTransform, ScaledTranslation

from .axes import annotate_labels, ensure_top_text_headroom, iter_axes

XAxisStatistic = Literal["mean", "median", "count"]
AnnotationPlacement = Literal["bottom", "top"]

_ANNOTATION_FONTSIZE = 8
_ANNOTATION_FONTWEIGHT = "bold"
_ANNOTATION_BOTTOM_PAD_POINTS = 1.5
_ANNOTATION_BAND_PAD_POINTS = 1.5
_ANNOTATION_ANCHOR_GAP_POINTS = 2.0
_ANNOTATION_TOP_PAD_POINTS = 5.0
_ANNOTATION_LINE_SPACING_POINTS = 6.0
_ANNOTATION_ZORDER_EPSILON = 0.001
_ANNOTATION_TEXT_ZORDER = 3.2
_ANNOTATION_BAND_ATTR = "_haiu_above_xaxis_annotation_band"
_ANNOTATION_ANCHOR_ATTR = "_haiu_above_xaxis_annotation_anchor_y"
_ANNOTATION_ANCHOR_GAP_ATTR = "_haiu_above_xaxis_annotation_anchor_gap_points"


@dataclass(frozen=True)
class AboveXAxisAnnotation:
    """Container for one above-x-axis group statistic annotation.

    :param texts: Text artists used for the label prefix and values.
    :param band: Background band artist, if labels were rendered.
    :param anchor_y: Data value that clears the annotation band.
    """

    texts: tuple[Text, ...]
    band: Artist | None
    anchor_y: float


def _annotation_renderer(ax: Axes) -> Any | None:
    """Return the active canvas renderer for measuring annotation artists."""
    fig = ax.figure
    # !! Dynamic boundary: Matplotlib canvas backends expose renderer access differently.
    get_renderer = getattr(fig.canvas, "get_renderer", None)
    if get_renderer is None:
        fig.canvas.draw()
        # !! Dynamic boundary: drawing may attach renderer access on some Matplotlib backends.
        get_renderer = getattr(fig.canvas, "get_renderer", None)
    if get_renderer is None:
        return None
    return get_renderer()


def _points_to_pixels(ax: Axes, points: float) -> float:
    """Convert typographic points to display pixels for one figure."""
    return float(points) * float(ax.figure.dpi) / 72.0


def _points_to_axes_y_fraction(
    ax: Axes,
    *,
    renderer: Any,
    points: float,
) -> float:
    """Convert a vertical point distance to axes-height fraction."""
    axes_bbox = ax.get_window_extent(renderer)
    if axes_bbox.height <= 0:
        return 0.0
    return _points_to_pixels(ax, points) / float(axes_bbox.height)


def _clearance_anchor(
    ax: Axes,
    *,
    base_limits: tuple[float, float] | None = None,
    clearance_anchor: float | None = None,
) -> float:
    """Return the data value that should clear the annotation band."""
    if clearance_anchor is not None:
        return float(clearance_anchor)
    y_min, y_max = ax.get_ylim() if base_limits is None else base_limits
    if y_min <= 0.0 <= y_max:
        return 0.0
    return float(y_min)


def _expand_y_limits(
    ax: Axes,
    *,
    anchor_y: float,
    target_anchor_fraction: float,
) -> None:
    """Expand lower y-limits so one data anchor clears the label band."""
    if not 0.0 < target_anchor_fraction < 0.95:
        return

    y_min, y_max = ax.get_ylim()
    if y_max <= y_min:
        return

    scale_transform = ax.yaxis.get_transform()
    try:
        scale_anchor = float(scale_transform.transform([anchor_y])[0])
        scale_top = float(scale_transform.transform([y_max])[0])
    except (TypeError, ValueError, OverflowError):
        return
    if not math.isfinite(scale_anchor) or not math.isfinite(scale_top):
        return
    if scale_anchor >= scale_top:
        return

    scale_bottom = (scale_anchor - (target_anchor_fraction * scale_top)) / (
        1.0 - target_anchor_fraction
    )
    try:
        expanded_bottom = float(
            scale_transform.inverted().transform([scale_bottom])[0]
        )
    except (TypeError, ValueError, OverflowError):
        return
    if math.isfinite(expanded_bottom) and expanded_bottom < y_min:
        ax.set_ylim(bottom=expanded_bottom, top=y_max)


def _limit_y_axis_ticks(
    ax: Axes,
    *,
    minimum_visible_y: float,
) -> None:
    """Hide tick decorations in a reserved annotation band below the data.

    :param ax: Axes whose y ticks are limited to the data-bearing range.
    :param minimum_visible_y: Lowest value that should retain tick decorations.
    :return: None.

    The annotation band may extend an otherwise non-negative axis below zero.
    Keeping automatically generated negative ticks in that band makes it look
    like data space. Freeze only the currently visible tick locations after
    layout so the reserved area remains visually distinct without changing the
    data limits or clipping valid zero-valued observations.
    """
    lower_y, upper_y = ax.get_ylim()
    axis = ax.yaxis
    for locator_getter, locator_setter in (
        (axis.get_major_locator, axis.set_major_locator),
        (axis.get_minor_locator, axis.set_minor_locator),
    ):
        locator = locator_getter()
        try:
            locations = locator.tick_values(lower_y, upper_y)
        except (NotImplementedError, TypeError, ValueError, OverflowError):
            continue
        visible_locations = [
            float(location)
            for location in locations
            if math.isfinite(location)
            and float(location) >= float(minimum_visible_y)
        ]
        locator_setter(FixedLocator(visible_locations))


def _visible_artist_zorders(artists: Sequence[Artist]) -> list[float]:
    """Return z-orders for visible artists in one sequence."""
    return [
        float(artist.get_zorder()) for artist in artists if artist.get_visible()
    ]


def _annotation_band_zorder(ax: Axes) -> float:
    """Return a band z-order between gridlines and x-axis decorations."""
    grid_zorders = _visible_artist_zorders(
        [*ax.get_ygridlines(), *ax.get_xgridlines()]
    )
    grid_zorder = max(grid_zorders, default=2.0)

    bottom_spine = ax.spines.get("bottom")
    decoration_zorders = (
        [float(bottom_spine.get_zorder())] if bottom_spine is not None else []
    )
    for tick in [*ax.xaxis.majorTicks, *ax.xaxis.minorTicks]:
        decoration_zorders.extend(
            _visible_artist_zorders([tick.tick1line, tick.tick2line])
        )
    decoration_zorder = min(decoration_zorders, default=grid_zorder + 1.0)

    if decoration_zorder > grid_zorder:
        return (grid_zorder + decoration_zorder) / 2.0
    return grid_zorder + _ANNOTATION_ZORDER_EPSILON


class _AboveXAxisAnnotationBand(Artist):
    """Display-space band that masks gridlines behind annotations."""

    def __init__(
        self,
        target_ax: Axes,
        target_texts: Sequence[Text],
        *,
        band_pad_points: float,
        anchor_gap_points: float,
        anchor_y: float,
    ) -> None:
        super().__init__()
        setattr(self, _ANNOTATION_BAND_ATTR, True)
        setattr(self, _ANNOTATION_ANCHOR_ATTR, anchor_y)
        setattr(self, _ANNOTATION_ANCHOR_GAP_ATTR, anchor_gap_points)
        self._target_ax = target_ax
        self._target_texts = tuple(target_texts)
        self._band_pad_points = float(band_pad_points)
        self._facecolor = to_rgba(target_ax.get_facecolor())
        self.set_zorder(_annotation_band_zorder(target_ax))

    def get_window_extent(self, renderer: Any | None = None) -> Bbox:
        """Return the display-space band extent."""
        active_renderer = (
            _annotation_renderer(self._target_ax)
            if renderer is None
            else renderer
        )
        if active_renderer is None:
            return Bbox.from_extents(0.0, 0.0, 0.0, 0.0)
        axes_bbox = self._target_ax.get_window_extent(active_renderer)
        text_bboxes = [
            text.get_window_extent(active_renderer)
            for text in self._target_texts
            if text.get_visible()
        ]
        if not text_bboxes:
            band_top = axes_bbox.y0
        else:
            band_top = max(text_bbox.y1 for text_bbox in text_bboxes)
            band_top += _points_to_pixels(
                self._target_ax,
                self._band_pad_points,
            )
        band_top = min(max(band_top, axes_bbox.y0), axes_bbox.y1)
        return Bbox.from_extents(
            axes_bbox.x0,
            axes_bbox.y0,
            axes_bbox.x1,
            band_top,
        )

    def draw(self, renderer: Any) -> None:
        """Draw the display-space band."""
        if not self.get_visible():
            return
        band_bbox = self.get_window_extent(renderer)
        path = MplPath(
            [
                (band_bbox.x0, band_bbox.y0),
                (band_bbox.x1, band_bbox.y0),
                (band_bbox.x1, band_bbox.y1),
                (band_bbox.x0, band_bbox.y1),
                (band_bbox.x0, band_bbox.y0),
            ],
            [
                MplPath.MOVETO,
                MplPath.LINETO,
                MplPath.LINETO,
                MplPath.LINETO,
                MplPath.CLOSEPOLY,
            ],
        )
        gc = renderer.new_gc()
        try:
            gc.set_linewidth(0.0)
            gc.set_foreground(self._facecolor)
            gc.set_alpha(self._facecolor[-1])
            renderer.draw_path(
                gc,
                path,
                IdentityTransform(),
                rgbFace=self._facecolor,
            )
        finally:
            gc.restore()


def _add_annotation_band(
    ax: Axes,
    *,
    texts: Sequence[Text],
    band_pad_points: float,
    anchor_gap_points: float,
    anchor_y: float,
) -> Artist:
    """Add a clean axes-relative band behind annotations."""
    band = _AboveXAxisAnnotationBand(
        ax,
        texts,
        band_pad_points=band_pad_points,
        anchor_gap_points=anchor_gap_points,
        anchor_y=anchor_y,
    )
    ax.add_artist(band)
    return band


def _annotation_label_x(
    ax: Axes,
    *,
    value_xs: Sequence[float],
    box_width: float,
) -> float:
    """Reserve left x-axis space and return the label-prefix position."""
    if not value_xs:
        return 0.0
    first_value_x = min(value_xs)
    current_left, current_right = ax.get_xlim()
    label_x = first_value_x - (box_width * 0.65)
    reserved_left = min(current_left, label_x - (box_width * 0.45))
    ax.set_xlim(left=float(reserved_left), right=float(current_right))
    return label_x


def _finalize_annotation_layout(
    ax: Axes,
    texts: Sequence[Text],
    *,
    base_limits: tuple[float, float] | None,
    clearance_anchor: float | None,
    bottom_pad_points: float,
    band_pad_points: float,
    anchor_gap_points: float,
) -> tuple[Artist | None, float]:
    """Place labels in display space and reserve data-space clearance."""
    anchor_y = _clearance_anchor(
        ax,
        base_limits=base_limits,
        clearance_anchor=clearance_anchor,
    )
    if not texts:
        return None, anchor_y
    if base_limits is not None:
        ax.set_ylim(*base_limits)

    renderer = _annotation_renderer(ax)
    if renderer is None:
        return None, anchor_y

    y_transform = ax.get_xaxis_transform() + ScaledTranslation(
        0.0,
        float(bottom_pad_points) / 72.0,
        ax.figure.dpi_scale_trans,
    )
    for text in texts:
        x_position, _old_y = text.get_position()
        text.set_position((x_position, 0.0))
        text.set_transform(y_transform)
        text.set_clip_on(True)
        text.set_zorder(_ANNOTATION_TEXT_ZORDER)

    ax.figure.canvas.draw()
    renderer = _annotation_renderer(ax)
    if renderer is None:
        return None, anchor_y

    axes_bbox = ax.get_window_extent(renderer)
    if axes_bbox.height <= 0:
        return None, anchor_y
    band = _add_annotation_band(
        ax,
        texts=texts,
        band_pad_points=band_pad_points,
        anchor_gap_points=anchor_gap_points,
        anchor_y=anchor_y,
    )
    setattr(ax, _ANNOTATION_ANCHOR_ATTR, anchor_y)
    band_bbox = band.get_window_extent(renderer)
    band_fraction = (band_bbox.y1 - axes_bbox.y0) / float(axes_bbox.height)

    anchor_gap_fraction = _points_to_axes_y_fraction(
        ax,
        renderer=renderer,
        points=anchor_gap_points,
    )
    _expand_y_limits(
        ax,
        anchor_y=anchor_y,
        target_anchor_fraction=band_fraction + anchor_gap_fraction,
    )
    return band, anchor_y


def _ordered_present_values(
    values: Sequence[Any],
    *,
    preferred_order: Sequence[Any] | None = None,
) -> list[Any]:
    """Return values in preferred order followed by first-seen leftovers."""
    present_values = [
        value
        for value in pd.unique(pd.Series(values, dtype=object))
        if pd.notna(value)
    ]
    if preferred_order is None:
        return present_values
    ordered = [value for value in preferred_order if value in present_values]
    ordered.extend(value for value in present_values if value not in ordered)
    return ordered


def _default_value_formatter(value: float) -> str:
    """Format one statistic value as compact text."""
    float_value = float(value)
    if float_value.is_integer():
        return str(int(float_value))
    return f"{float_value:g}"


def _statistic_values(
    data: pd.DataFrame,
    *,
    x: str,
    y: str,
    hue: str | None,
    statistic: XAxisStatistic,
) -> Mapping[Any, float]:
    """Return grouped statistic values keyed by x or by x/hue tuple."""
    group_columns = [x] if hue is None else [x, hue]
    if statistic == "count":
        grouped = data.groupby(
            group_columns,
            sort=False,
            observed=False,
        )[y].count()
    else:
        numeric_data = data.loc[:, group_columns].copy()
        numeric_data["_haiu_annotation_value"] = pd.to_numeric(
            data[y],
            errors="coerce",
        )
        grouped_values = numeric_data.groupby(
            group_columns,
            sort=False,
            observed=False,
        )["_haiu_annotation_value"]
        grouped = (
            grouped_values.mean()
            if statistic == "mean"
            else grouped_values.median()
        )
    return grouped.dropna().astype(float).to_dict()


def _hue_offsets(hue_count: int, *, box_width: float) -> list[float]:
    """Return seaborn-like dodge offsets for one grouped box width."""
    series_count = max(hue_count, 1)
    if series_count == 1:
        return [0.0]
    step = box_width / series_count
    return [
        (-box_width / 2.0) + (step / 2.0) + (series_index * step)
        for series_index in range(series_count)
    ]


def annotate_xaxis_group_statistic(
    ax: Axes,
    *,
    data: pd.DataFrame,
    x: str,
    y: str,
    x_order: Sequence[Any],
    statistic: XAxisStatistic = "mean",
    hue: str | None = None,
    hue_order: Sequence[Any] | None = None,
    palette: Mapping[Any, str] | None = None,
    color: str = "black",
    label_color: str | None = None,
    box_width: float = 0.6,
    label: str | None = None,
    value_formatter: Callable[[float], str] | None = None,
    base_ylim: tuple[float, float] | None = None,
    clearance_anchor: float | None = None,
    bottom_pad_points: float = _ANNOTATION_BOTTOM_PAD_POINTS,
    band_pad_points: float = _ANNOTATION_BAND_PAD_POINTS,
    anchor_gap_points: float = _ANNOTATION_ANCHOR_GAP_POINTS,
    placement: AnnotationPlacement = "bottom",
    line_index: int = 0,
    line_spacing_points: float = _ANNOTATION_LINE_SPACING_POINTS,
    fontsize: float = _ANNOTATION_FONTSIZE,
    alpha: float = 1.0,
    minimum_visible_y: float | None = None,
) -> AboveXAxisAnnotation:
    """Annotate grouped x-axis categories with one statistic row.

    :param ax: Axes that receive the annotation.
    :param data: Source data frame with grouping and value columns.
    :param x: Column used for x-axis groups.
    :param y: Numeric or count target column.
    :param x_order: Display order for x groups.
    :param statistic: Group statistic to annotate.
    :param hue: Optional column used for dodged group annotations.
    :param hue_order: Display order for hue groups.
    :param palette: Optional hue-to-color mapping.
    :param color: Fallback color for ungrouped or unmapped values.
    :param label_color: Optional color for the statistic label prefix.
    :param box_width: Width used to place dodged annotations.
    :param label: Optional label prefix.
    :param value_formatter: Optional statistic formatter.
    :param base_ylim: Optional y-limits to restore before layout.
    :param clearance_anchor: Optional data value that should clear the band.
    :param bottom_pad_points: Text baseline offset above the x-axis.
    :param band_pad_points: Extra band padding above label bounds.
    :param anchor_gap_points: Display-space gap above the band.
    :param placement: Reserve label space below or above the plotted data.
    :param line_index: Zero-based vertical annotation row within one placement.
    :param line_spacing_points: Distance between adjacent annotation rows.
    :param fontsize: Text size for the prefix and statistic values.
    :param alpha: Shared opacity for the prefix and statistic values.
    :param minimum_visible_y: Optional y-axis floor below which tick decorations
        are hidden. Use this when the annotation band extends a non-negative
        data axis below zero.
    :return: Created annotation artists and clearance anchor.
    """
    if statistic not in {"mean", "median", "count"}:
        raise ValueError(f"Unsupported x-axis statistic: {statistic!r}")
    if placement not in {"bottom", "top"}:
        raise ValueError(f"Unsupported annotation placement: {placement!r}")
    if line_index < 0:
        raise ValueError("line_index must be non-negative.")

    statistic_map = _statistic_values(
        data,
        x=x,
        y=y,
        hue=hue,
        statistic=statistic,
    )
    label_defaults = {"mean": "µ:", "median": "med:", "count": "n:"}
    label_text = label if label is not None else label_defaults[statistic]
    formatter = value_formatter or _default_value_formatter
    palette_map = dict(palette or {})
    hue_values = (
        _ordered_present_values(data[hue].tolist(), preferred_order=hue_order)
        if hue is not None
        else []
    )
    offsets = _hue_offsets(len(hue_values), box_width=box_width)

    label_specs: list[tuple[float, float, str]] = []
    label_colors: list[str] = []
    label_xs: list[float] = []
    for category_index, category in enumerate(x_order):
        if hue is None:
            statistic_value = statistic_map.get(category)
            if statistic_value is None or pd.isna(statistic_value):
                continue
            x_position = float(category_index)
            label_specs.append(
                (x_position, 0.0, formatter(float(statistic_value)))
            )
            label_colors.append(color)
            label_xs.append(x_position)
            continue

        for hue_index, hue_value in enumerate(hue_values):
            statistic_value = statistic_map.get((category, hue_value))
            if statistic_value is None or pd.isna(statistic_value):
                continue
            x_position = float(category_index) + offsets[hue_index]
            label_specs.append(
                (x_position, 0.0, formatter(float(statistic_value)))
            )
            label_colors.append(palette_map.get(hue_value, color))
            label_xs.append(x_position)

    if not label_specs:
        band, anchor_y = _finalize_annotation_layout(
            ax,
            (),
            base_limits=base_ylim,
            clearance_anchor=clearance_anchor,
            bottom_pad_points=bottom_pad_points,
            band_pad_points=band_pad_points,
            anchor_gap_points=anchor_gap_points,
        )
        return AboveXAxisAnnotation(texts=(), band=band, anchor_y=anchor_y)

    prefix_x = _annotation_label_x(
        ax,
        value_xs=label_xs,
        box_width=box_width,
    )
    prefix_texts = annotate_labels(
        ax,
        [(prefix_x, 0.0, label_text)],
        colors=[label_color or "black"],
        fontsize=fontsize,
        fontweight=_ANNOTATION_FONTWEIGHT,
        ha="right",
        alpha=alpha,
    )
    value_texts = annotate_labels(
        ax,
        label_specs,
        colors=label_colors,
        fontsize=fontsize,
        fontweight=_ANNOTATION_FONTWEIGHT,
        alpha=alpha,
    )
    texts = tuple([*prefix_texts, *value_texts])
    if placement == "top":
        if base_ylim is not None:
            ax.set_ylim(*base_ylim)
        top = ax.get_ylim()[1]
        for text in texts:
            x_position, _old_y = text.get_position()
            text.set_position((x_position, top))
            text.set_transform(ax.transData)
            text.set_clip_on(True)
            text.set_zorder(_ANNOTATION_TEXT_ZORDER)
        ensure_top_text_headroom(
            ax,
            texts,
            pad_points=_ANNOTATION_TOP_PAD_POINTS
            + (line_index * line_spacing_points),
        )
        return AboveXAxisAnnotation(texts=texts, band=None, anchor_y=top)
    band, anchor_y = _finalize_annotation_layout(
        ax,
        texts,
        base_limits=base_ylim,
        clearance_anchor=clearance_anchor,
        bottom_pad_points=bottom_pad_points
        + (line_index * line_spacing_points),
        band_pad_points=band_pad_points,
        anchor_gap_points=anchor_gap_points,
    )
    if minimum_visible_y is not None:
        _limit_y_axis_ticks(ax, minimum_visible_y=minimum_visible_y)
    return AboveXAxisAnnotation(texts=texts, band=band, anchor_y=anchor_y)


def refresh_above_xaxis_annotations(axes: Any) -> None:
    """Refresh annotation clearance after constrained layout settles.

    :param axes: Single axes, figure, or axes container.
    :return: None.
    """
    axis_list = list(iter_axes(axes))
    if not axis_list:
        return
    axis_list[0].figure.canvas.draw()
    for ax in axis_list:
        bands = [
            artist
            for artist in ax.artists
            if getattr(artist, _ANNOTATION_BAND_ATTR, False)
        ]
        if not bands:
            continue
        renderer = _annotation_renderer(ax)
        if renderer is None:
            continue
        axes_bbox = ax.get_window_extent(renderer)
        if axes_bbox.height <= 0:
            continue
        band = bands[-1]
        band_bbox = band.get_window_extent(renderer)
        band_fraction = (band_bbox.y1 - axes_bbox.y0) / float(axes_bbox.height)
        anchor_gap_points = float(
            getattr(
                band, _ANNOTATION_ANCHOR_GAP_ATTR, _ANNOTATION_ANCHOR_GAP_POINTS
            )
        )
        anchor_gap_fraction = _points_to_axes_y_fraction(
            ax,
            renderer=renderer,
            points=anchor_gap_points,
        )
        anchor_y = float(getattr(band, _ANNOTATION_ANCHOR_ATTR))
        _expand_y_limits(
            ax,
            anchor_y=anchor_y,
            target_anchor_fraction=band_fraction + anchor_gap_fraction,
        )


__all__ = [
    "AboveXAxisAnnotation",
    "XAxisStatistic",
    "annotate_xaxis_group_statistic",
    "refresh_above_xaxis_annotations",
]
