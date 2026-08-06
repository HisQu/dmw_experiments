"""Typer command tree for dmw_experiments."""

from __future__ import annotations

import logging
import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any

import apprc as rc
import typer

import dmw_experiments
from dmw_experiments.config import APP_RC

PACKAGE_NAME = "dmw_experiments"
VERSION_FALLBACK = "0.1.0"
LOG = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=True,
    help="Command-line tools for dmw_experiments.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _package_version() -> str:
    """Return the installed package version.

    :return: Installed package metadata version, or the scaffold fallback when
        running from ``PYTHONPATH`` before installation.
    """
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return VERSION_FALLBACK


def _diagnose_payload() -> dict[str, Any]:
    """Build a stable diagnostic payload for support reports.

    :return: JSON-friendly process, package, and import metadata.
    """
    spec = APP_RC.spec
    index_path = spec.index_path()
    return {
        "config_home": str(spec.config_home()),
        "cwd": str(Path.cwd()),
        "index_env_key": spec.index_env_key,
        "index_path": str(index_path),
        "package": PACKAGE_NAME,
        "package_file": str(Path(dmw_experiments.__file__).resolve()),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "storage_env_filename": spec.storage_env_filename,
        "storage_env_key": spec.storage_env_key,
        "version": _package_version(),
    }


def _config_show_payload(state: rc.cli.DefaultConfigCliState) -> dict[str, Any]:
    """Build a small resolved-runtime payload for ``config show``.

    :param state: Root CLI state created by AppRC's Typer integration.
    :return: JSON-friendly package and AppRC bootstrap metadata.
    """
    env_bootstrap = state.env_bootstrap
    spec = APP_RC.spec
    return {
        "app_wide_env": (
            None
            if env_bootstrap is None or env_bootstrap.app_wide_env is None
            else str(env_bootstrap.app_wide_env)
        ),
        "env_files": (
            []
            if env_bootstrap is None
            else [str(path) for path in env_bootstrap.env_files]
        ),
        "index_env_key": spec.index_env_key,
        "index_path": (
            None
            if env_bootstrap is None or env_bootstrap.index_path is None
            else str(env_bootstrap.index_path)
        ),
        "package": PACKAGE_NAME,
        "shared_env": (
            None
            if env_bootstrap is None or env_bootstrap.shared_env is None
            else str(env_bootstrap.shared_env)
        ),
        "storage": state.storage,
        "storage_count": 0
        if env_bootstrap is None
        else env_bootstrap.storage_count,
        "storage_env": (
            None
            if env_bootstrap is None or env_bootstrap.storage_env is None
            else str(env_bootstrap.storage_env)
        ),
        "storage_env_key": spec.storage_env_key,
        "storage_name": None
        if env_bootstrap is None
        else env_bootstrap.storage_name,
        "storage_root": (
            None
            if env_bootstrap is None or env_bootstrap.storage_root is None
            else str(env_bootstrap.storage_root)
        ),
        "storage_selector_source": (
            None
            if env_bootstrap is None
            else env_bootstrap.storage_selector_source
        ),
        "storage_selector_value": (
            None
            if env_bootstrap is None
            else env_bootstrap.storage_selector_value
        ),
        "version": _package_version(),
    }


def _setup_app_logging(level: str | int = "INFO", **_: object) -> None:
    """Configure stdlib logging for one CLI invocation.

    :param level: Logging level name or number supplied by AppRC.
    :param _: Extra logger-specific keyword arguments ignored by this scaffold.
    :return: None.
    """

    logging.basicConfig(level=level)


def _echo_diagnose_payload(payload: dict[str, Any]) -> None:
    """Print a human-readable diagnostic payload.

    :param payload: Diagnostic values returned by :func:`_diagnose_payload`.
    :return: None.
    """
    for key in sorted(payload):
        typer.echo(f"{key}: {payload[key]}")


APP_RC.mount_cli(
    app,
    runtime_policy=rc.cli.CliRuntimePolicy(
        runtime_independent_commands={
            "version": rc.cli.RuntimeIndependentCommand(skip_empty=True),
            "diagnose": rc.cli.RuntimeIndependentCommand(skip_empty=True),
        },
        extra_cli_flag_options={"--json"},
    ),
    runtime_payload=_config_show_payload,
    setup_logging=_setup_app_logging,
    logger=LOG,
)


@app.command("version")
def version_cmd() -> None:
    """Print the installed package version."""
    typer.echo(_package_version())


@app.command("diagnose")
def diagnose_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    """Print local package and Python diagnostics."""
    payload = _diagnose_payload()
    if json_output:
        rc.cli.dump_json(payload)
        return
    _echo_diagnose_payload(payload)


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
