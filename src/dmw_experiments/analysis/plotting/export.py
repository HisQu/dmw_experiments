"""Shared figure export helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from matplotlib.figure import Figure

FigureFormat = Literal["pdf", "png", "svg"]
DEFAULT_FIGURE_FORMATS: tuple[FigureFormat, ...] = ("pdf", "png", "svg")
_SUPPORTED_FIGURE_FORMATS = frozenset(DEFAULT_FIGURE_FORMATS)


def export_figure(
    figure: Figure,
    output_path: str | Path,
    *,
    formats: Sequence[FigureFormat] = DEFAULT_FIGURE_FORMATS,
    raster_dpi: int | None = None,
    bbox_inches: str | None = "tight",
) -> tuple[Path, ...]:
    """Write one figure in a consistent set of publication formats.

    The supplied path may be a stem or carry one supported extension. In both
    cases, each requested format is written beside that stem. PDF and SVG
    remain vector outputs; ``raster_dpi`` applies only to PNG.

    :param figure: Matplotlib figure to persist.
    :param output_path: Output stem or path with a supported extension.
    :param formats: Unique output formats in return-value order.
    :param raster_dpi: Optional PNG resolution; Matplotlib defaults apply when
        omitted.
    :param bbox_inches: Matplotlib bounding-box mode, or ``None`` to disable it.
    :return: Written paths in the same order as ``formats``.
    """
    normalized_formats = tuple(str(value).lower() for value in formats)
    if not normalized_formats:
        raise ValueError("At least one figure format is required.")
    unsupported = sorted(
        set(normalized_formats).difference(_SUPPORTED_FIGURE_FORMATS)
    )
    if unsupported:
        raise ValueError(
            f"Unsupported figure formats: {', '.join(unsupported)}"
        )
    if len(set(normalized_formats)) != len(normalized_formats):
        raise ValueError("Figure formats must be unique.")
    if raster_dpi is not None and raster_dpi <= 0:
        raise ValueError("raster_dpi must be greater than zero.")

    requested_path = Path(output_path)
    requested_suffix = requested_path.suffix.lower().removeprefix(".")
    stem = (
        requested_path.with_suffix("")
        if requested_suffix in _SUPPORTED_FIGURE_FORMATS
        else requested_path
    )
    stem.parent.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for figure_format in normalized_formats:
        path = stem.with_suffix(f".{figure_format}")
        save_options: dict[str, Any] = {
            "format": figure_format,
            "bbox_inches": bbox_inches,
        }
        if figure_format == "png" and raster_dpi is not None:
            save_options["dpi"] = raster_dpi
        figure.savefig(path, **save_options)
        written_paths.append(path)
    return tuple(written_paths)


__all__ = [
    "DEFAULT_FIGURE_FORMATS",
    "FigureFormat",
    "export_figure",
]
