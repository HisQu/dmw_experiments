"""Bootstrap one run environment before importing a provider component."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from dmw_experiments.shared.config.runtime_environment import (
    bootstrap_run_environment,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Load AppRC layers, then dispatch to a backend or runner entry point.

    :param argv: Optional component command line.
    :return: Component process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("component", choices=("backend", "runner"))
    args, remaining = parser.parse_known_args(argv)
    spec = load_run_contract(args.run_dir)
    execution = spec.execution(args.execution)
    bootstrap_run_environment(
        args.run_dir,
        execution,
        require_app_wide_secrets=True,
    )
    if args.component == "runner":
        from dmw_experiments.studies.haiu_comparison.data_collection.runner import (
            main as component_main,
        )
    elif execution.name == "academiccloud":
        from dmw_experiments.studies.haiu_comparison.entrypoints.academiccloud_backend import (
            main as component_main,
        )
    else:
        from dmw_experiments.studies.haiu_comparison.entrypoints.lmstudio_backend import (
            main as component_main,
        )
    return component_main(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
