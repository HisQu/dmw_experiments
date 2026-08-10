"""Run-directory lifecycle for independently supervised provider executions."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dmw_experiments.shared.artifacts import RunWorkspace
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.shared.config.runtime_environment import (
    ResolvedRunEnvironment,
    bootstrap_run_environment,
    validate_run_environment_contract,
)
from dmw_experiments.shared.supervision import ServiceUnits, UserServiceManager
from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ExecutionArtifactLayout,
)
from dmw_experiments.studies.haiu_comparison.data_collection.artifacts import (
    ArtifactWriter,
)
from dmw_experiments.studies.haiu_comparison.model.inputs import (
    load_dmw_pair_import_manifest,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.model.providers import (
    provider_profile,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    ProviderExecutionSpec,
    RunContract,
    load_run_contract,
)
from dmw_experiments.studies.haiu_comparison.operations.artifact_migration import (
    ArtifactLayoutMigrator,
    ArtifactMigrationReport,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    REPOSITORY_ROOT,
)
from dmw_experiments.studies.haiu_comparison.operations.runtime import (
    RuntimePaths,
)
from dmw_experiments.studies.haiu_comparison.operations.runtime_transition import (
    RuntimeTransitionReport,
    record_runtime_transition,
)
from dmw_experiments.studies.haiu_comparison.operations.status import (
    ExecutionStatus,
    RunStatus,
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
BACKEND_URLS = {
    "academiccloud": "http://127.0.0.1:8000",
    "lmstudio": "http://127.0.0.1:8001",
}


class ExperimentLifecycle:
    """Validate, start, pause, resume, and inspect one copied run."""

    def __init__(
        self,
        *,
        config: AppRuntimeConfig,
        services: UserServiceManager | None = None,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        self.config = config
        self.services = services or UserServiceManager()
        self._command_runner = command_runner

    def validate(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
        require_credentials: bool = True,
    ) -> dict[str, Any]:
        """Validate a complete run without preparing storage or services.

        :param run_root: Copied run directory.
        :param execution_names: Optional enabled execution filter.
        :param require_credentials: Whether AppRC app-wide secrets must exist.
        :return: Portable non-secret launch plan.
        """
        spec = load_run_contract(run_root)
        runtime = RuntimePaths.from_config(self.config)
        runtime.validate()
        executions = self._selected_executions(spec, execution_names)
        plans = {}
        for execution in executions:
            validate_run_environment_contract(run_root.resolve(), execution)
            resolved = bootstrap_run_environment(
                run_root,
                execution,
                require_app_wide_secrets=require_credentials,
            )
            plans[execution.name] = {
                "provider_profile": execution.provider_profile,
                "population_units": self._population_units(spec, run_root),
                "expected_cells": self._population_units(spec, run_root)
                * len(spec.conditions),
                "output_directory": execution.output_directory_name,
                "storage": {
                    "branch": execution.target_branch,
                    "raw_collection": execution.raw_collection,
                    "annotation_collection": execution.annotation_collection,
                    "ontology_collection": execution.ontology_collection,
                },
                "service_units": asdict(
                    ServiceUnits.for_run(spec.run_id, execution.name)
                ),
                "config_origins": {
                    key: value["origin"]
                    for key, value in resolved.provenance_payload().items()
                },
            }
        return {
            "schema_version": spec.schema_version,
            "study": spec.study,
            "mode": spec.mode,
            "run_id": spec.run_id,
            "conditions": list(spec.conditions),
            "executions": plans,
        }

    def start(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> tuple[RunWorkspace, ...]:
        """Prepare and launch every selected enabled execution independently.

        :param run_root: Copied run directory.
        :param execution_names: Optional provider filter.
        :return: Workspaces whose services started successfully.
        """
        return self._start_or_resume(
            run_root,
            execution_names=execution_names,
            resume=False,
        )

    def resume(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> tuple[RunWorkspace, ...]:
        """Resume selected executions with their exact frozen contract.

        :param run_root: Existing copied run directory.
        :param execution_names: Optional provider filter.
        :return: Workspaces whose services restarted successfully.
        """
        return self._start_or_resume(
            run_root,
            execution_names=execution_names,
            resume=True,
        )

    def pause(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> RunStatus:
        """Stop selected providers in checkpoint-safe order.

        :param run_root: Existing copied run directory.
        :param execution_names: Optional provider filter.
        :return: Aggregate durable status after stopping services.
        """
        spec = load_run_contract(run_root)
        for execution in self._selected_executions(spec, execution_names):
            workspace = RunWorkspace.open(run_root, execution.name)
            units = ServiceUnits.for_run(spec.run_id, execution.name)
            self.services.stop(units.watchdog)
            self.services.interrupt(units.runner)
            deadline = time.monotonic() + 20
            while (
                self.services.is_active(units.runner)
                and time.monotonic() < deadline
            ):
                time.sleep(1)
            self.services.stop(units.runner)
            self.services.stop(units.backend)
            workspace.append_event(
                event="execution_paused",
                detail="Stopped watchdog, runner, and backend in safe order.",
            )
            workspace.append_babysit(
                heading="Execution paused",
                bullets=(
                    "Stopped the watchdog before interrupting the runner.",
                    "Preserved every terminal result and attempt checkpoint.",
                ),
            )
        return self.status(run_root)

    def status(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> RunStatus:
        """Count terminal observations and inspect selected services.

        :param run_root: Existing copied run directory.
        :param execution_names: Optional provider filter.
        :return: Per-provider and aggregate progress.
        """
        spec = load_run_contract(run_root)
        statuses = {
            execution.name: self._execution_status(
                spec=spec,
                execution=execution,
                run_root=run_root.resolve(),
            )
            for execution in self._selected_executions(spec, execution_names)
        }
        return RunStatus(
            run_id=spec.run_id,
            expected_cells=sum(
                item.expected_cells for item in statuses.values()
            ),
            terminal_cells=sum(
                item.terminal_cells for item in statuses.values()
            ),
            successful_cells=sum(
                item.successful_cells for item in statuses.values()
            ),
            failed_cells=sum(item.failed_cells for item in statuses.values()),
            retry_pending_cells=sum(
                item.retry_pending_cells for item in statuses.values()
            ),
            strict_analysis_ready=bool(statuses)
            and all(item.strict_analysis_ready for item in statuses.values()),
            executions=statuses,
        )

    def migrate_artifacts(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> tuple[ArtifactMigrationReport, ...]:
        """Convert stopped legacy provider outputs into schema-v3 bundles.

        :param run_root: Existing copied run directory.
        :param execution_names: Optional enabled provider filter.
        :return: One verified migration report per selected execution.
        :raises RuntimeError: If any selected service can still write evidence.
        """
        spec = load_run_contract(run_root)
        reports: list[ArtifactMigrationReport] = []
        for execution in self._selected_executions(spec, execution_names):
            self._require_execution_stopped(
                spec=spec,
                execution=execution,
                operation="artifact migration",
            )
            workspace = RunWorkspace.open(run_root, execution.name)
            report = ArtifactLayoutMigrator(
                run_root=run_root,
                execution=execution.name,
            ).migrate()
            workspace.append_event(
                event="artifact_layout_migrated",
                detail=(
                    "Converted verified provider evidence from schema v2 to "
                    "schema v3."
                ),
                source_schema_version=report.source_schema_version,
                target_schema_version=report.target_schema_version,
                terminal_cells=report.terminal_cells,
                backup=report.backup,
            )
            workspace.append_babysit(
                heading="Artifact layout migrated",
                bullets=(
                    "Paused services before changing artifact paths.",
                    (
                        f"Converted and verified {report.terminal_cells} "
                        "terminal cells without changing their source payloads."
                    ),
                    (
                        f"Retained the hash-inventoried schema-v2 snapshot at "
                        f"`{report.backup}`."
                    ),
                    (
                        "Resume uses the same scientific contract through the "
                        "recorded harness-only artifact migration."
                    ),
                ),
            )
            reports.append(report)
        return tuple(reports)

    def refresh_artifacts(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], ...]:
        """Rebuild deterministic terminal projections from exact raw payloads.

        :param run_root: Existing copied run directory.
        :param execution_names: Optional enabled provider filter.
        :return: Refresh counts for each selected execution.
        :raises RuntimeError: If any selected service can still write evidence.
        """
        spec = load_run_contract(run_root)
        reports: list[dict[str, Any]] = []
        for execution in self._selected_executions(spec, execution_names):
            self._require_execution_stopped(
                spec=spec,
                execution=execution,
                operation="artifact refresh",
            )
            workspace = RunWorkspace.open(run_root, execution.name)
            writer = ArtifactWriter(run_root / execution.output_directory_name)
            counts = writer.refresh_terminal_projections()
            writer.write_final_outputs(writer.load_existing_rows())
            report = {"execution": execution.name, **counts}
            workspace.append_event(
                event="terminal_artifacts_refreshed",
                detail=(
                    "Rebuilt deterministic projections from exact retained "
                    "provider payloads."
                ),
                **counts,
            )
            reports.append(report)
        return tuple(reports)

    def adopt_runtime_transition(
        self,
        run_root: Path,
        *,
        reason: str,
        execution_names: tuple[str, ...] = (),
    ) -> tuple[RuntimeTransitionReport, ...]:
        """Record a stopped run's exact harness and Haiu patch transition.

        :param run_root: Existing copied run directory.
        :param reason: Concise operational reason for the patch.
        :param execution_names: Optional enabled provider filter.
        :return: One durable transition report per selected execution.
        :raises RuntimeError: If any selected service can still write evidence.
        """
        spec = load_run_contract(run_root)
        reports: list[RuntimeTransitionReport] = []
        for execution in self._selected_executions(spec, execution_names):
            self._require_execution_stopped(
                spec=spec,
                execution=execution,
                operation="runtime transition",
            )
            report = record_runtime_transition(
                run_root=run_root,
                execution=execution.name,
                reason=reason,
            )
            workspace = RunWorkspace.open(run_root, execution.name)
            workspace.append_event(
                event="runtime_transition_adopted",
                detail=reason,
                source_harness_commit=report.source_harness_commit,
                target_harness_commit=report.target_harness_commit,
                source_haiu_version=report.source_haiu_version,
                target_haiu_version=report.target_haiu_version,
            )
            reports.append(report)
        return tuple(reports)

    def _require_execution_stopped(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        operation: str,
    ) -> None:
        """Reject derived-data or identity changes while services are active.

        :param spec: Frozen run contract.
        :param execution: Selected provider execution.
        :param operation: Human-readable requested operation.
        :return: None when all three provider services are inactive.
        :raises RuntimeError: If any provider service remains active.
        """
        units = ServiceUnits.for_run(spec.run_id, execution.name)
        active = [
            unit
            for unit in asdict(units).values()
            if self.services.is_active(unit)
        ]
        if active:
            raise RuntimeError(
                f"Pause the execution before {operation}: " + ", ".join(active)
            )

    def _start_or_resume(
        self,
        run_root: Path,
        *,
        execution_names: tuple[str, ...],
        resume: bool,
    ) -> tuple[RunWorkspace, ...]:
        spec = load_run_contract(run_root)
        runtime = RuntimePaths.from_config(self.config)
        runtime.validate()
        started: list[RunWorkspace] = []
        errors: list[str] = []
        for execution in self._selected_executions(spec, execution_names):
            workspace = RunWorkspace.open(run_root, execution.name)
            try:
                if resume:
                    workspace.require_frozen_contract()
                else:
                    workspace.freeze_contract()
                self._require_no_other_execution_run(
                    execution,
                    allowed=ServiceUnits.for_run(spec.run_id, execution.name)
                    if resume
                    else None,
                )
                resolved = bootstrap_run_environment(
                    run_root,
                    execution,
                    require_app_wide_secrets=True,
                )
                self._prepare_haiu_storage(
                    workspace=workspace,
                    execution=execution,
                    resume=resume,
                )
                if resume:
                    manifest, environment_lock = self._resume_artifacts(
                        workspace
                    )
                else:
                    manifest = self._prepare_storage(
                        spec=spec,
                        execution=execution,
                        runtime=runtime,
                        workspace=workspace,
                        resolved=resolved,
                    )
                    environment_lock = self._capture_environment_lock(
                        spec=spec,
                        execution=execution,
                        runtime=runtime,
                        workspace=workspace,
                        resolved=resolved,
                        dmw_input_manifest=manifest,
                    )
                self._start_services(
                    spec=spec,
                    execution=execution,
                    runtime=runtime,
                    workspace=workspace,
                    resolved=resolved,
                    dmw_input_manifest=manifest,
                    environment_lock=environment_lock,
                    resume=resume,
                )
                started.append(workspace)
            except BaseException as error:
                workspace.append_event(
                    event="resume_failed" if resume else "launch_failed",
                    detail=str(error),
                    error_type=type(error).__name__,
                )
                workspace.append_babysit(
                    heading="Resume failed" if resume else "Launch failed",
                    bullets=(
                        f"Provider execution did not start: {error}",
                        "Other provider executions remain independent.",
                    ),
                )
                errors.append(f"{execution.name}: {error}")
        if errors:
            raise RuntimeError("; ".join(errors))
        return tuple(started)

    def _prepare_haiu_storage(
        self,
        *,
        workspace: RunWorkspace,
        execution: ProviderExecutionSpec,
        resume: bool,
    ) -> Path:
        """Create or verify the run-owned Haiu AppRC storage root.

        Haiu validates its selected storage during ``HaiuRC`` construction.
        The lifecycle must therefore establish this derived run directory
        before it starts either the backend or collection runner.

        :param workspace: Provider-specific view of the copied run.
        :param execution: Provider execution owning the storage.
        :param resume: Whether an earlier launch must already own the root.
        :return: Absolute run-local Haiu storage directory.
        :raises ValueError: If resume evidence lacks its storage root.
        """
        storage = workspace.environment / f"haiu-{execution.name}"
        if resume:
            if not storage.is_dir():
                raise ValueError(
                    "Cannot resume without Haiu storage: " + storage.name
                )
            return storage
        storage.mkdir()
        return storage

    def _resume_artifacts(self, workspace: RunWorkspace) -> tuple[Path, Path]:
        manifest = workspace.environment / (
            f"{workspace.execution}-dmw-input-manifest.json"
        )
        lock = workspace.environment / (
            f"{workspace.execution}-environment-lock.json"
        )
        runner_manifest = (
            workspace.root / f"raw-{workspace.execution}" / "manifest.json"
        )
        legacy_runner_manifest = workspace.environment / (
            f"{workspace.execution}-run-manifest.json"
        )
        if not runner_manifest.is_file() and legacy_runner_manifest.is_file():
            runner_manifest = legacy_runner_manifest
        for required in (manifest, lock, runner_manifest):
            if not required.is_file():
                raise ValueError(
                    f"Cannot resume without immutable artifact: {required.name}"
                )
        return manifest, lock

    def _selected_executions(
        self,
        spec: RunContract,
        names: tuple[str, ...],
    ) -> tuple[ProviderExecutionSpec, ...]:
        if not names:
            return spec.enabled_executions
        if len(names) != len(set(names)):
            raise ValueError("Do not repeat --execution.")
        selected = tuple(spec.execution(name) for name in names)
        disabled = [
            execution.name for execution in selected if not execution.enabled
        ]
        if disabled:
            raise ValueError(
                "Selected executions are disabled: " + ", ".join(disabled)
            )
        return selected

    def _population_units(self, spec: RunContract, run_root: Path) -> int:
        if spec.limit == 1:
            return 1
        catalogue = load_header_sublemma_catalog(run_root / spec.input_catalog)
        return len(catalogue.records)

    def _execution_status(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        run_root: Path,
    ) -> ExecutionStatus:
        output = run_root / execution.output_directory_name
        artifact_layout = ExecutionArtifactLayout(output)
        results_by_key: dict[tuple[str, str], Path] = {}
        for condition, result_path in artifact_layout.iter_result_records():
            if condition in spec.conditions:
                results_by_key[(condition, result_path.parent.name)] = (
                    result_path
                )
        for (
            condition,
            result_path,
        ) in artifact_layout.iter_legacy_result_records():
            if condition in spec.conditions:
                results_by_key.setdefault(
                    (condition, result_path.stem),
                    result_path,
                )
        result_paths = tuple(results_by_key.values())
        successes = 0
        failures = 0
        for path in result_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            outcome = (
                payload.get("outcome") if isinstance(payload, dict) else None
            )
            success = (
                outcome.get("success")
                if isinstance(outcome, dict)
                else payload.get("success")
                if isinstance(payload, dict)
                else False
            )
            if bool(success):
                successes += 1
            else:
                failures += 1
        attempts = tuple(
            path
            for condition in spec.conditions
            for pattern in ("*/checkpoint.json", "*.attempt.json")
            for path in (output / f"intermediates-{condition}").glob(pattern)
        )
        retry_pending = sum(
            1 for path in attempts if _attempt_status(path) == "retry_pending"
        )
        expected = self._population_units(spec, run_root) * len(spec.conditions)
        units = ServiceUnits.for_run(spec.run_id, execution.name)
        service_states = {
            role: self.services.active_state(unit)
            for role, unit in asdict(units).items()
        }
        return ExecutionStatus(
            execution=execution.name,
            expected_cells=expected,
            terminal_cells=len(result_paths),
            successful_cells=successes,
            failed_cells=failures,
            retry_pending_cells=retry_pending,
            strict_analysis_ready=len(result_paths) == expected
            and retry_pending == 0,
            services=service_states,
        )

    def _require_no_other_execution_run(
        self,
        execution: ProviderExecutionSpec,
        *,
        allowed: ServiceUnits | None,
    ) -> None:
        allowed_names = set(asdict(allowed).values()) if allowed else set()
        marker = f"-{execution.name}-"
        active = tuple(
            unit
            for unit in self.services.active_experiment_units()
            if marker in unit and unit not in allowed_names
        )
        if active:
            raise RuntimeError(
                f"Another {execution.name} experiment is active: "
                + ", ".join(active)
            )

    def _prepare_storage(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        resolved: ResolvedRunEnvironment,
    ) -> Path:
        manifest = workspace.environment / (
            f"{execution.name}-dmw-input-manifest.json"
        )
        command = [
            str(runtime.publication_python),
            "-m",
            "dmw_experiments.studies.haiu_comparison.preparation.dmw_storage",
            "--catalog",
            str(workspace.root / spec.input_catalog),
            "--output",
            str(manifest),
            "--source-branch",
            execution.source_branch,
            "--target-branch",
            execution.target_branch,
            "--raw-collection",
            execution.raw_collection,
            "--ontology-context-version",
            execution.ontology_context_version,
            *_env_file_arguments(resolved.env_files),
        ]
        self._run_checked(command, cwd=workspace.root)
        workspace.append_event(
            event="storage_prepared",
            detail="Created or verified isolated DMW storage.",
            target_branch=execution.target_branch,
            raw_collection=execution.raw_collection,
        )
        workspace.append_babysit(
            heading="Isolated storage prepared",
            bullets=(
                f"Database branch: `{execution.target_branch}`.",
                f"Raw collection: `{execution.raw_collection}`.",
                f"Annotation collection: `{execution.annotation_collection}`.",
                f"Ontology collection: `{execution.ontology_collection}`.",
            ),
        )
        return manifest

    def _capture_environment_lock(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        resolved: ResolvedRunEnvironment,
        dmw_input_manifest: Path,
    ) -> Path:
        from dmw_experiments.studies.haiu_comparison.operations.environment_lock import (
            _frozen_experiment_harness,
            _package_report,
            _sha256_file,
            validated_stack_packages,
        )

        package_report = _package_report(runtime.publication_python)
        stack_lock_path = workspace.root / "locks" / "stack-lock.json"
        stack_lock = json.loads(stack_lock_path.read_text(encoding="utf-8"))
        expected_versions = stack_lock.get("distributions")
        if not isinstance(expected_versions, dict):
            raise ValueError(
                "locks/stack-lock.json has no distributions table."
            )
        packages = validated_stack_packages(package_report, expected_versions)
        catalogue = load_header_sublemma_catalog(
            workspace.root / spec.input_catalog
        )
        import_manifest = load_dmw_pair_import_manifest(
            dmw_input_manifest,
            catalog=catalogue,
        )
        profile = provider_profile(execution.provider_profile)
        provider = {
            "profile": profile.manifest_entry(),
            "chat_endpoint_sha256": hashlib.sha256(
                resolved.config.haiu.base_url.encode("utf-8")
            ).hexdigest(),
            "embedding_endpoint_sha256": hashlib.sha256(
                (
                    resolved.config.haiu.embedding_base_url
                    or resolved.config.haiu.base_url
                ).encode("utf-8")
            ).hexdigest(),
        }
        payload = {
            "schema_version": 3,
            "study": spec.study,
            "run_id": spec.run_id,
            "execution": execution.name,
            "provider": provider,
            "runtime": {
                "python_version": package_report.get("python_version"),
                "packages": packages,
            },
            "stack_lock": {
                "stack_id": stack_lock.get("stack_id"),
                "sha256": _sha256_file(stack_lock_path),
            },
            "run_contract": {
                "run_toml_sha256": _sha256_file(workspace.run_spec),
                "run_env_sha256": _sha256_file(resolved.env_files[0]),
                "execution_env_sha256": _sha256_file(resolved.env_files[1]),
            },
            "configuration": resolved.provenance_payload(),
            "input_population": {
                "schema_version": 1,
                "unit_kind": "header_sublemma_pair",
                "file_sha256": catalogue.file_sha256,
                "catalogue_content_sha256": catalogue.content_sha256,
                "input_unit_count": len(catalogue.records),
                "dmw_import_manifest_file_sha256": import_manifest.file_sha256,
                "dmw_import_manifest_content_sha256": import_manifest.content_sha256,
            },
            "dmw_data_identity": {
                "branch": execution.target_branch,
                "raw": execution.raw_collection,
                "annotation": execution.annotation_collection,
                "ontology": execution.ontology_collection,
                "ontology_context_version": execution.ontology_context_version,
            },
            "experiment_harness": _frozen_experiment_harness(REPOSITORY_ROOT),
        }
        output = workspace.environment / (
            f"{execution.name}-environment-lock.json"
        )
        _write_json_immutable(output, payload)
        workspace.append_event(
            event="environment_locked",
            detail="Captured schema-v3 package, input, and AppRC provenance.",
        )
        workspace.append_babysit(
            heading="Environment lock captured",
            bullets=(
                "Verified the published DMW stack and copied input contract.",
                "Recorded redacted AppRC sources without credential values.",
            ),
        )
        return output

    def _start_services(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        resolved: ResolvedRunEnvironment,
        dmw_input_manifest: Path,
        environment_lock: Path,
        resume: bool,
    ) -> None:
        units = ServiceUnits.for_run(spec.run_id, execution.name)
        if any(
            self.services.is_active(unit) for unit in asdict(units).values()
        ):
            raise RuntimeError(
                "One or more services for this execution are active."
            )
        backend_log = workspace.logs / f"{execution.name}-backend.log"
        runner_log = workspace.logs / f"{execution.name}-runner.log"
        watchdog_log = workspace.logs / f"{execution.name}-watchdog.log"
        backend_command = self._backend_command(
            spec=spec,
            execution=execution,
            runtime=runtime,
            workspace=workspace,
            resolved=resolved,
        )
        self.services.start(
            unit=units.backend,
            command=backend_command,
            working_directory=workspace.root,
            log_file=backend_log,
            restart="no",
        )
        try:
            _wait_for_http(f"{BACKEND_URLS[execution.name]}/openapi.json")
            self.services.start(
                unit=units.runner,
                command=self._runner_command(
                    spec=spec,
                    execution=execution,
                    runtime=runtime,
                    workspace=workspace,
                    dmw_input_manifest=dmw_input_manifest,
                    environment_lock=environment_lock,
                    resume=resume,
                ),
                working_directory=workspace.root,
                log_file=runner_log,
                restart="on-failure",
                restart_seconds=30,
            )
            time.sleep(2)
            if not self.services.is_active(units.runner):
                raise RuntimeError("Runner exited before watchdog attachment.")
            self.services.start(
                unit=units.watchdog,
                command=[
                    str(runtime.publication_python),
                    "-m",
                    "dmw_experiments.shared.supervision.watch_runner_progress",
                    "--runner-unit",
                    units.runner,
                    "--result-dir",
                    str(workspace.root / execution.output_directory_name),
                    "--event-log",
                    str(workspace.babysit_log),
                    "--stall-seconds",
                    str(resolved.config.app.watchdog_stall_seconds),
                ],
                working_directory=workspace.root,
                log_file=watchdog_log,
                restart="no",
            )
        except BaseException:
            self.services.stop(units.watchdog)
            self.services.stop(units.runner)
            self.services.stop(units.backend)
            raise
        workspace.write_services(units)
        workspace.append_event(
            event="services_started",
            detail="Backend, runner, and watchdog are active.",
            resume=resume,
            **asdict(units),
        )
        workspace.append_babysit(
            heading="Services started",
            bullets=(
                f"Backend: `{units.backend}`.",
                f"Runner: `{units.runner}`.",
                f"Watchdog: `{units.watchdog}`.",
                f"Launch mode: {'identical resume' if resume else 'new run'}.",
            ),
        )

    def _backend_command(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        resolved: ResolvedRunEnvironment,
    ) -> list[str]:
        command = _execution_wrapper_command(
            runtime=runtime,
            workspace=workspace,
            execution=execution,
            component="backend",
        )
        command.extend(
            [
                "--raw-collection",
                execution.raw_collection,
                "--max-tokens",
                str(spec.max_output_tokens),
                *_env_file_arguments(
                    (
                        workspace.root / "run.env",
                        workspace.root / execution.env_file,
                    )
                ),
            ]
        )
        if execution.name == "lmstudio":
            command.extend(
                [
                    "--lmstudio-base-url",
                    resolved.config.haiu.base_url,
                    "--model",
                    "qwen/qwen3.6-27b",
                    "--lmstudio-model-id",
                    "qwen/qwen3.6-27b",
                ]
            )
        return command

    def _runner_command(
        self,
        *,
        spec: RunContract,
        execution: ProviderExecutionSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        dmw_input_manifest: Path,
        environment_lock: Path,
        resume: bool,
    ) -> list[str]:
        input_root = workspace.root / "INPUTS"
        command = _execution_wrapper_command(
            runtime=runtime,
            workspace=workspace,
            execution=execution,
            component="runner",
        )
        command.extend(
            [
                "--base-url",
                BACKEND_URLS[execution.name],
                "--timeout-seconds",
                "3600",
                "--input-catalog",
                str(workspace.root / spec.input_catalog),
                "--dmw-input-manifest",
                str(dmw_input_manifest),
                "--limit",
                str(spec.limit),
                "--missing-id-policy",
                "fail",
                "--conditions",
                *spec.conditions,
                "--output-dir",
                str(workspace.root / execution.output_directory_name),
                "--run-id",
                f"{spec.run_id}-{execution.name}",
                "--max-attempts",
                "3",
                "--retry-delay-seconds",
                "30",
                "--annotation-max-attempts",
                "3",
                *_env_file_arguments(
                    (
                        workspace.root / "run.env",
                        workspace.root / execution.env_file,
                    )
                ),
                "--publication-run",
                "--provider-profile",
                execution.provider_profile,
                "--max-output-tokens",
                str(spec.max_output_tokens),
                "--output-safety-margin-tokens",
                str(spec.output_safety_margin_tokens),
                "--ontology-example-limit",
                str(spec.ontology_example_limit),
                "--branch",
                execution.target_branch,
                "--ontology-context-version",
                execution.ontology_context_version,
                "--annotation-guideline-version",
                execution.ontology_context_version,
                "--storage",
                str(workspace.environment / f"haiu-{execution.name}"),
                "--ontology-user-input-file",
                str(input_root / "historian_ontology_user_input.md"),
                "--annotation-guidelines-file",
                str(input_root / "annotation_guidelines.md"),
                "--provenance-file",
                f"reference_ontology={input_root / 'reference_ontology.ttl'}",
                "--provenance-file",
                f"retrieval_workspace={input_root / 'retrieval_workspace.json'}",
                "--provenance-file",
                f"environment_lock={environment_lock}",
            ]
        )
        if resume:
            command.append("--resume")
        return command

    def _run_checked(self, command: list[str], *, cwd: Path) -> None:
        completed = self._command_runner(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Setup command failed: {detail}")


def _execution_wrapper_command(
    *,
    runtime: RuntimePaths,
    workspace: RunWorkspace,
    execution: ProviderExecutionSpec,
    component: str,
) -> list[str]:
    return [
        str(runtime.publication_python),
        "-m",
        "dmw_experiments.studies.haiu_comparison.entrypoints.run_execution",
        "--run-dir",
        str(workspace.root),
        "--execution",
        execution.name,
        component,
    ]


def _env_file_arguments(paths: Iterable[Path]) -> list[str]:
    return [item for path in paths for item in ("--env-file", str(path))]


def _wait_for_http(
    url: str,
    *,
    timeout_seconds: float = 180,
    poll_seconds: float = 2,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(poll_seconds)
    raise RuntimeError(f"Backend readiness timed out: {last_error}")


def _attempt_status(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid"
    if not isinstance(payload, dict):
        return "invalid"
    return str(payload.get("status") or "")


def _write_json_immutable(path: Path, payload: dict[str, Any]) -> None:
    content = (
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise ValueError(
                f"Immutable environment evidence differs: {path.name}."
            )
        return
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
