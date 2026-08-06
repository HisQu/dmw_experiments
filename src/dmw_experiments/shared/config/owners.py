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
from dmw_experiments.shared.config.app import APP_RC

UNSET_PATH = Path(".not-configured")


@APP_RC.config(
    "app",
    prefix="DMW_EXPERIMENTS_",
    title="App",
)
class AppRuntimeConfig(rc.Config):
    """Typed application settings loaded from AppRC-managed env layers."""

    storage_root: Path = rc.field(
        "DMW_EXPERIMENTS_STORAGE",
        default=Path("output"),
        title="Storage root",
        explanation_short="Root for all runs, analyses, and local logs.",
        explanation_long=(
            "The default is the repository-local output directory. AppRC may "
            "select another storage root without changing a run specification."
        ),
        editable=False,
    )
    publication_python: Path = rc.field(
        "DMW_EXPERIMENTS_PUBLICATION_PYTHON",
        default=UNSET_PATH,
        title="Published DMW Python",
        explanation_short="Python executable containing the frozen DMW stack.",
        explanation_long=(
            "Execution commands require an environment containing published "
            "DMW 1.1.3, OPA 2.1.2, GTA 0.2.4, and Haiu 1.8.0 releases."
        ),
    )
    academiccloud_env_file: Path = rc.field(
        "DMW_EXPERIMENTS_ACADEMICCLOUD_ENV_FILE",
        default=UNSET_PATH,
        title="AcademicCloud environment file",
        explanation_short=(
            "Ignored DMW, MongoDB, and AcademicCloud runtime configuration."
        ),
    )
    lmstudio_env_file: Path = rc.field(
        "DMW_EXPERIMENTS_LMSTUDIO_ENV_FILE",
        default=UNSET_PATH,
        title="LM Studio environment file",
        explanation_short="Ignored local LM Studio provider configuration.",
    )
    watchdog_stall_seconds: int = rc.field(
        "DMW_EXPERIMENTS_WATCHDOG_STALL_SECONDS",
        default=14_400,
        title="Watchdog stall limit",
        explanation_short="Seconds without a checkpoint before interruption.",
    )
