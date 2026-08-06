#!/usr/bin/env python3
"""Materialize Stage-1, Turtle, and YAML documents from raw result JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.comparison_experiment.artifacts import (
    ArtifactWriter,
)


def main(argv: list[str] | None = None) -> int:
    """Write derived raw documents for one existing experiment run.

    :param argv: Optional argument vector.
    :return: Process exit code.
    """
    args = _build_parser().parse_args(argv)
    run_dir = args.run_dir.expanduser().resolve()
    writer = ArtifactWriter(run_dir)
    counts = writer.materialize_existing_raw_documents()
    print(
        f"Materialized {counts['stage1']} Stage-1 reply, {counts['ttl']} "
        f"Turtle, and {counts['yaml']} YAML result artifact(s), with "
        f"{counts['stage1_unavailable']} Stage-1 reply/replies transparently "
        f"unavailable from preserved evidence; plus "
        f"{counts['retrieved_ttl']} retrieved Turtle and "
        f"{counts['retrieved_yaml']} retrieved YAML artifact(s) under "
        f"{run_dir}."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    :return: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Materialize raw_stage1, raw_ttl, and raw_yaml documents without "
            "replacing active aggregate checkpoints."
        )
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Existing comparison run directory containing raw/*.json.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
