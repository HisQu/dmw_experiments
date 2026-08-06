#!/usr/bin/env python3
"""Validate and render a non-secret header--sublemma run plan before launch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.operations.run_spec import (
    HeaderSublemmaRunSpec,
    load_header_sublemma_run_spec,
)
from dmw_experiments.studies.haiu_comparison.paths import (
    REPOSITORY_ROOT,
    STUDY_ROOT,
)

EXPERIMENT_ROOT = STUDY_ROOT
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "output"


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the run-plan validation command.

    :return: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument(
        "--allow-existing-result-directory",
        action="store_true",
        help="Permit a result directory only when inspecting a known resume plan.",
    )
    return parser


def _plan(
    spec: HeaderSublemmaRunSpec,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, object]:
    """Render the non-secret identities checked before service launch.

    :param spec: Validated run specification.
    :return: JSON-serializable service-independent launch plan.
    """
    return {
        "schema_version": spec.schema_version,
        "run_id": spec.run_id,
        "provider_profile": spec.provider_profile,
        "source_branch": spec.source_branch,
        "target_branch": spec.target_branch,
        "raw_collection": spec.raw_collection,
        "annotation_collection": spec.annotation_collection,
        "ontology_collection": spec.ontology_collection,
        "ontology_context_version": spec.ontology_context_version,
        "input_catalog": spec.input_catalog.as_posix(),
        "limit": spec.limit,
        "conditions": list(spec.conditions),
        "max_output_tokens": spec.max_output_tokens,
        "output_safety_margin_tokens": spec.output_safety_margin_tokens,
        "ontology_example_limit": spec.ontology_example_limit,
        "result_directory": spec.result_directory(output_root)
        .relative_to(output_root)
        .as_posix(),
    }


def main() -> int:
    """Validate one plan without connecting to DMW, MongoDB, or a provider.

    :return: Zero when the specification is safe to hand to the launcher.
    """
    args = _parser().parse_args()
    spec = load_header_sublemma_run_spec(args.spec)
    spec.validate(EXPERIMENT_ROOT)
    result_directory = spec.result_directory(DEFAULT_OUTPUT_ROOT)
    if result_directory.exists() and not args.allow_existing_result_directory:
        raise SystemExit(
            "Result directory already exists. Use a new run_id, or explicitly "
            "inspect an existing resume plan."
        )
    print(json.dumps(_plan(spec), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
