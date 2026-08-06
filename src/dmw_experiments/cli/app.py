"""Typer command tree for dmw_experiments."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any, TypeVar

import apprc as rc
import typer

import dmw_experiments
from dmw_experiments.shared.config import APP_RC
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.studies.haiu_comparison import (
    HaiuComparisonStudy,
)

PACKAGE_NAME = "dmw_experiments"
VERSION_FALLBACK = "0.3.0"
LOG = logging.getLogger(__name__)
T = TypeVar("T")

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


def _study() -> HaiuComparisonStudy:
    """Construct the supported study façade from resolved AppRC settings.

    :return: Complete Haiu comparison lifecycle for this invocation.
    """
    return HaiuComparisonStudy(config=AppRuntimeConfig())


def _run_lifecycle(action: Callable[[], T]) -> T:
    """Run one lifecycle operation with concise terminal diagnostics.

    :param action: Zero-argument callable containing one requested operation.
    :return: Operation result.
    """
    try:
        return action()
    except (OSError, RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _execution_filter(execution: list[str] | None) -> tuple[str, ...]:
    """Normalize repeated provider options for lifecycle methods.

    :param execution: Repeated ``--execution`` values or ``None``.
    :return: Immutable provider selection.
    """
    return tuple(execution or ())


@app.command("new-run")
def new_run_cmd(
    run_id: Annotated[str, typer.Option(help="Portable run identifier.")],
    mode: Annotated[
        str,
        typer.Option(help="Run area and unit limit: smoke or full."),
    ],
    execution: Annotated[
        list[str] | None,
        typer.Option(
            "--execution",
            help="Enable academiccloud or lmstudio. Repeat for both.",
        ),
    ] = None,
    study: Annotated[
        str,
        typer.Option(help="Study template. Only haiu_comparison exists."),
    ] = "haiu_comparison",
) -> None:
    """Copy a complete tracked template into an ignored run area."""
    if study != "haiu_comparison":
        raise typer.BadParameter("Only haiu_comparison is available.")
    path = _run_lifecycle(
        lambda: _study().new_run(
            run_id=run_id,
            mode=mode,
            executions=_execution_filter(execution),
        )
    )
    typer.echo(path)


@app.command("validate")
def validate_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    execution: Annotated[
        list[str] | None,
        typer.Option("--execution", help="Optional provider filter."),
    ] = None,
) -> None:
    """Validate the run, AppRC sources, storage identities, and runtime."""
    payload = _run_lifecycle(
        lambda: _study().validate(
            run_dir,
            executions=_execution_filter(execution),
        )
    )
    rc.cli.dump_json(payload)


@app.command("start")
def start_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    execution: Annotated[
        list[str] | None,
        typer.Option("--execution", help="Optional provider filter."),
    ] = None,
) -> None:
    """Prepare fresh storage and start selected provider services."""
    workspaces = _run_lifecycle(
        lambda: _study().start(
            run_dir,
            executions=_execution_filter(execution),
        )
    )
    for workspace in workspaces:
        typer.echo(f"Started {workspace.execution}: {workspace.babysit_log}")


@app.command("resume")
def resume_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    execution: Annotated[
        list[str] | None,
        typer.Option("--execution", help="Optional provider filter."),
    ] = None,
) -> None:
    """Resume the same run from durable checkpoints and frozen settings."""
    workspaces = _run_lifecycle(
        lambda: _study().resume(
            run_dir,
            executions=_execution_filter(execution),
        )
    )
    for workspace in workspaces:
        typer.echo(f"Resumed {workspace.execution}: {workspace.babysit_log}")


@app.command("pause")
def pause_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    execution: Annotated[
        list[str] | None,
        typer.Option("--execution", help="Optional provider filter."),
    ] = None,
) -> None:
    """Stop an active run in checkpoint-safe service order."""
    status = _run_lifecycle(
        lambda: _study().pause(
            run_dir,
            executions=_execution_filter(execution),
        )
    )
    rc.cli.dump_json(asdict(status))


@app.command("status")
def status_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    execution: Annotated[
        list[str] | None,
        typer.Option("--execution", help="Optional provider filter."),
    ] = None,
) -> None:
    """Report durable cell counts and current service states."""
    status = _run_lifecycle(
        lambda: _study().status(
            run_dir,
            executions=_execution_filter(execution),
        )
    )
    rc.cli.dump_json(asdict(status))


@app.command("analyze")
def analyze_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    quality_review_workbook: Annotated[
        Path | None,
        typer.Option(help="Optional evaluated historian-review workbook."),
    ] = None,
    quality_reveal_key: Annotated[
        Path | None,
        typer.Option(help="Reveal key matching the evaluated review workbook."),
    ] = None,
    allow_partial: Annotated[
        bool,
        typer.Option(help="Permit explicitly labelled partial exports."),
    ] = False,
    audit_csv: Annotated[
        bool,
        typer.Option(help="Also export raw-derived audit CSV tables."),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite/--no-overwrite",
            help=(
                "Replace exporter-owned derived run files. Human grade "
                "inputs and existing timestamped plot directories remain "
                "immutable."
            ),
        ),
    ] = True,
) -> None:
    """Regenerate workbooks, review packets, and plots from raw data."""
    artifacts = _run_lifecycle(
        lambda: _study().analyze(
            run_dir,
            allow_partial=allow_partial,
            audit_csv=audit_csv,
            overwrite=overwrite,
            quality_review_workbook=quality_review_workbook,
            quality_reveal_key=quality_reveal_key,
        )
    )
    typer.echo(f"Analysis written: {artifacts.plots}")


@app.command("prepare-promotion")
def prepare_promotion_cmd(
    run_dir: Annotated[Path, typer.Option(help="Copied run directory.")],
    allow_partial: Annotated[
        bool,
        typer.Option(help="Permit an explicitly incomplete promoted run."),
    ] = False,
) -> None:
    """Validate a run and build its experiment-package artifacts."""
    result = _run_lifecycle(
        lambda: _study().prepare_promotion(
            run_dir,
            allow_partial=allow_partial,
        )
    )
    typer.echo(
        f"Prepared {result.terminal_cells}/{result.expected_cells} cells."
    )
    for path in result.distribution_files:
        typer.echo(path)


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
