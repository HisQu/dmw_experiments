#!/usr/bin/env python3
"""Materialize Stage-1, Turtle, and YAML documents from raw result JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.data_collection.artifacts import (
    ArtifactWriter,
)


def main(argv: list[str] | None = None) -> int:
    """Write derived raw documents for one existing experiment run.

    :param argv: Optional argument vector.
    :return: Process exit code.
    """
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    writer = ArtifactWriter(output_dir)
    counts = writer.materialize_existing_raw_documents()
    print(
        f"Materialized {counts['stage1']} Stage-1 reply, {counts['ttl']} "
        f"Turtle, and {counts['yaml']} YAML result artifact(s), with "
        f"{counts['stage1_unavailable']} Stage-1 reply/replies transparently "
        f"unavailable from preserved evidence; plus "
        f"{counts['retrieved_ttl']} retrieved Turtle and "
        f"{counts['retrieved_yaml']} retrieved YAML artifact(s) under "
        f"{output_dir}."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    :return: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Materialize Stage-1, Turtle, and YAML documents from terminal "
            "JSON without replacing aggregate checkpoints."
        )
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Existing raw-<execution> directory containing result-* JSON.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
