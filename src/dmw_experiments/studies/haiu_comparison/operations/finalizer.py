#!/usr/bin/env python3
"""Wait for complete provider matrices, then create final derived artifacts.

This operational helper deliberately reads immutable raw observations until the
strict exporter contract can succeed. It never starts, stops, retries, or
rewrites an experiment condition. Once both matrices are complete it
materializes derived raw sidecars and invokes the one-command analysis runner
without ``--allow-partial``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


CONDITIONS = (
    "workflow_full_ontology",
    "workflow_rag",
    "haiu_rag_ontologizer",
)


@dataclass(frozen=True, slots=True)
class RunMatrixStatus:
    """Describe whether one provider has finished its expected condition grid.

    :param expected_cells: Number of condition and regest combinations in the
        immutable run manifest.
    :param raw_cells: Number of those combinations with a raw JSON result.
    :param missing_cells: Expected combinations without a raw JSON result.
    :param retry_pending_cells: Observations still marked for an ordinary
        retry; these are not terminal experiment rows.
    """

    expected_cells: int
    raw_cells: int
    missing_cells: tuple[str, ...]
    retry_pending_cells: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """State whether this matrix meets the final-export precondition.

        :return: ``True`` only when every expected cell exists and none is
            awaiting an ordinary retry.
        """
        return not self.missing_cells and not self.retry_pending_cells


def inspect_run_matrix(run_dir: Path) -> RunMatrixStatus:
    """Read the durable result state needed before publication export.

    The check intentionally mirrors the exporter's treatment of a
    ``retry_pending`` attempt: a raw failure checkpoint exists for crash
    recovery, but is not yet a terminal experimental observation.

    :param run_dir: Provider-specific ``RESULTS/<run-id>`` directory.
    :return: Complete matrix status derived from its frozen run manifest.
    :raises ValueError: If the required run manifest or attempt state is not a
        JSON object with scheduled identifiers.
    """
    manifest = _load_object(run_dir / "summaries" / "run_manifest.json")
    regest_ids = manifest.get("regest_ids")
    if not isinstance(regest_ids, list) or not regest_ids:
        raise ValueError(f"Run manifest has no regest_ids: {run_dir}")
    expected = tuple(
        (condition, str(regest_id))
        for condition in CONDITIONS
        for regest_id in regest_ids
    )
    missing: list[str] = []
    retry_pending: list[str] = []
    raw_cells = 0
    for condition, regest_id in expected:
        cell = f"{condition}/{regest_id}"
        raw_path = run_dir / "raw" / condition / f"{regest_id}.json"
        if not raw_path.is_file():
            missing.append(cell)
            continue
        raw_cells += 1
        attempt_path = run_dir / "attempts" / condition / f"{regest_id}.json"
        if (
            attempt_path.is_file()
            and _load_object(attempt_path).get("status") == "retry_pending"
        ):
            retry_pending.append(cell)
    return RunMatrixStatus(
        expected_cells=len(expected),
        raw_cells=raw_cells,
        missing_cells=tuple(missing),
        retry_pending_cells=tuple(retry_pending),
    )


def wait_for_complete_matrices(
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    *,
    poll_seconds: float,
) -> None:
    """Block until both providers satisfy the final-export precondition.

    :param academiccloud_run_dir: AcademicCloud results directory.
    :param lmstudio_run_dir: LM Studio results directory.
    :param poll_seconds: Delay between durable-state inspections.
    :return: ``None`` once both matrices are complete.
    """
    previous: tuple[RunMatrixStatus, RunMatrixStatus] | None = None
    while True:
        statuses = (
            inspect_run_matrix(academiccloud_run_dir),
            inspect_run_matrix(lmstudio_run_dir),
        )
        if statuses != previous:
            _print_status("AcademicCloud", statuses[0])
            _print_status("LM Studio", statuses[1])
            previous = statuses
        if all(status.is_complete for status in statuses):
            return
        time.sleep(poll_seconds)


def run_final_analysis(
    *,
    experiment_dir: Path,
    analysis_python: Path,
    materialize_script: Path,
    analysis_script: Path,
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    output_root: Path,
    quality_review_workbook: Path,
    quality_reveal_key: Path,
    timestamp: str | None,
) -> None:
    """Materialize raw sidecars and invoke the strict final analysis command.

    :param experiment_dir: Experiment directory used as the command cwd.
    :param analysis_python: Interpreter with experiment export dependencies.
    :param materialize_script: Artifact-materialization command entrypoint.
    :param analysis_script: One-command analysis entrypoint.
    :param academiccloud_run_dir: Complete AcademicCloud result directory.
    :param lmstudio_run_dir: Complete LM Studio result directory.
    :param output_root: Shared parent for final derived artifacts.
    :param quality_review_workbook: Immutable evaluated historian workbook.
    :param quality_reveal_key: Matching immutable reveal key.
    :param timestamp: Optional fixed export timestamp.
    :return: ``None`` after all final commands succeed.
    :raises subprocess.CalledProcessError: If a materialization or analysis
        command exits unsuccessfully.
    """
    materialization_commands = (
        (
            "AcademicCloud sidecars",
            [analysis_python, materialize_script, academiccloud_run_dir],
        ),
        (
            "LM Studio sidecars",
            [analysis_python, materialize_script, lmstudio_run_dir],
        ),
    )
    for label, command in materialization_commands:
        print(f"Finalizing {label}.", flush=True)
        subprocess.run(
            [str(part) for part in command],
            check=True,
            cwd=experiment_dir,
        )
    analysis_command: list[Path | str] = [
        analysis_python,
        analysis_script,
        academiccloud_run_dir,
        lmstudio_run_dir,
        "--overwrite",
        "--audit-csv",
        "--output-root",
        output_root,
        "--quality-review-workbook",
        quality_review_workbook,
        "--quality-reveal-key",
        quality_reveal_key,
    ]
    if timestamp is not None:
        analysis_command.extend(("--timestamp", timestamp))
    print("Exporting final workbooks, review packet, and plots.", flush=True)
    subprocess.run(
        [str(part) for part in analysis_command],
        check=True,
        cwd=experiment_dir,
    )


def _load_object(path: Path) -> dict[str, object]:
    """Load one required JSON mapping without guessing missing state.

    :param path: JSON file to read.
    :return: Parsed JSON mapping.
    :raises ValueError: If the file does not contain a JSON object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _print_status(provider: str, status: RunMatrixStatus) -> None:
    """Write a compact, durable-state progress line for an operator.

    :param provider: Display name of the inspected provider.
    :param status: Matrix status to report.
    :return: ``None`` after writing one line.
    """
    print(
        f"{provider}: {status.raw_cells}/{status.expected_cells} raw cells; "
        f"missing={len(status.missing_cells)}; "
        f"retry_pending={len(status.retry_pending_cells)}.",
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the operational finalization interface.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Wait for two complete experiment matrices and export final "
            "derived artifacts."
        )
    )
    parser.add_argument("academiccloud_run_dir", type=Path)
    parser.add_argument("lmstudio_run_dir", type=Path)
    parser.add_argument("--analysis-python", type=Path, required=True)
    parser.add_argument("--quality-review-workbook", type=Path, required=True)
    parser.add_argument("--quality-reveal-key", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--timestamp")
    parser.add_argument("--poll-seconds", type=float, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Wait safely, then create final publication-facing derived artifacts.

    :param argv: Optional command-line arguments.
    :return: Zero after successful materialization and strict final analysis.
    """
    args = _parser().parse_args(argv)
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive.")
    experiment_dir = Path(__file__).resolve().parent.parent
    analysis_python = args.analysis_python.expanduser().resolve()
    academiccloud_run_dir = args.academiccloud_run_dir.expanduser().resolve()
    lmstudio_run_dir = args.lmstudio_run_dir.expanduser().resolve()
    quality_review_workbook = (
        args.quality_review_workbook.expanduser().resolve()
    )
    quality_reveal_key = args.quality_reveal_key.expanduser().resolve()
    for required_path in (
        analysis_python,
        quality_review_workbook,
        quality_reveal_key,
    ):
        if not required_path.is_file():
            raise ValueError(
                f"Required finalization input is missing: {required_path}"
            )
    output_root = (
        args.output_root.expanduser().resolve()
        if args.output_root is not None
        else _shared_results_parent(academiccloud_run_dir, lmstudio_run_dir)
    )
    wait_for_complete_matrices(
        academiccloud_run_dir,
        lmstudio_run_dir,
        poll_seconds=args.poll_seconds,
    )
    run_final_analysis(
        experiment_dir=experiment_dir,
        analysis_python=analysis_python,
        materialize_script=experiment_dir / "materialize_raw_artifacts.py",
        analysis_script=experiment_dir / "run_analysis.py",
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        output_root=output_root,
        quality_review_workbook=quality_review_workbook,
        quality_reveal_key=quality_reveal_key,
        timestamp=args.timestamp,
    )
    return 0


def _shared_results_parent(
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
) -> Path:
    """Require the common result parent instead of guessing an output path.

    :param academiccloud_run_dir: AcademicCloud result directory.
    :param lmstudio_run_dir: LM Studio result directory.
    :return: Shared result-directory parent.
    :raises ValueError: If the provider directories are not siblings.
    """
    if academiccloud_run_dir.parent != lmstudio_run_dir.parent:
        raise ValueError("Provider result directories must share one parent.")
    return academiccloud_run_dir.parent


if __name__ == "__main__":
    raise SystemExit(main())
