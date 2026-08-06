"""Reusable legend helpers for experiment plotting layouts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil
from typing import Any, cast

from matplotlib import colors as mcolors
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.patches import Patch

from .axes import iter_axes


def collect_legend_entries(obj: Any) -> tuple[list[Any], list[str]]:
    """Collect de-duplicated legend entries across axes."""
    seen: set[str] = set()
    handles_out: list[Any] = []
    labels_out: list[str] = []

    for ax in iter_axes(obj):
        handles, labels = ax.get_legend_handles_labels()
        for handle, label in zip(handles, labels, strict=False):
            if not label or label.startswith("_"):
                continue
            if label in seen:
                continue
            seen.add(label)
            handles_out.append(handle)
            labels_out.append(label)

    return handles_out, labels_out


def square_legend_entries(
    labels_to_colors: Mapping[str, str],
    *,
    linewidth: float = 1.5,
) -> tuple[list[Patch], list[str]]:
    """Build simple hollow-square legend entries from label/color pairs."""
    labels = list(labels_to_colors)
    handles = [
        Patch(
            facecolor="none",
            edgecolor=labels_to_colors[label],
            linewidth=linewidth,
        )
        for label in labels
    ]
    return handles, labels


def remove_axis_legends(obj: Any) -> None:
    """Remove legends attached to axes while leaving figure legends intact."""
    for ax in iter_axes(obj):
        if ax.legend_ is not None:
            ax.legend_.remove()


def _normalize_legend_color(value: Any) -> str | None:
    """Normalize one matplotlib color-like value into a simple display color."""
    if value is None:
        return None
    if isinstance(value, str):
        return None if value.lower() == "none" else value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if not value:
            return None
        first = value[0]
        if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
            return _normalize_legend_color(first)
    try:
        return mcolors.to_hex(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _infer_handle_display_color(handle: Any) -> str | None:
    """Infer one display color from a proxy legend handle."""
    for attr_name in ("get_edgecolor", "get_color", "get_facecolor"):
        # !! Dynamic boundary: Matplotlib legend proxy handles expose color methods by artist type.
        getter = getattr(handle, attr_name, None)
        if not callable(getter):
            continue
        color = _normalize_legend_color(getter())
        if color is not None:
            return color
    return None


def add_top_band_figure_legend(
    fig: Figure,
    band_ax: Axes,
    *,
    handles: Sequence[Any],
    labels: Sequence[str],
    ncol: int | None = None,
    max_rows: int | None = None,
    label_colors: Sequence[Any] | None = None,
    show_handles: bool = False,
    frameon: bool = True,
    loc: str = "center",
    bbox_to_anchor: tuple[float, float] = (0.5, 0.5),
    alignment: str | None = None,
) -> Legend:
    """Anchor a centered figure legend inside one reserved top-band axes.

    :param fig: Figure that owns the legend.
    :param band_ax: Dedicated axes that reserves space for the legend.
    :param handles: Matplotlib handles for the legend entries.
    :param labels: Display labels that correspond to ``handles``.
    :param ncol: Explicit number of legend columns.
    :param max_rows: Maximum number of legend rows.  The helper derives the
        smallest sufficient number of columns.  Cannot be combined with
        ``ncol``.
    :param label_colors: Optional text colors corresponding to ``labels``.
    :param show_handles: Whether to retain the handle glyphs beside labels.
    :param frameon: Whether to render a legend frame.
    :param loc: Matplotlib legend location within the reserved axes.
    :param bbox_to_anchor: Anchor position relative to ``band_ax``.
    :param alignment: Optional Matplotlib legend alignment.
    :return: The figure-level legend.
    """
    if ncol is not None and max_rows is not None:
        raise ValueError("Specify either ncol or max_rows, not both.")
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be at least 1.")

    band_ax.set_axis_off()
    resolved_ncol = (
        ceil(len(labels) / max_rows)
        if max_rows is not None
        else (1 if ncol is None else ncol)
    )
    resolved_label_colors = (
        list(label_colors)
        if label_colors is not None
        else [
            inferred
            for inferred in (
                _infer_handle_display_color(handle) for handle in handles
            )
            if inferred is not None
        ]
    )
    legend_kws: dict[str, Any] = {
        "loc": loc,
        "bbox_to_anchor": bbox_to_anchor,
        "bbox_transform": band_ax.transAxes,
        "ncol": resolved_ncol,
        "frameon": frameon,
    }
    if alignment is not None:
        legend_kws["alignment"] = alignment
    if resolved_label_colors and len(resolved_label_colors) == len(labels):
        legend_kws["labelcolor"] = list(resolved_label_colors)
    if not show_handles:
        legend_kws["handlelength"] = 0.0
        legend_kws["handletextpad"] = 0.2
    return fig.legend(
        list(handles),
        list(labels),
        **legend_kws,
    )


__all__ = [
    "add_top_band_figure_legend",
    "collect_legend_entries",
    "remove_axis_legends",
    "square_legend_entries",
]
