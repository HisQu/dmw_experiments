"""dmw_experiments runtime configuration declarations.

This module is the application-owned inventory that AppRC reuses for runtime
loading, validation, documentation, the generated config CLI, and the Textual
editor. Add new settings here before reading them from your runtime code.
"""

from __future__ import annotations

# == Standard Library ========================
from pathlib import Path

# == 3rd Party ===============================
import apprc as rc

# == Internal ================================
from dmw_experiments.config.app import APP_RC


@APP_RC.config(
    "app",
    prefix="DMW_EXPERIMENTS_",
    title="App",
)
class AppRuntimeConfig(rc.Config):
    """Typed application settings loaded from AppRC-managed env layers."""

    storage_root: Path = rc.field(
        "DMW_EXPERIMENTS_STORAGE",
        title="Storage root",
        explanation_short="Active local data root selected by AppRC.",
        explanation_long=(
            "The storage root is selected through the user-level AppRC "
            "selector, not by editing a packaged dotenv file."
        ),
        editable=False,
        required=True,
    )
    message: str = rc.field(
        "DMW_EXPERIMENTS_MESSAGE",
        default="Hello from dmw_experiments",
        title="Example message",
        explanation_short="Small editable example setting.",
        explanation_long=(
            "This field exists so a new scaffold immediately demonstrates "
            "`dmw_experiments config set app.message VALUE` and the Textual "
            "config editor. Replace it with real application settings."
        ),
    )
