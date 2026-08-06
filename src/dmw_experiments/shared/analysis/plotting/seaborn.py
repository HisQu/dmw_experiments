"""Small seaborn-facing plotting helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pandas as pd
from matplotlib.colors import to_rgba

from haiu.utils.pd import numeric_series

# -- Linewidths
THIN, THICK = 0.3, 1.0
# -- Alpha values for different plot elements
COVERING, TRANSLUCENT, HAZY = 1.0, 0.5, 0.3
# -- Z-order values
FRONT, MID, BACKGROUND, HIDDEN = 100, 50, 1, -1

DEFAULT_WIDTH = 0.6
OVERLAY_STRIP_FACE_ALPHA = 0.2
OVERLAY_STRIP_EDGE_ALPHA = 0.7
DEFAULT_OVERLAY_STRIP_KWS: dict[str, Any] = dict(
    alpha=TRANSLUCENT,
    size=2.5,
    linewidth=THIN,
    edgecolor="none",
    jitter=0.15,
    # dodge=True,
    zorder=FRONT,
)


DEFAULT_BOXPLOT_KWS: dict[str, Any] = dict(
    showfliers=False,
    boxprops=dict(  #' Box line and surface
        alpha=HAZY,
        linewidth=THIN,
    ),
    medianprops=dict(  #' Median line
        alpha=COVERING,
        zorder=FRONT,
        linewidth=THICK,
    ),
    whiskerprops=dict(  #' Lines conencting box and caps
        alpha=COVERING,
        zorder=MID,
        linewidth=THIN,
    ),
    capprops=dict(  #' Caps at the end of whiskers
        alpha=COVERING,
        zorder=BACKGROUND,
        linewidth=THICK,
    ),
)


def upper_whisker_position(
    values: pd.Series,
    *,
    whis: float | tuple[float, float] = 1.5,
) -> float | None:
    """Return the upper whisker position for one plotted distribution."""
    clean = numeric_series(values, errors="coerce").dropna()
    if clean.empty:
        return None
    if isinstance(whis, tuple):
        upper_percentile = float(whis[1]) / 100.0
        return float(clean.quantile(upper_percentile))

    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    iqr = q3 - q1
    if iqr == 0:
        return float(clean.max())
    upper_limit = q3 + float(whis) * iqr
    inlier_values = cast(pd.Series, clean.loc[clean <= upper_limit])
    if inlier_values.empty:
        return float(q3)
    return float(inlier_values.max())


def restyle_overlay_strip_collections(
    collections: Sequence[Any],
    *,
    face_alpha: float = OVERLAY_STRIP_FACE_ALPHA,
    edge_alpha: float = OVERLAY_STRIP_EDGE_ALPHA,
) -> None:
    """Restyle strip collections with transparent fills and solid hue edges."""
    for collection in collections:
        # !! Dynamic boundary: Matplotlib collection subclasses do not all expose alpha setters.
        set_alpha = getattr(collection, "set_alpha", None)
        if callable(set_alpha):
            set_alpha(None)
        facecolors = collection.get_facecolors()
        if len(facecolors):
            collection.set_facecolors(
                [to_rgba(color, face_alpha) for color in facecolors]
            )
            collection.set_edgecolors(
                [to_rgba(color, edge_alpha) for color in facecolors]
            )
            continue
        edgecolors = collection.get_edgecolors()
        if len(edgecolors):
            collection.set_edgecolors(
                [to_rgba(color, edge_alpha) for color in edgecolors]
            )


def restyle_collections(
    collections: Sequence[Any],
    *,
    face_alpha: float = OVERLAY_STRIP_FACE_ALPHA,
    edge_alpha: float = OVERLAY_STRIP_EDGE_ALPHA,
) -> None:
    """Restyle matplotlib collections with separate face and edge alpha."""
    restyle_overlay_strip_collections(
        collections,
        face_alpha=face_alpha,
        edge_alpha=edge_alpha,
    )
