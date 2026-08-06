"""Lean plotting helpers for matplotlib axes containers and axis formatting."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Literal

import numpy as np
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.ticker import LogFormatterSciNotation, LogLocator

from .style import DEFAULT_PAPER_FONTSIZE

AxisName = Literal["x", "y"]
HorizontalAlignment = Literal["left", "center", "right"]
VerticalAlignment = Literal[
    "bottom",
    "baseline",
    "center",
    "center_baseline",
    "top",
]


def iter_axes(obj: Any) -> Iterator[Axes]:
    """Yield axes from a supported container."""
    if isinstance(obj, Axes):
        yield obj
        return

    if isinstance(obj, Figure):
        for ax in obj.axes:
            yield ax
        return

    axes_obj = getattr(obj, "axes", obj)

    if isinstance(axes_obj, Axes):
        yield axes_obj
        return

    arr = np.asarray(axes_obj, dtype=object)
    if arr.ndim == 0:
        item = arr.item()
        if isinstance(item, Axes):
            yield item
            return
        raise TypeError(f"Unsupported axes container: {type(obj)!r}")

    for item in arr.ravel():
        if item is None:
            continue
        if not isinstance(item, Axes):
            raise TypeError(
                f"Expected matplotlib Axes, got {type(item)!r} in container {type(obj)!r}"
            )
        yield item


def apply(
    obj: Any,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> list[Any]:
    """Apply an axes function to every axes in a container."""
    return [func(ax, *args, **kwargs) for ax in iter_axes(obj)]


def annotate_labels(
    ax: Axes,
    labels: Sequence[tuple[float, float, str]],
    *,
    fontsize: float = DEFAULT_PAPER_FONTSIZE - 1,
    fontweight: str = "normal",
    colors: Sequence[str] | None = None,
    ha: str = "center",
    va: str = "bottom",
    alpha: float = 1.0,
) -> list[Text]:
    """Draw text labels on one axes.

    :param ax: Axes that receive the labels.
    :param labels: Tuples with x, y, and display text values.
    :param fontsize: Text font size.
    :param fontweight: Text font weight.
    :param colors: Optional color sequence matched by label index.
    :param ha: Horizontal text alignment.
    :param va: Vertical text alignment.
    :param alpha: Shared text opacity.
    :return: Created text artists.
    """
    color_values = list(colors) if colors is not None else []
    text_artists: list[Text] = []
    for index, (x, y, text) in enumerate(labels):
        color: str = (
            color_values[index] if index < len(color_values) else "black"
        )
        text_artists.append(
            ax.text(
                x,
                y,
                text,
                ha=ha,
                va=va,
                fontsize=fontsize,
                fontweight=fontweight,
                color=color,
                alpha=alpha,
            )
        )
    return text_artists


def ensure_top_text_headroom(
    ax: Axes,
    texts: Sequence[Text],
    *,
    pad_points: float = 2.0,
    max_iterations: int = 3,
) -> None:
    """Expand the y-axis top so text labels fit inside the axes.

    :param ax: Axes whose y-limit may be expanded.
    :param texts: Text artists to keep below the top axis border.
    :param pad_points: Minimum display padding above the text.
    :param max_iterations: Maximum redraw-and-expand passes.
    :return: None.
    """
    visible_texts = [text for text in texts if text.get_visible()]
    if not visible_texts:
        return

    fig = ax.figure
    # !! Dynamic boundary: Matplotlib canvas backends expose renderer access differently.
    get_renderer = getattr(fig.canvas, "get_renderer", None)
    if get_renderer is None:
        fig.canvas.draw()
        # !! Dynamic boundary: drawing may attach renderer access on some Matplotlib backends.
        get_renderer = getattr(fig.canvas, "get_renderer", None)
        if get_renderer is None:
            return

    pad_pixels = pad_points * fig.dpi / 72.0
    for _iteration in range(max_iterations):
        renderer = get_renderer()
        axes_bbox = ax.get_window_extent(renderer)
        overflow_pixels = max(
            text.get_window_extent(renderer).y1 + pad_pixels - axes_bbox.y1
            for text in visible_texts
        )
        if overflow_pixels <= 0:
            return

        y_min, y_max = ax.get_ylim()
        if y_max <= y_min:
            return
        x_display = axes_bbox.x0 + (axes_bbox.width / 2.0)
        _x_data, expanded_top = ax.transData.inverted().transform(
            (x_display, axes_bbox.y1 + overflow_pixels)
        )
        if not np.isfinite(expanded_top) or expanded_top <= y_max:
            data_span = y_max - y_min
            expanded_top = y_max + (data_span * 0.05 if data_span else 1.0)
        ax.set_ylim(top=float(expanded_top))
        # > Recalculate artist bounds against the expanded data transform.
        fig.canvas.draw()


def format_facet_title(
    key: tuple[Any, ...] | Any,
    *,
    connect: str = "\n",
    capitalize: bool = False,
) -> str:
    """Format a facet key into a subplot title."""
    if isinstance(key, tuple):
        parts: list[str] = []
        for value in key:
            if isinstance(value, str) and capitalize:
                parts.append(value.capitalize())
            else:
                parts.append(str(value))
        return connect.join(parts)

    if isinstance(key, str) and capitalize:
        return key.capitalize()

    return str(key)


def set_fixed_x_ticklabels(
    ax: Axes,
    labels: Sequence[str],
    *,
    positions: Sequence[float] | None = None,
) -> None:
    """Set fixed x tick labels using explicit positions."""
    tick_positions = (
        list(ax.get_xticks()) if positions is None else list(positions)
    )
    if len(tick_positions) != len(labels):
        raise ValueError(
            f"Label count {len(labels)} does not match position count {len(tick_positions)}"
        )
    ax.set_xticks(tick_positions, labels=list(labels))


def rotate_x_ticklabels(
    ax: Axes,
    *,
    rotation: float,
    ha: HorizontalAlignment | None = None,
    va: VerticalAlignment | None = None,
    rotation_mode: Literal["default", "anchor"] | None = None,
    pad: float | None = None,
) -> None:
    """Rotate x tick labels with sensible defaults."""
    if 20 < rotation < 89:
        ha = "right" if ha is None else ha
        va = "center" if va is None else va
        rotation_mode = "anchor" if rotation_mode is None else rotation_mode
        pad = 2.5 if pad is None else pad
    ax.tick_params(axis="x", labelrotation=rotation)
    if pad is not None:
        ax.tick_params(axis="x", pad=pad)
    for label in ax.get_xticklabels():
        if ha is not None:
            label.set_horizontalalignment(ha)
        if va is not None:
            label.set_verticalalignment(va)
        if rotation_mode is not None:
            label.set_rotation_mode(rotation_mode)


def configure_log_minor_ticks(
    ax: Axes,
    *,
    axis: AxisName = "y",
    base: float = 10,
    subs: Sequence[float] = (2, 3, 5, 7),
    label_only_base: bool = False,
    minor_thresholds: tuple[int, float] = (2, 0.4),
) -> None:
    """Configure log minor ticks through locator and formatter objects."""
    axis_obj: Axis
    if axis == "x":
        axis_obj = ax.xaxis
    elif axis == "y":
        axis_obj = ax.yaxis
    else:
        raise ValueError(f"Unsupported axis: {axis!r}")

    axis_obj.set_minor_locator(LogLocator(base=base, subs=tuple(subs)))
    axis_obj.set_minor_formatter(
        LogFormatterSciNotation(
            base=base,
            labelOnlyBase=label_only_base,
            minor_thresholds=minor_thresholds,
        )
    )


def apply_grid(
    ax: Axes,
    *,
    y_major_kws: Mapping[str, Any] | None = None,
    y_minor_kws: Mapping[str, Any] | None = None,
    x_major_kws: Mapping[str, Any] | None = None,
) -> None:
    """Apply a simple benchmark-friendly grid style."""
    y_major = {
        "linestyle": "--",
        "linewidth": 0.7,
        "alpha": 0.45,
    }
    y_minor = {
        "linestyle": ":",
        "linewidth": 0.5,
        "alpha": 0.3,
    }
    x_major = {
        "linestyle": ":",
        "linewidth": 0.35,
        "color": "0.85",
        "zorder": 0,
    }

    if y_major_kws is not None:
        y_major.update(y_major_kws)
    if y_minor_kws is not None:
        y_minor.update(y_minor_kws)
    if x_major_kws is not None:
        x_major.update(x_major_kws)

    ax.grid(True, axis="y", which="major", **y_major)
    ax.grid(True, axis="y", which="minor", **y_minor)
    if x_major_kws is not None:
        ax.grid(True, axis="x", which="major", **x_major)


def set_fontsizes(
    ax: Axes,
    *,
    ticklabels: float = 10,
    axis_labels: float = 10,
    title: float = 10,
) -> None:
    """Set common font sizes on a single axes."""
    ax.tick_params(axis="x", which="major", labelsize=ticklabels)
    ax.tick_params(axis="y", which="major", labelsize=ticklabels)
    ax.xaxis.label.set_fontsize(axis_labels)
    ax.yaxis.label.set_fontsize(axis_labels)
    ax.title.set_fontsize(title)


__all__ = [
    "apply",
    "apply_grid",
    "annotate_labels",
    "configure_log_minor_ticks",
    "ensure_top_text_headroom",
    "format_facet_title",
    "iter_axes",
    "rotate_x_ticklabels",
    "set_fixed_x_ticklabels",
    "set_fontsizes",
]


def configure_percent_axis(
    ax: Any,
    *,
    ymax: float = 1.0,
    ymin: float = -0.05,  # < if negative values, set this to -1
    major_max: float = 1.10,
    major_step: float = 0.1,
    minor_step: float = 0.05,
    major_step_for_label: int = 2,
) -> None:
    """Apply a percentage score axis to one axis object."""
    from matplotlib.ticker import (
        FixedLocator,
        FuncFormatter,
        MultipleLocator,
    )

    ax.set_ylim(ymin, ymax)
    major_ticks: list[float] = []
    tick_value = 0.0
    while tick_value <= major_max + (major_step / 2.0):
        major_ticks.append(round(tick_value, 10))
        tick_value += major_step

    def format_major_tick(value: float, pos: int | None) -> str:
        """Label only every second major tick."""
        if pos is None or pos % major_step_for_label == 1:
            return ""
        return f"{value:.0%}"

    ax.yaxis.set_major_locator(FixedLocator(major_ticks))
    ax.yaxis.set_minor_locator(MultipleLocator(minor_step))
    ax.yaxis.set_major_formatter(FuncFormatter(format_major_tick))
    ax.tick_params(axis="y", which="minor", length=0, labelleft=False)
    ax.set_axisbelow(True)
