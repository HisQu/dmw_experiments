"""Command-line arguments for one raw data-collection process."""

from __future__ import annotations

import argparse

from dmw_experiments.studies.haiu_comparison.data_collection.protocol import (
    DEFAULT_ANNOTATION_GUIDELINES_FILE,
    DEFAULT_CONDITIONS,
    DEFAULT_PROMPT_FILE,
)
from dmw_experiments.studies.haiu_comparison.model.providers import (
    PROVIDER_PROFILES,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the low-level provider-runner argument contract.

    :return: Parser used by user-systemd provider services and focused tests.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Compare direct Haiu ontology generation with "
            "datamodel-workflow modes."
        )
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--login", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--ids-file", default="")
    input_group.add_argument(
        "--input-catalog",
        default="",
        help=(
            "Frozen header--sublemma catalogue. Pair publication runs require "
            "AcademicCloud and all three conditions."
        ),
    )
    parser.add_argument(
        "--dmw-input-manifest",
        default="",
        help="Import manifest written by the DMW storage preparer.",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--keep-duplicates", action="store_true")
    parser.add_argument(
        "--missing-id-policy",
        choices=("skip", "fail"),
        default="skip",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=DEFAULT_CONDITIONS,
        default=list(DEFAULT_CONDITIONS),
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--output-cap-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for a resumed replay of terminal "
            "output-cap failures. Requires --rerun-output-truncated-at-cap."
        ),
    )
    parser.add_argument(
        "--rerun-output-truncated-at-cap",
        type=int,
        default=None,
        help=(
            "Replay only terminal output-truncated observations whose stage "
            "used this requested and effective cap."
        ),
    )
    parser.add_argument(
        "--provider-timeout-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for replaying exhausted provider-timeout "
            "results that were already selected by --output-cap-recovery-id."
        ),
    )
    parser.add_argument(
        "--connection-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for replaying exhausted connection "
            "failures after the local provider becomes reachable again."
        ),
    )
    parser.add_argument(
        "--local-runtime-recovery-id",
        default="",
        help=(
            "Immutable amendment ID for a corrected local model context, "
            "proxy mapping, or recorded HTTP 502 initial-response replay."
        ),
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=30.0)
    parser.add_argument("--annotation-max-attempts", type=int, default=3)
    parser.add_argument("--progress-poll-seconds", type=float, default=2.0)
    parser.add_argument("--env-file", action="append", default=[])
    parser.add_argument("--storage", default=None)
    parser.add_argument(
        "--provenance-file",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help=(
            "Additional frozen input, such as reference_ontology=... or "
            "environment_lock=.... Repeat for each file."
        ),
    )
    parser.add_argument(
        "--publication-run",
        action="store_true",
        help=(
            "Require reference_ontology, retrieval_workspace, and "
            "environment_lock provenance inputs before creating the run."
        ),
    )
    parser.add_argument(
        "--provider-profile",
        choices=tuple(PROVIDER_PROFILES),
        default="academiccloud-qwen36",
        help=(
            "Pinned Qwen 3.6 27B provider environment. The exact provider "
            "model identifier is selected by this profile."
        ),
    )
    parser.add_argument("--base-url-override", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-output-tokens", type=int, default=60_000)
    parser.add_argument(
        "--direct-max-tokens",
        dest="max_output_tokens",
        type=int,
        default=argparse.SUPPRESS,
        help=(
            "Deprecated alias for --max-output-tokens. The cap now applies "
            "to every ontology-generation condition."
        ),
    )
    parser.add_argument(
        "--output-safety-margin-tokens",
        type=int,
        default=4_096,
    )
    parser.add_argument("--ontology-example-limit", type=int, default=1)
    parser.add_argument("--direct-temperature", type=float, default=0.6)
    parser.add_argument("--direct-top-p", type=float, default=0.95)
    parser.add_argument("--direct-top-k", type=int, default=20)
    parser.add_argument("--direct-min-p", type=float, default=0.0)
    parser.add_argument("--direct-frequency-penalty", type=float, default=0.0)
    parser.add_argument("--direct-presence-penalty", type=float, default=0.0)
    parser.add_argument("--annotation-model", default="")
    parser.add_argument("--annotation-guideline-version", default="1.5.8")
    parser.add_argument("--annotation-min-version", default=None)
    parser.add_argument("--annotation-top-n", type=int, default=5)
    parser.add_argument("--annotation-example-limit", type=int, default=10)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--ontology-context-version", required=True)
    parser.add_argument("--ontology-min-example-version", default="1.0.0")
    parser.add_argument(
        "--ontology-user-input-file", default=str(DEFAULT_PROMPT_FILE)
    )
    parser.add_argument(
        "--annotation-guidelines-file",
        default=str(DEFAULT_ANNOTATION_GUIDELINES_FILE),
    )
    parser.add_argument(
        "--use-only-existing-ontology-terms", action="store_true"
    )
    parser.set_defaults(include_annotations=True)
    parser.add_argument(
        "--include-annotations", dest="include_annotations", action="store_true"
    )
    parser.add_argument(
        "--no-include-annotations",
        dest="include_annotations",
        action="store_false",
    )
    return parser
