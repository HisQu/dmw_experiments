"""Typer command tree for dmw_experiments."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any, TypeVar

import apprc as rc
import typer

import dmw_experiments
from dmw_experiments.shared.config import APP_RC
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.studies.haiu_comparison.operations.lifecycle import (
    ExperimentLifecycle,
)
from dmw_experiments.studies.haiu_comparison.paths import (
    REPOSITORY_ROOT,
    SPEC_ROOT,
)

PACKAGE_NAME = "dmw_experiments"
VERSION_FALLBACK = "0.2.0"
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


def _lifecycle() -> ExperimentLifecycle:
    """Construct the application lifecycle from resolved AppRC settings.

    :return: Lifecycle facade for the current CLI invocation.
    """
    return ExperimentLifecycle(config=AppRuntimeConfig())


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


def _analysis_output_root() -> Path:
    """Resolve the configured generated-analysis directory.

    :return: Absolute parent for timestamped analysis exports.
    """
    storage_root = AppRuntimeConfig().storage_root.expanduser()
    if not storage_root.is_absolute():
        storage_root = REPOSITORY_ROOT / storage_root
    return storage_root.resolve() / "analyses"


@app.command("validate")
def validate_cmd(
    spec: Annotated[
        Path,
        typer.Option(
            "--spec",
            help="Tracked run specification to validate without launching.",
        ),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-smoke.json",
) -> None:
    """Validate the scientific, storage, and local runtime contract."""
    payload = _run_lifecycle(lambda: _lifecycle().validate(spec))
    rc.cli.dump_json(payload)


@app.command("smoke")
def smoke_cmd(
    spec: Annotated[
        Path,
        typer.Option("--spec", help="Disposable one-unit smoke contract."),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-smoke.json",
) -> None:
    """Prepare and start the isolated one-unit AcademicCloud smoke."""
    workspace = _run_lifecycle(
        lambda: _lifecycle().launch(spec, expected_mode="smoke")
    )
    typer.echo(f"Smoke started: {workspace.root}")
    typer.echo(f"Babysit log: {workspace.babysit_log}")


@app.command("run")
def run_cmd(
    spec: Annotated[
        Path,
        typer.Option("--spec", help="Complete experiment run contract."),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-full.json",
) -> None:
    """Prepare and start the complete isolated AcademicCloud matrix."""
    workspace = _run_lifecycle(
        lambda: _lifecycle().launch(spec, expected_mode="full")
    )
    typer.echo(f"Run started: {workspace.root}")
    typer.echo(f"Babysit log: {workspace.babysit_log}")


@app.command("resume")
def resume_cmd(
    spec: Annotated[
        Path,
        typer.Option(
            "--spec", help="Original contract of the interrupted run."
        ),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-full.json",
) -> None:
    """Resume the same run from durable checkpoints and frozen settings."""
    workspace = _run_lifecycle(lambda: _lifecycle().resume(spec))
    typer.echo(f"Run resumed: {workspace.root}")
    typer.echo(f"Babysit log: {workspace.babysit_log}")


@app.command("pause")
def pause_cmd(
    spec: Annotated[
        Path,
        typer.Option("--spec", help="Original contract of the active run."),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-full.json",
) -> None:
    """Stop an active run in checkpoint-safe service order."""
    status = _run_lifecycle(lambda: _lifecycle().pause(spec))
    rc.cli.dump_json(asdict(status))


@app.command("status")
def status_cmd(
    spec: Annotated[
        Path,
        typer.Option("--spec", help="Original contract of the run to inspect."),
    ] = SPEC_ROOT / "academiccloud-header-sublemma-full.json",
) -> None:
    """Report durable cell counts and current service states."""
    status = _run_lifecycle(lambda: _lifecycle().status(spec))
    rc.cli.dump_json(asdict(status))


@app.command("analyze")
def analyze_cmd(
    academiccloud_run: Annotated[
        Path,
        typer.Option(
            "--academiccloud-run",
            help="AcademicCloud run directory containing raw observations.",
        ),
    ],
    lmstudio_run: Annotated[
        Path,
        typer.Option(
            "--lmstudio-run",
            help="LM Studio run directory containing raw observations.",
        ),
    ],
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
    from dmw_experiments.studies.haiu_comparison.run_analysis import (
        run_analysis,
    )

    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%Z")
    output_root = _analysis_output_root() / timestamp
    review = output_root / "historian_quality_review.xlsx"
    artifacts = _run_lifecycle(
        lambda: run_analysis(
            academiccloud_run_dir=academiccloud_run,
            lmstudio_run_dir=lmstudio_run,
            provider_review_workbook=review,
            output_root=output_root,
            allow_partial=allow_partial,
            audit_csv=audit_csv,
            overwrite=overwrite,
            timestamp=timestamp,
            quality_review_workbook=quality_review_workbook,
            quality_reveal_key=quality_reveal_key,
        )
    )
    typer.echo(f"Analysis written: {artifacts.plots.parent}")


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
