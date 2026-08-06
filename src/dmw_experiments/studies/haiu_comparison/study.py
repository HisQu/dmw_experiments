"""Supported Python façade for the complete Haiu comparison lifecycle."""

from __future__ import annotations

from pathlib import Path

from dmw_experiments.shared.artifacts import RunWorkspace
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.studies.haiu_comparison.analysis.pipeline import (
    AnalysisArtifacts,
    run_analysis,
)
from dmw_experiments.studies.haiu_comparison.operations.lifecycle import (
    ExperimentLifecycle,
)
from dmw_experiments.studies.haiu_comparison.operations.promotion import (
    PromotionArtifacts,
    prepare_promotion,
)
from dmw_experiments.studies.haiu_comparison.operations.run_factory import (
    NewRunRequest,
    create_run,
)
from dmw_experiments.studies.haiu_comparison.operations.status import RunStatus


class HaiuComparisonStudy:
    """Expose the supported run lifecycle without internal module knowledge.

    The façade keeps the CLI and external Python callers on the same path. Raw
    collection adapters, workbook implementations, and process launchers stay
    private implementation details behind these lifecycle operations.

    :param config: Resolved experiment-owned AppRC settings.
    """

    def __init__(self, config: AppRuntimeConfig) -> None:
        self._lifecycle = ExperimentLifecycle(config=config)

    def new_run(
        self,
        *,
        run_id: str,
        mode: str,
        executions: tuple[str, ...],
    ) -> Path:
        """Copy and initialize one tracked study template.

        :param run_id: Portable run and directory identifier.
        :param mode: ``smoke`` for one unit or ``full`` for the population.
        :param executions: Provider executions enabled for this run.
        :return: Newly created ignored run directory.
        """
        return create_run(
            NewRunRequest(
                run_id=run_id,
                mode=mode,
                executions=executions,
            )
        )

    def validate(
        self,
        run_dir: Path,
        *,
        executions: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Validate contracts, settings, storage identities, and runtime.

        :param run_dir: Complete copied run directory.
        :param executions: Optional provider filter.
        :return: Non-secret launch plan.
        """
        return self._lifecycle.validate(
            run_dir,
            execution_names=executions,
        )

    def start(
        self,
        run_dir: Path,
        *,
        executions: tuple[str, ...] = (),
    ) -> tuple[RunWorkspace, ...]:
        """Prepare fresh storage and start supervised provider services.

        :param run_dir: Complete copied run directory.
        :param executions: Optional provider filter.
        :return: Provider workspaces started for this invocation.
        """
        return self._lifecycle.start(
            run_dir,
            execution_names=executions,
        )

    def resume(
        self,
        run_dir: Path,
        *,
        executions: tuple[str, ...] = (),
    ) -> tuple[RunWorkspace, ...]:
        """Resume frozen settings and durable checkpoints.

        :param run_dir: Existing copied run directory.
        :param executions: Optional provider filter.
        :return: Provider workspaces resumed for this invocation.
        """
        return self._lifecycle.resume(
            run_dir,
            execution_names=executions,
        )

    def pause(
        self,
        run_dir: Path,
        *,
        executions: tuple[str, ...] = (),
    ) -> RunStatus:
        """Stop provider services in checkpoint-safe order.

        :param run_dir: Existing copied run directory.
        :param executions: Optional provider filter.
        :return: Durable status after services stop.
        """
        return self._lifecycle.pause(
            run_dir,
            execution_names=executions,
        )

    def status(
        self,
        run_dir: Path,
        *,
        executions: tuple[str, ...] = (),
    ) -> RunStatus:
        """Report durable cell counts and provider service state.

        :param run_dir: Existing copied run directory.
        :param executions: Optional provider filter.
        :return: Aggregated progress for selected executions.
        """
        return self._lifecycle.status(
            run_dir,
            execution_names=executions,
        )

    def analyze(
        self,
        run_dir: Path,
        *,
        allow_partial: bool = False,
        audit_csv: bool = False,
        overwrite: bool = False,
        timestamp: str | None = None,
        quality_review_workbook: Path | None = None,
        quality_reveal_key: Path | None = None,
    ) -> AnalysisArtifacts:
        """Regenerate every derived artifact from preserved raw data.

        :param run_dir: Complete copied run directory.
        :param allow_partial: Permit labelled diagnostics before completion.
        :param audit_csv: Export machine-readable audit tables.
        :param overwrite: Replace exporter-owned derived files.
        :param timestamp: Optional stable plot timestamp.
        :param quality_review_workbook: Optional evaluated blinded workbook.
        :param quality_reveal_key: Reveal key matching the evaluated workbook.
        :return: Workbook, review, and plot paths.
        """
        return run_analysis(
            run_dir=run_dir,
            allow_partial=allow_partial,
            audit_csv=audit_csv,
            overwrite=overwrite,
            timestamp=timestamp,
            quality_review_workbook=quality_review_workbook,
            quality_reveal_key=quality_reveal_key,
        )

    def prepare_promotion(
        self,
        run_dir: Path,
        *,
        allow_partial: bool = False,
    ) -> PromotionArtifacts:
        """Validate a selected dataset and build reproducibility archives.

        :param run_dir: Ignored run selected for possible Git promotion.
        :param allow_partial: Permit an explicitly incomplete dataset.
        :return: Built distribution paths and terminal matrix counts.
        """
        return prepare_promotion(run_dir, allow_partial=allow_partial)
