"""Matplotlib font registration and reusable paper-style defaults."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_PAPER_FONTSIZE = 10
DEFAULT_SANS_SERIF_STACK: tuple[str, ...] = (
    "Liberation Sans Narrow",
    "DejaVu Sans",
)


def _default_font_dir() -> Path:
    """Return the font directory shipped with the experiment package."""
    return Path(__file__).resolve().parent / "fonts"


def _xdg_config_home() -> Path:
    """Return the current XDG config home or the platform-default fallback."""
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config"


def _xdg_cache_home() -> Path:
    """Return the current XDG cache home or the platform-default fallback."""
    configured = os.environ.get("XDG_CACHE_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache"


def _current_matplotlib_config_dir() -> Path:
    """Return the current Matplotlib config dir without importing Matplotlib."""
    configured = os.environ.get("MPLCONFIGDIR")
    if configured:
        return Path(configured).expanduser()
    return _xdg_config_home() / "matplotlib"


def _dir_is_writable(path: Path) -> bool:
    """Return whether one directory exists and is writable."""
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def _ensure_writable_dir(path: Path) -> Path | None:
    """Create one directory if needed and return it when writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path if _dir_is_writable(path) else None


def ensure_matplotlib_cache_dir() -> Path:
    """Ensure Matplotlib uses a stable writable config/cache directory."""
    current_dir = _current_matplotlib_config_dir()
    if _dir_is_writable(current_dir):
        return current_dir

    preferred_candidates = (
        _xdg_cache_home() / "dmw_experiments" / "matplotlib",
        Path(tempfile.gettempdir()) / "dmw_experiments" / "matplotlib",
    )
    for candidate in preferred_candidates:
        ensured = _ensure_writable_dir(candidate)
        if ensured is None:
            continue
        os.environ["MPLCONFIGDIR"] = str(ensured)
        return ensured
    raise OSError("Unable to create a writable Matplotlib config directory.")


def register_repo_fonts(font_dir: Path | None = None) -> None:
    """Register vendored TTF/OTF fonts with Matplotlib."""
    ensure_matplotlib_cache_dir()
    from matplotlib import font_manager as fm

    resolved_font_dir = (
        _default_font_dir() if font_dir is None else Path(font_dir).expanduser()
    )
    if not resolved_font_dir.is_dir():
        raise FileNotFoundError(
            f"Font directory not found: {resolved_font_dir}"
        )

    for pattern in ("*.ttf", "*.otf"):
        for font_path in sorted(resolved_font_dir.glob(pattern)):
            fm.fontManager.addfont(font_path)


def paper_rc_params(
    fontsize: int = DEFAULT_PAPER_FONTSIZE,
) -> dict[Any, Any]:
    """Return the experiment's reusable paper-style Matplotlib preset."""
    return {
        "figure.dpi": 200,
        "figure.figsize": (3, 3),
        "figure.facecolor": "white",
        "savefig.dpi": 300,
        "savefig.format": "pdf",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        # == Font
        "font.family": "sans-serif",
        "font.sans-serif": list(DEFAULT_SANS_SERIF_STACK),
        "font.size": fontsize,
        "font.weight": "bold",  # <
        # == Titles Axes
        "axes.titlesize": fontsize + 1,
        "axes.titleweight": "bold",
        "axes.titlepad": 5,
        # == Grid
        "grid.linestyle": "-",
        "grid.linewidth": 0.5,
        # == Spines / Edges
        # "lines.linewidth": 0.75, # < All lines
        "axes.spines.right": True,
        "axes.spines.top": True,
        "axes.linewidth": 0.75,
        # == Labels for x- and y-axis
        "axes.labelweight": "bold",
        "axes.labelsize": fontsize,
        # == Ticks
        "ytick.left": True,
        "xtick.labelsize": fontsize - 1,
        "ytick.labelsize": fontsize - 1,
        "ytick.major.pad": 0.9,
        "ytick.minor.pad": 0.8,
        "xtick.major.pad": 2,
        "xtick.minor.pad": 2,
        "ytick.major.size": 2.5,
        "ytick.minor.size": 2,
        "xtick.major.size": 2.5,
        "xtick.minor.size": 2,
        # -- Legend
        "legend.fancybox": False,
        "legend.title_fontsize": fontsize,
        "legend.fontsize": fontsize,
        "legend.markerscale": 1.3,
        "legend.handleheight": 0.7,
        "legend.handletextpad": 0.1,
        "legend.borderpad": 0.1,
    }


def configure_matplotlib_defaults(
    fontsize: int = DEFAULT_PAPER_FONTSIZE,
) -> None:
    """Register packaged fonts and apply default paper-style rcParams."""
    ensure_matplotlib_cache_dir()
    import matplotlib as mpl

    register_repo_fonts()
    mpl.rcParams.update(paper_rc_params(fontsize=fontsize))


def paper_rc_context(fontsize: int = DEFAULT_PAPER_FONTSIZE) -> Any:
    """Return one temporary Matplotlib context with paper defaults."""
    ensure_matplotlib_cache_dir()
    import matplotlib as mpl

    return mpl.rc_context(rc=paper_rc_params(fontsize=fontsize))


__all__ = [
    "DEFAULT_PAPER_FONTSIZE",
    "DEFAULT_SANS_SERIF_STACK",
    "configure_matplotlib_defaults",
    "ensure_matplotlib_cache_dir",
    "paper_rc_context",
    "paper_rc_params",
    "register_repo_fonts",
]
