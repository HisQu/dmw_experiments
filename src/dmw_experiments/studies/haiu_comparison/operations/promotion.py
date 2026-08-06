"""Prepare a completed run for an explicit Git-tracked promotion."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dmw_experiments.shared.config.runtime_environment import (
    validate_run_environment_contract,
)
from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
    load_run_spec,
)


@dataclass(frozen=True, slots=True)
class PromotionArtifacts:
    """Report the reproducibility artifacts prepared inside a run.

    :param run_root: Complete run that remains in its current location.
    :param distribution_files: Built experiment wheel and source archive.
    :param terminal_cells: Count of preserved terminal observations.
    :param expected_cells: Count required by the enabled execution matrix.
    """

    run_root: Path
    distribution_files: tuple[Path, ...]
    terminal_cells: int
    expected_cells: int


def prepare_promotion(
    run_root: Path,
    *,
    allow_partial: bool = False,
) -> PromotionArtifacts:
    """Validate and add harness distributions without moving the run.

    :param run_root: Ignored run selected by the user for possible promotion.
    :param allow_partial: Permit an explicitly incomplete promoted dataset.
    :return: Built package paths and terminal matrix counts.
    :raises ValueError: If contracts, terminal counts, or output state fail.
    """
    root = run_root.expanduser().resolve()
    spec = load_run_spec(root)
    for execution in spec.executions:
        validate_run_environment_contract(root, execution)
    expected_units = (
        1 if spec.limit == 1 else _catalogue_size(root / spec.input_catalog)
    )
    expected = (
        expected_units * len(spec.conditions) * len(spec.enabled_executions)
    )
    terminal = sum(
        1
        for execution in spec.enabled_executions
        for condition in spec.conditions
        for _ in (
            root / execution.output_directory_name / f"result-{condition}"
        ).glob("*.json")
    )
    if not allow_partial and terminal != expected:
        raise ValueError(
            f"Run has {terminal}/{expected} terminal cells; strict promotion "
            "requires the complete enabled matrix."
        )
    distribution_dir = root / "locks" / "dist"
    distribution_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        path for path in distribution_dir.iterdir() if path.name != ".gitkeep"
    ]
    if existing:
        raise ValueError(
            "locks/dist must be empty before promotion preparation."
        )
    (distribution_dir / ".gitkeep").unlink(missing_ok=True)
    source_root = Path(__file__).resolve().parents[5]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(distribution_dir),
            str(source_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        shutil.rmtree(distribution_dir)
        distribution_dir.mkdir()
        raise RuntimeError(f"Cannot build promotion artifacts: {detail}")
    artifacts = tuple(sorted(distribution_dir.iterdir()))
    if len(artifacts) != 2:
        raise ValueError("Promotion build must create one wheel and one sdist.")
    return PromotionArtifacts(
        run_root=root,
        distribution_files=artifacts,
        terminal_cells=terminal,
        expected_cells=expected,
    )


def _catalogue_size(path: Path) -> int:
    """Count frozen input units without importing study runtime clients."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("Input catalogue has no records.")
    return len(records)


__all__ = ["PromotionArtifacts", "prepare_promotion"]
