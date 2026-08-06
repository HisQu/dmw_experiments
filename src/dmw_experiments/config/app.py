"""dmw_experiments-bound AppRC application contract."""

from __future__ import annotations

# == 3rd Party ===============================
import apprc as rc

APP_RC = rc.AppRC.storage_only(
    app_name="dmw_experiments",
    display_name="dmw_experiments",
    config_package="dmw_experiments.config",
    storage_env_key="DMW_EXPERIMENTS_STORAGE",
    command_name="dmw_experiments",
    index_filename="dmw_experiments.apprc.toml",
    shared_env_filename=".env.shared",
    storage_env_filename=".env.apprc-storage",
)
