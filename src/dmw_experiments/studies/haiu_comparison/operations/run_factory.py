"""Create actual run directories from the tracked study template."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    EXECUTION_PROVIDER_PROFILES,
    RUN_NAME,
    load_run_contract,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    FULL_RUNS_ROOT,
    RUN_TEMPLATE_ROOT,
    SMOKE_RUNS_ROOT,
)


@dataclass(frozen=True, slots=True)
class NewRunRequest:
    """Describe one safe template copy.

    :param run_id: Portable directory and scientific run identity.
    :param mode: ``smoke`` or ``full``.
    :param executions: Provider execution names to enable.
    """

    run_id: str
    mode: str
    executions: tuple[str, ...]

    def validate(self) -> None:
        """Reject invalid identities before copying data.

        :return: ``None`` when the request can initialize a run.
        """
        if not RUN_NAME.fullmatch(self.run_id):
            raise ValueError(
                "run_id must use lowercase letters, digits, and hyphens."
            )
        if self.mode not in {"smoke", "full"}:
            raise ValueError("mode must be 'smoke' or 'full'.")
        if not self.executions:
            raise ValueError("Select at least one --execution.")
        unknown = sorted(
            set(self.executions) - set(EXECUTION_PROVIDER_PROFILES)
        )
        if unknown:
            raise ValueError("Unknown executions: " + ", ".join(unknown))
        if len(self.executions) != len(set(self.executions)):
            raise ValueError("Do not repeat an execution name.")


def create_run(request: NewRunRequest) -> Path:
    """Copy and initialize one complete run directory.

    :param request: Validated identity, mode, and providers.
    :return: New run root in the mode-specific ignored area.
    :raises FileExistsError: If the destination already exists.
    """
    request.validate()
    destination_parent = (
        SMOKE_RUNS_ROOT if request.mode == "smoke" else FULL_RUNS_ROOT
    )
    destination = destination_parent / request.run_id
    if destination.exists():
        raise FileExistsError(f"Run already exists: {destination}")
    destination_parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(RUN_TEMPLATE_ROOT, destination)
    _initialize_run_toml(destination / "run.toml", request=request)
    _initialize_readme(destination / "README.md", request=request)
    spec = load_run_contract(destination)
    if tuple(execution.name for execution in spec.enabled_executions) != (
        request.executions
    ):
        raise RuntimeError(
            "Initialized run executions differ from the request."
        )
    return destination


def _initialize_run_toml(path: Path, *, request: NewRunRequest) -> None:
    """Replace template identities without introducing a TOML writer."""
    text = path.read_text(encoding="utf-8")
    text = text.replace('run_id = "template"', f'run_id = "{request.run_id}"')
    text = text.replace('mode = "full"', f'mode = "{request.mode}"')
    text = text.replace(
        "limit = 0", f"limit = {1 if request.mode == 'smoke' else 0}"
    )
    storage_slug = request.run_id.replace("-", "_")
    for execution in EXECUTION_PROVIDER_PROFILES:
        enabled = "true" if execution in request.executions else "false"
        pattern = (
            rf"(\[executions\.{re.escape(execution)}\]\n)"
            rf"enabled = (?:true|false)"
        )
        text, count = re.subn(
            pattern,
            rf"\1enabled = {enabled}",
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Template is missing executions.{execution}.")
        text = text.replace(
            f'target_branch = "template_{execution}"',
            f'target_branch = "{storage_slug}_{execution}"',
        )
        text = text.replace(
            f'raw_collection = "RG_raw_template_{execution}"',
            f'raw_collection = "RG_raw_{storage_slug}_{execution}"',
        )
    path.write_text(text, encoding="utf-8")


def _initialize_readme(path: Path, *, request: NewRunRequest) -> None:
    """Give the copied run a factual identity and edit prompt."""
    text = path.read_text(encoding="utf-8")
    providers = ", ".join(request.executions)
    text = text.replace("# Run: template", f"# Run: {request.run_id}")
    text = text.replace(
        "Replace this paragraph with the concrete purpose, date, providers, and scope\n"
        "of the copied run.",
        f"Mode: `{request.mode}`. Enabled executions: `{providers}`. Replace "
        "this sentence with the concrete scientific purpose before launch.",
    )
    path.write_text(text, encoding="utf-8")
