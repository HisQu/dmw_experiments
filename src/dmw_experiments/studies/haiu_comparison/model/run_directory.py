"""Paths owned by one copied Haiu comparison run directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.model.conditions import (
    ConditionId,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    RUN_CONTRACT_FILENAME,
    ProviderExecutionSpec,
    RunContract,
    load_run_contract,
)


@dataclass(frozen=True, slots=True)
class HaiuComparisonRun:
    """Provide the authoritative model and paths for one copied run.

    The copied directory is the operational boundary of the study. Keeping
    path construction next to its validated contract prevents preparation,
    collection, and analysis code from inventing competing layouts.

    :param root: Absolute copied-run directory.
    :param contract: Validated ``run.toml`` contents for ``root``.
    """

    root: Path
    contract: RunContract

    @classmethod
    def open(cls, root: Path) -> HaiuComparisonRun:
        """Open and validate an existing copied run.

        :param root: Directory containing ``run.toml`` and run artifacts.
        :return: Validated run boundary with canonical path helpers.
        """
        resolved = root.expanduser().resolve()
        return cls(root=resolved, contract=load_run_contract(resolved))

    @property
    def contract_path(self) -> Path:
        """Return the authoritative TOML contract path.

        :return: ``run.toml`` inside this run.
        """
        return self.root / RUN_CONTRACT_FILENAME

    @property
    def input_catalog_path(self) -> Path:
        """Return the frozen input catalogue selected by the contract.

        :return: Absolute catalogue path.
        """
        return self.root / self.contract.input_catalog

    @property
    def lock_directory(self) -> Path:
        """Return the environment and package-lock evidence directory.

        :return: Run-local ``locks`` directory.
        """
        return self.root / "locks"

    @property
    def log_directory(self) -> Path:
        """Return the operator and service log directory.

        :return: Run-local ``logs`` directory.
        """
        return self.root / "logs"

    @property
    def analysis_directory(self) -> Path:
        """Return the root of derived analysis artifacts.

        :return: Run-local ``analysis`` directory.
        """
        return self.root / "analysis"

    @property
    def plot_directory(self) -> Path:
        """Return the final plot export directory.

        :return: Run-local ``plots`` directory.
        """
        return self.root / "plots"

    def execution(self, name: str) -> ProviderExecutionSpec:
        """Return one provider execution declared by the run.

        :param name: Stable provider execution identifier.
        :return: Matching execution contract.
        """
        return self.contract.execution(name)

    def raw_directory(self, execution: str | ProviderExecutionSpec) -> Path:
        """Return the raw artifact root for one provider execution.

        :param execution: Execution name or its validated contract.
        :return: Top-level ``raw-<execution>`` directory.
        """
        spec = (
            execution
            if isinstance(execution, ProviderExecutionSpec)
            else self.execution(execution)
        )
        return self.root / spec.output_directory_name

    def intermediate_directory(
        self,
        execution: str | ProviderExecutionSpec,
        condition: str | ConditionId,
    ) -> Path:
        """Return pipeline intermediates for one measured cell.

        :param execution: Execution name or its validated contract.
        :param condition: Scientific condition identifier.
        :return: Existing run-local intermediate directory.
        """
        return self.raw_directory(execution) / f"intermediates-{condition}"

    def result_directory(
        self,
        execution: str | ProviderExecutionSpec,
        condition: str | ConditionId,
    ) -> Path:
        """Return terminal results for one measured cell.

        :param execution: Execution name or its validated contract.
        :param condition: Scientific condition identifier.
        :return: Existing run-local result directory.
        """
        return self.raw_directory(execution) / f"result-{condition}"
