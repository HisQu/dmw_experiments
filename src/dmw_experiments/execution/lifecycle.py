"""Provide one safe lifecycle for the DMW--Haiu comparison study."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dmw_experiments.artifacts.run_workspace import RunWorkspace
from dmw_experiments.config import AppRuntimeConfig, UNSET_PATH
from dmw_experiments.execution.release_stack import ReleaseStackManager
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.operations.run_spec import (
    HeaderSublemmaRunSpec,
    load_header_sublemma_run_spec,
    validate_isolated_specs,
)
from dmw_experiments.studies.datamodel_workflow_haiu_comparison.paths import (
    INPUT_ROOT,
    REPOSITORY_ROOT,
    SPEC_ROOT,
    STUDY_ROOT,
)
from dmw_experiments.supervision.systemd_services import (
    ServiceUnits,
    UserServiceManager,
)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ACADEMICCLOUD_BACKEND_URL = "http://127.0.0.1:8000"
REFERENCE_ONTOLOGY = INPUT_ROOT / "reference_ontology.ttl"
RETRIEVAL_WORKSPACE = INPUT_ROOT / "retrieval_workspace.json"
ONTOLOGY_USER_INPUT = INPUT_ROOT / "historian_ontology_user_input.md"
ANNOTATION_GUIDELINES = INPUT_ROOT / "annotation_guidelines.md"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolve host-specific paths outside tracked scientific specifications.

    :param output_root: Parent of all generated runs and analyses.
    :param publication_python: Interpreter containing the locked DMW stack.
    :param provider_environment_file: Ignored AcademicCloud configuration file.
    """

    output_root: Path
    publication_python: Path
    provider_environment_file: Path

    @classmethod
    def from_config(cls, config: AppRuntimeConfig) -> RuntimePaths:
        """Apply repository-relative defaults to resolved AppRC settings.

        :param config: AppRC-owned runtime configuration.
        :return: Absolute runtime paths without recording them in run specs.
        :raises ValueError: If AcademicCloud has no ignored environment file.
        """
        output_root = config.storage_root.expanduser()
        if not output_root.is_absolute():
            output_root = REPOSITORY_ROOT / output_root
        publication_python = config.publication_python
        if publication_python == UNSET_PATH:
            publication_python = REPOSITORY_ROOT / ".venv" / "bin" / "python"
        else:
            publication_python = _repository_relative_path(publication_python)
        provider_environment_file = config.academiccloud_env_file
        if provider_environment_file == UNSET_PATH:
            raise ValueError(
                "Set DMW_EXPERIMENTS_ACADEMICCLOUD_ENV_FILE to an ignored "
                "dotenv file containing DATAMODEL_LOGIN and "
                "DATAMODEL_PASSWORD."
            )
        return cls(
            output_root=output_root.resolve(),
            # > Keep the virtual-environment executable path itself. Resolving
            # > its symlink would invoke the base interpreter without the
            # > locked environment when systemd starts a service.
            publication_python=publication_python.absolute(),
            provider_environment_file=(
                _repository_relative_path(provider_environment_file).resolve()
            ),
        )

    def validate(self) -> None:
        """Reject missing runtime components before external mutation.

        :return: ``None`` when the local machine can execute the frozen stack.
        :raises ValueError: If the interpreter, scientific inputs, or private
            configuration are unavailable.
        """
        if not self.publication_python.is_file():
            raise ValueError(
                "Published-stack interpreter does not exist: "
                f"{self.publication_python}"
            )
        if not self.provider_environment_file.is_file():
            raise ValueError(
                "AcademicCloud environment file does not exist: "
                f"{self.provider_environment_file}"
            )
        for input_file in (
            REFERENCE_ONTOLOGY,
            RETRIEVAL_WORKSPACE,
            ONTOLOGY_USER_INPUT,
            ANNOTATION_GUIDELINES,
        ):
            if not input_file.is_file():
                raise ValueError(
                    f"Required scientific input is missing: {input_file}"
                )


@dataclass(frozen=True, slots=True)
class RunStatus:
    """Summarize durable matrix progress and current service ownership.

    :param run_id: Stable run identity.
    :param expected_cells: Complete scheduled matrix size.
    :param terminal_cells: Cells with an authoritative raw record.
    :param successful_cells: Terminal rows reporting success.
    :param failed_cells: Terminal rows reporting a measured failure.
    :param retry_pending_cells: Raw rows still marked for an in-run retry.
    :param strict_analysis_ready: Whether every cell is terminal and stable.
    :param services: Current systemd active state by process role.
    """

    run_id: str
    expected_cells: int
    terminal_cells: int
    successful_cells: int
    failed_cells: int
    retry_pending_cells: int
    strict_analysis_ready: bool
    services: dict[str, str]


class ExperimentLifecycle:
    """Coordinate validation, storage, provenance, services, and resumptions."""

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
        spec_path: Path,
        *,
        expected_mode: str | None = None,
        allow_existing_run: bool = False,
    ) -> dict[str, Any]:
        """Validate one complete launch contract without mutating run state.

        :param spec_path: Tracked schema-v2 run specification.
        :param expected_mode: Optional command-specific ``smoke`` or ``full``.
        :param allow_existing_run: Permit the exact run directory for status or
            resume workflows.
        :return: Non-secret plan suitable for terminal or JSON display.
        """
        spec = self._load_spec(spec_path, expected_mode=expected_mode)
        runtime = RuntimePaths.from_config(self.config)
        runtime.validate()
        result_directory = spec.result_directory(runtime.output_root)
        if result_directory.exists() and not allow_existing_run:
            raise ValueError(
                "Run directory already exists. Use resume for an interrupted "
                f"run: {result_directory}"
            )
        return {
            "schema_version": spec.schema_version,
            "study": spec.study,
            "mode": spec.mode,
            "run_id": spec.run_id,
            "provider_profile": spec.provider_profile,
            "population_units": self._population_units(spec),
            "expected_cells": self._population_units(spec)
            * len(spec.conditions),
            "conditions": list(spec.conditions),
            "storage": {
                "branch": spec.target_branch,
                "raw_collection": spec.raw_collection,
                "annotation_collection": spec.annotation_collection,
                "ontology_collection": spec.ontology_collection,
            },
            "result_directory": str(result_directory),
            "service_units": asdict(ServiceUnits.for_run(spec.run_id)),
            "runtime": {
                "publication_python": str(runtime.publication_python),
                "provider_environment_file": str(
                    runtime.provider_environment_file
                ),
            },
        }

    def launch(self, spec_path: Path, *, expected_mode: str) -> RunWorkspace:
        """Prepare and start one fresh smoke or full provider run.

        Pre-service preparation is idempotent for an existing workspace that
        has not yet created a scientific run manifest. Once the runner has
        frozen that manifest, continuation belongs exclusively to
        :meth:`resume`.

        :param spec_path: Tracked schema-v2 run specification.
        :param expected_mode: Required ``smoke`` or ``full`` command mode.
        :return: Started run workspace.
        """
        spec = self._load_spec(spec_path, expected_mode=expected_mode)
        runtime = RuntimePaths.from_config(self.config)
        runtime.validate()
        self._require_no_other_provider_run()
        root = spec.result_directory(runtime.output_root)
        if root.exists():
            workspace = RunWorkspace.open(root, spec_path)
            if (root / "summaries" / "run_manifest.json").exists():
                raise ValueError(
                    "The runner already created its immutable manifest. Use "
                    "the resume command for this run."
                )
        else:
            workspace = RunWorkspace.create(root, spec_path)
        workspace.append_babysit(
            heading="Run contract",
            bullets=(
                f"Mode: {spec.mode}; provider: {spec.provider_profile}.",
                f"Population: {self._population_units(spec)} units and "
                f"{self._population_units(spec) * len(spec.conditions)} cells.",
                "Published stack: DMW 1.1.3, OPA 2.1.2, GTA 0.2.4, "
                "and Haiu 1.8.0.",
                "Terminal context, length, and model failures remain evidence; "
                "no recovery-amendment flags are used.",
            ),
        )
        try:
            manifest = self._prepare_storage(
                spec=spec,
                runtime=runtime,
                workspace=workspace,
            )
            environment_lock = self._capture_environment_lock(
                spec=spec,
                runtime=runtime,
                workspace=workspace,
                dmw_input_manifest=manifest,
            )
            self._start_services(
                spec=spec,
                runtime=runtime,
                workspace=workspace,
                dmw_input_manifest=manifest,
                environment_lock=environment_lock,
                resume=False,
            )
        except BaseException as error:
            workspace.append_event(
                event="launch_failed",
                detail=str(error),
                error_type=type(error).__name__,
            )
            workspace.append_babysit(
                heading="Launch failed",
                bullets=(
                    f"Stopped before a confirmed complete launch: {error}",
                    "The workspace and any durable preparation evidence were "
                    "preserved for diagnosis.",
                ),
            )
            raise
        return workspace

    def resume(self, spec_path: Path) -> RunWorkspace:
        """Restart only an interrupted run with its exact frozen settings.

        :param spec_path: Original tracked run specification.
        :return: Restarted run workspace.
        :raises ValueError: If required immutable artifacts are unavailable.
        """
        spec = self._load_spec(spec_path)
        runtime = RuntimePaths.from_config(self.config)
        runtime.validate()
        root = spec.result_directory(runtime.output_root)
        workspace = RunWorkspace.open(root, spec_path)
        manifest = workspace.provenance / "dmw_input_manifest.json"
        environment_lock = workspace.provenance / "environment_lock.json"
        runner_manifest = root / "summaries" / "run_manifest.json"
        for required in (manifest, environment_lock, runner_manifest):
            if not required.is_file():
                raise ValueError(
                    f"Cannot resume without immutable artifact: {required.name}"
                )
        self._require_no_other_provider_run(
            allowed=ServiceUnits.for_run(spec.run_id)
        )
        self._start_services(
            spec=spec,
            runtime=runtime,
            workspace=workspace,
            dmw_input_manifest=manifest,
            environment_lock=environment_lock,
            resume=True,
        )
        return workspace

    def pause(self, spec_path: Path) -> RunStatus:
        """Stop supervision, runner, and backend in checkpoint-safe order.

        :param spec_path: Original tracked run specification.
        :return: Durable progress after all owned services stop.
        """
        spec = self._load_spec(spec_path)
        runtime = RuntimePaths.from_config(self.config)
        workspace = RunWorkspace.open(
            spec.result_directory(runtime.output_root), spec_path
        )
        units = ServiceUnits.for_run(spec.run_id)
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
            event="run_paused",
            detail="Stopped watchdog, runner, and backend in safe order.",
        )
        workspace.append_babysit(
            heading="Run paused",
            bullets=(
                "Stopped the watchdog before interrupting the runner.",
                "Preserved every raw result, attempt checkpoint, manifest, "
                "and storage identity for an identical resume.",
            ),
        )
        return self.status(spec_path)

    def status(self, spec_path: Path) -> RunStatus:
        """Count authoritative cells and inspect the run's service units.

        :param spec_path: Original tracked run specification.
        :return: Current durable and process state.
        """
        spec = self._load_spec(spec_path)
        runtime = RuntimePaths.from_config(self.config)
        workspace = RunWorkspace.open(
            spec.result_directory(runtime.output_root), spec_path
        )
        raw_paths = tuple(sorted((workspace.root / "raw").glob("*/*.json")))
        successes = 0
        failures = 0
        for raw_path in raw_paths:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and bool(payload.get("success")):
                successes += 1
            else:
                failures += 1
        retry_pending = sum(
            1
            for path in (workspace.root / "attempts").glob("*/*.json")
            if _attempt_status(path) == "retry_pending"
        )
        expected = self._population_units(spec) * len(spec.conditions)
        units = ServiceUnits.for_run(spec.run_id)
        services = {
            role: self.services.active_state(unit)
            for role, unit in asdict(units).items()
        }
        return RunStatus(
            run_id=spec.run_id,
            expected_cells=expected,
            terminal_cells=len(raw_paths),
            successful_cells=successes,
            failed_cells=failures,
            retry_pending_cells=retry_pending,
            strict_analysis_ready=(
                len(raw_paths) == expected and retry_pending == 0
            ),
            services=services,
        )

    def _load_spec(
        self,
        spec_path: Path,
        *,
        expected_mode: str | None = None,
    ) -> HeaderSublemmaRunSpec:
        """Load one spec and enforce the study-wide isolation pair.

        :param spec_path: Candidate JSON contract.
        :param expected_mode: Optional command-specific mode.
        :return: Validated immutable specification.
        """
        spec_path = spec_path.expanduser().resolve()
        spec = load_header_sublemma_run_spec(spec_path)
        spec.validate(STUDY_ROOT)
        if expected_mode is not None and spec.mode != expected_mode:
            raise ValueError(
                f"This command requires a {expected_mode!r} run spec."
            )
        smoke = load_header_sublemma_run_spec(
            SPEC_ROOT / "academiccloud-header-sublemma-smoke.json"
        )
        full = load_header_sublemma_run_spec(
            SPEC_ROOT / "academiccloud-header-sublemma-full.json"
        )
        smoke.validate(STUDY_ROOT)
        full.validate(STUDY_ROOT)
        validate_isolated_specs(smoke, full)
        if spec.mode == "smoke":
            validate_isolated_specs(spec, full)
        else:
            validate_isolated_specs(smoke, spec)
        return spec

    def _population_units(self, spec: HeaderSublemmaRunSpec) -> int:
        """Return the scheduled population after applying smoke selection.

        :param spec: Validated run contract.
        :return: One for smoke mode or the complete catalogue count.
        """
        if spec.limit == 1:
            return 1
        payload = json.loads((STUDY_ROOT / spec.input_catalog).read_text())
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError("Header--sublemma input catalogue has no records.")
        return len(records)

    def _require_no_other_provider_run(
        self,
        *,
        allowed: ServiceUnits | None = None,
    ) -> None:
        """Reject a launch while another AcademicCloud experiment is active.

        :param allowed: Own unit names permitted during an exact resume.
        :return: ``None`` when provider ownership is unambiguous.
        """
        allowed_names = set(asdict(allowed).values()) if allowed else set()
        active = tuple(
            unit
            for unit in self.services.active_academiccloud_units()
            if unit not in allowed_names
        )
        if active:
            raise RuntimeError(
                "Another AcademicCloud experiment is active: "
                + ", ".join(active)
            )

    def _prepare_storage(
        self,
        *,
        spec: HeaderSublemmaRunSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
    ) -> Path:
        """Create or verify the run's isolated DMW database identities.

        :param spec: Validated run contract.
        :param runtime: Resolved local runtime paths.
        :param workspace: Durable destination for the import manifest.
        :return: Immutable DMW import manifest path.
        """
        manifest = workspace.provenance / "dmw_input_manifest.json"
        command = [
            str(runtime.publication_python),
            "-m",
            "dmw_experiments.studies.datamodel_workflow_haiu_comparison.prepare_header_sublemma_environment",
            "--catalog",
            str(STUDY_ROOT / spec.input_catalog),
            "--output",
            str(manifest),
            "--source-branch",
            spec.source_branch,
            "--target-branch",
            spec.target_branch,
            "--raw-collection",
            spec.raw_collection,
            "--ontology-context-version",
            spec.ontology_context_version,
            "--env-file",
            str(runtime.provider_environment_file),
        ]
        self._run_checked(command, cwd=REPOSITORY_ROOT)
        workspace.append_event(
            event="storage_prepared",
            detail="Created or verified isolated DMW storage.",
            target_branch=spec.target_branch,
            raw_collection=spec.raw_collection,
        )
        workspace.append_babysit(
            heading="Isolated storage prepared",
            bullets=(
                f"Database branch: `{spec.target_branch}`.",
                f"Raw collection: `{spec.raw_collection}`.",
                f"Annotation collection: `{spec.annotation_collection}`.",
                f"Ontology collection: `{spec.ontology_collection}`.",
            ),
        )
        return manifest

    def _capture_environment_lock(
        self,
        *,
        spec: HeaderSublemmaRunSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        dmw_input_manifest: Path,
    ) -> Path:
        """Capture schema-v2 evidence from release tags and live config.

        :param spec: Validated run contract.
        :param runtime: Resolved local runtime paths.
        :param workspace: Durable provenance destination.
        :param dmw_input_manifest: Verified storage-import evidence.
        :return: Captured environment-lock path.
        """
        from haiu import HaiuRC
        from haiu.config import HAIU_CONFIG

        from dmw_experiments.studies.datamodel_workflow_haiu_comparison.capture_environment_lock import (
            main as capture_main,
        )
        from dmw_experiments.studies.datamodel_workflow_haiu_comparison.run_experiment import (
            _configure_provider_profile,
            _load_runtime_environment,
        )

        releases = ReleaseStackManager(output_root=runtime.output_root).ensure()
        _load_runtime_environment(
            provider_environment_files=(runtime.provider_environment_file,),
        )
        HAIU_CONFIG.bootstrap(
            env_files=(runtime.provider_environment_file,),
            env_file_overrides_os_environ=False,
            load_dotenv_layers=True,
        )
        haiu_config = HaiuRC()
        from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.provider_profiles import (
            provider_profile,
        )

        _configure_provider_profile(
            rc=haiu_config,
            profile=provider_profile(spec.provider_profile),
        )
        output = workspace.provenance / "environment_lock.json"
        result = capture_main(
            [
                "--output",
                str(output),
                "--provider-profile",
                spec.provider_profile,
                "--dmw-ontology-branch",
                spec.target_branch,
                "--dmw-ontology-collection",
                spec.ontology_collection,
                "--dmw-raw-collection",
                spec.raw_collection,
                "--dmw-annotation-collection",
                spec.annotation_collection,
                "--ontology-context-version",
                spec.ontology_context_version,
                "--input-catalog",
                str(STUDY_ROOT / spec.input_catalog),
                "--dmw-input-manifest",
                str(dmw_input_manifest),
                "--chat-endpoint",
                haiu_config.client.base_url,
                "--embedding-endpoint",
                str(
                    haiu_config.client.embedding_base_url
                    or haiu_config.client.base_url
                ),
                "--provider-environment-file",
                str(runtime.provider_environment_file),
                "--dmw-repo",
                str(releases.datamodel_workflow),
                "--opa-repo",
                str(releases.opa),
                "--gta-repo",
                str(releases.gta),
                "--haiu-repo",
                str(releases.haiu),
                "--experiment-repo",
                str(REPOSITORY_ROOT),
                "--dmw-python",
                str(runtime.publication_python),
            ]
        )
        if result:
            raise RuntimeError(
                f"Environment-lock capture exited with status {result}."
            )
        workspace.append_event(
            event="environment_locked",
            detail="Captured schema-v2 published-stack and input evidence.",
        )
        workspace.append_babysit(
            heading="Environment lock captured",
            bullets=(
                "Verified the published DMW 1.1.3 / OPA 2.1.2 / GTA 0.2.4 "
                "/ Haiu 1.8.0 runtime and clean release sources.",
                "Recorded endpoint and provider-file hashes without retaining "
                "credentials or local paths.",
            ),
        )
        return output

    def _start_services(
        self,
        *,
        spec: HeaderSublemmaRunSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        dmw_input_manifest: Path,
        environment_lock: Path,
        resume: bool,
    ) -> None:
        """Start the backend, resumable runner, and unit-aware watchdog.

        :param spec: Validated run contract.
        :param runtime: Resolved local runtime paths.
        :param workspace: Run-local logs and observations.
        :param dmw_input_manifest: Frozen storage evidence.
        :param environment_lock: Frozen runtime evidence.
        :param resume: Whether to append the runner's exact resume flag.
        :return: ``None`` after all three units are active.
        """
        units = ServiceUnits.for_run(spec.run_id)
        if any(
            self.services.is_active(unit) for unit in asdict(units).values()
        ):
            raise RuntimeError(
                "One or more services for this run are already active."
            )
        backend_log = workspace.logs / "backend.log"
        runner_log = workspace.logs / "runner.log"
        watchdog_log = workspace.logs / "watchdog.log"
        self.services.start(
            unit=units.backend,
            command=[
                str(runtime.publication_python),
                "-m",
                "dmw_experiments.studies.datamodel_workflow_haiu_comparison.run_academiccloud_backend",
                "--raw-collection",
                spec.raw_collection,
                "--max-tokens",
                str(spec.max_output_tokens),
                "--env-file",
                str(runtime.provider_environment_file),
            ],
            working_directory=REPOSITORY_ROOT,
            log_file=backend_log,
            restart="no",
        )
        try:
            _wait_for_http(f"{ACADEMICCLOUD_BACKEND_URL}/openapi.json")
            runner_command = self._runner_command(
                spec=spec,
                runtime=runtime,
                workspace=workspace,
                dmw_input_manifest=dmw_input_manifest,
                environment_lock=environment_lock,
                resume=resume,
            )
            self.services.start(
                unit=units.runner,
                command=runner_command,
                working_directory=REPOSITORY_ROOT,
                log_file=runner_log,
                restart="on-failure",
                restart_seconds=30,
            )
            time.sleep(2)
            if not self.services.is_active(units.runner):
                raise RuntimeError(
                    "Runner exited before the watchdog could attach. Inspect "
                    f"{runner_log}."
                )
            self.services.start(
                unit=units.watchdog,
                command=[
                    str(runtime.publication_python),
                    "-m",
                    "dmw_experiments.supervision.watch_runner_progress",
                    "--runner-unit",
                    units.runner,
                    "--result-dir",
                    str(workspace.root),
                    "--event-log",
                    str(workspace.babysit_log),
                    "--stall-seconds",
                    str(self.config.watchdog_stall_seconds),
                ],
                working_directory=REPOSITORY_ROOT,
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

    def _runner_command(
        self,
        *,
        spec: HeaderSublemmaRunSpec,
        runtime: RuntimePaths,
        workspace: RunWorkspace,
        dmw_input_manifest: Path,
        environment_lock: Path,
        resume: bool,
    ) -> list[str]:
        """Build the exact publication-run argv without credential values.

        :param spec: Validated run contract.
        :param runtime: Resolved local runtime paths.
        :param workspace: Run output and logs.
        :param dmw_input_manifest: Frozen storage evidence.
        :param environment_lock: Frozen runtime evidence.
        :param resume: Whether the runner must reconcile existing checkpoints.
        :return: Argument vector safe to retain in systemd metadata.
        """
        command = [
            str(runtime.publication_python),
            "-m",
            "dmw_experiments.studies.datamodel_workflow_haiu_comparison.run_experiment",
            "--base-url",
            ACADEMICCLOUD_BACKEND_URL,
            "--timeout-seconds",
            "3600",
            "--input-catalog",
            str(STUDY_ROOT / spec.input_catalog),
            "--dmw-input-manifest",
            str(dmw_input_manifest),
            "--limit",
            str(spec.limit),
            "--missing-id-policy",
            "fail",
            "--conditions",
            *spec.conditions,
            "--output-dir",
            str(workspace.root),
            "--run-id",
            spec.run_id,
            "--max-attempts",
            "3",
            "--retry-delay-seconds",
            "30",
            "--annotation-max-attempts",
            "3",
            "--env-file",
            str(runtime.provider_environment_file),
            "--publication-run",
            "--provider-profile",
            spec.provider_profile,
            "--max-output-tokens",
            str(spec.max_output_tokens),
            "--output-safety-margin-tokens",
            str(spec.output_safety_margin_tokens),
            "--ontology-example-limit",
            str(spec.ontology_example_limit),
            "--branch",
            spec.target_branch,
            "--ontology-context-version",
            spec.ontology_context_version,
            "--annotation-guideline-version",
            spec.ontology_context_version,
            "--ontology-user-input-file",
            str(ONTOLOGY_USER_INPUT),
            "--annotation-guidelines-file",
            str(ANNOTATION_GUIDELINES),
            "--provenance-file",
            f"reference_ontology={REFERENCE_ONTOLOGY}",
            "--provenance-file",
            f"retrieval_workspace={RETRIEVAL_WORKSPACE}",
            "--provenance-file",
            f"environment_lock={environment_lock}",
        ]
        if resume:
            command.append("--resume")
        return command

    def _run_checked(self, command: list[str], *, cwd: Path) -> None:
        """Run one bounded setup command and surface concise diagnostics.

        :param command: Executable and arguments without secrets.
        :param cwd: Process working directory.
        :return: ``None`` on success.
        """
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


def _wait_for_http(
    url: str,
    *,
    timeout_seconds: float = 180,
    poll_seconds: float = 2,
) -> None:
    """Wait for a local backend through a bounded readiness window.

    :param url: Non-secret local health endpoint.
    :param timeout_seconds: Maximum startup allowance.
    :param poll_seconds: Delay between connection attempts.
    :return: ``None`` after any successful HTTP response.
    :raises RuntimeError: If the backend never becomes reachable.
    """
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
    """Read one attempt-state category without weakening malformed evidence.

    :param path: Attempt-state JSON file.
    :return: Stored status string, or ``invalid`` for a malformed document.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid"
    if not isinstance(payload, dict):
        return "invalid"
    return str(payload.get("status") or "")


def _repository_relative_path(path: Path) -> Path:
    """Anchor one configured host path at the experiment checkout.

    :param path: Absolute or repository-relative configuration value.
    :return: Expanded path with a deterministic repository anchor.
    """
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else REPOSITORY_ROOT / expanded
