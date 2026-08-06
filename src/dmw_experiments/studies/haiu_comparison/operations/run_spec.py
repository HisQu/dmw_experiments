"""Typed run-directory contracts for the Haiu comparison study."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STORAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BRANCH_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
EXECUTION_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

STUDY_ID = "haiu_comparison"
RELEASE_STACK = "published-dmw-1.1.3"
RUN_SPEC_FILENAME = "run.toml"
CONDITIONS = (
    "workflow_full_ontology",
    "workflow_rag",
    "haiu_rag_ontologizer",
)
PROVIDER_PROFILES = frozenset({"academiccloud-qwen36", "lmstudio-qwen36-q6"})
EXECUTION_PROVIDER_PROFILES = {
    "academiccloud": "academiccloud-qwen36",
    "lmstudio": "lmstudio-qwen36-q6",
}


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Describe one independently supervised provider execution.

    :param name: Stable execution slug used in directory and service names.
    :param enabled: Whether lifecycle actions include this execution.
    :param provider_profile: Pinned provider profile used by the runner.
    :param env_file: Run-relative provider override dotenv file.
    :param source_branch: Existing DMW branch containing source ontologies.
    :param target_branch: Fresh DMW branch for this execution.
    :param raw_collection: Fresh MongoDB raw collection for this execution.
    :param ontology_context_version: Frozen ontology-context version.
    """

    name: str
    enabled: bool
    provider_profile: str
    env_file: Path
    source_branch: str
    target_branch: str
    raw_collection: str
    ontology_context_version: str

    @property
    def annotation_collection(self) -> str:
        """Return the branch-scoped DMW annotation collection.

        :return: Physical collection identity selected by DMW.
        """
        return f"annotations__{self.target_branch}"

    @property
    def ontology_collection(self) -> str:
        """Return the branch-scoped DMW ontology collection.

        :return: Physical collection identity selected by DMW.
        """
        return f"ontologies__{self.target_branch}"

    @property
    def output_directory_name(self) -> str:
        """Return the required top-level raw execution directory.

        :return: Run-relative directory basename.
        """
        return f"raw-{self.name}"

    def validate(self, run_root: Path) -> None:
        """Reject unsafe or incomplete execution settings.

        :param run_root: Copied run directory used for relative paths.
        :return: ``None`` when the execution is safe to use.
        :raises ValueError: If an identity, provider, or path is invalid.
        """
        if not EXECUTION_NAME.fullmatch(self.name):
            raise ValueError(f"Invalid execution name: {self.name!r}.")
        expected_profile = EXECUTION_PROVIDER_PROFILES.get(self.name)
        if expected_profile is None:
            raise ValueError(f"Unsupported execution: {self.name!r}.")
        if self.provider_profile not in PROVIDER_PROFILES:
            raise ValueError(
                f"Unsupported provider profile: {self.provider_profile!r}."
            )
        if self.provider_profile != expected_profile:
            raise ValueError(
                f"Execution {self.name!r} requires provider profile "
                f"{expected_profile!r}."
            )
        if self.env_file.is_absolute() or ".." in self.env_file.parts:
            raise ValueError(
                f"Execution {self.name!r} env_file must be run-relative."
            )
        if not (run_root / self.env_file).is_file():
            raise ValueError(
                f"Execution env file does not exist: {self.env_file}."
            )
        if not BRANCH_NAME.fullmatch(self.source_branch):
            raise ValueError("source_branch is not a safe DMW branch identity.")
        if not BRANCH_NAME.fullmatch(self.target_branch):
            raise ValueError("target_branch is not a safe DMW branch identity.")
        if self.source_branch == self.target_branch:
            raise ValueError("source_branch and target_branch must differ.")
        if not STORAGE_NAME.fullmatch(self.raw_collection):
            raise ValueError("raw_collection is not a safe MongoDB identity.")
        output = run_root / self.output_directory_name
        if not output.is_dir():
            raise ValueError(
                f"Execution output directory does not exist: {output.name}."
            )
        for condition in CONDITIONS:
            for prefix in ("intermediates", "result"):
                directory = output / f"{prefix}-{condition}"
                if not directory.is_dir():
                    raise ValueError(
                        "Run template is missing condition directory: "
                        f"{directory.relative_to(run_root)}."
                    )


@dataclass(frozen=True, slots=True)
class HeaderSublemmaRunSpec:
    """Describe one copied smoke or full multi-provider run.

    :param schema_version: Supported TOML contract version.
    :param study: Study package that owns the run.
    :param mode: ``smoke`` or ``full``.
    :param release_stack: Published dependency-stack identity.
    :param run_id: Portable run-directory identity.
    :param input_catalog: Run-relative input catalogue.
    :param limit: One unit for smoke or zero for the full catalogue.
    :param conditions: Exact measured condition order.
    :param max_output_tokens: Configured cap before predictive sizing.
    :param output_safety_margin_tokens: Context reservation for generation.
    :param ontology_example_limit: Number of ontology examples sent to DMW.
    :param executions: Provider executions declared in this run.
    """

    schema_version: int
    study: str
    mode: str
    release_stack: str
    run_id: str
    input_catalog: Path
    limit: int
    conditions: tuple[str, ...]
    max_output_tokens: int
    output_safety_margin_tokens: int
    ontology_example_limit: int
    executions: tuple[ExecutionSpec, ...]

    @property
    def enabled_executions(self) -> tuple[ExecutionSpec, ...]:
        """Return enabled executions in TOML declaration order.

        :return: Non-empty tuple of enabled provider executions.
        """
        return tuple(
            execution for execution in self.executions if execution.enabled
        )

    def execution(self, name: str) -> ExecutionSpec:
        """Return one declared execution by name.

        :param name: Stable execution slug.
        :return: Matching execution specification.
        :raises ValueError: If the run does not declare ``name``.
        """
        for execution in self.executions:
            if execution.name == name:
                return execution
        raise ValueError(f"Run does not declare execution {name!r}.")

    def validate(self, run_root: Path) -> None:
        """Validate the complete copied run without changing it.

        :param run_root: Directory containing this contract and its data.
        :return: ``None`` when the run is internally consistent.
        :raises ValueError: If the contract or directory layout is invalid.
        """
        if self.schema_version != 3:
            raise ValueError("Unsupported run.toml schema version.")
        if self.study != STUDY_ID:
            raise ValueError(f"study must be {STUDY_ID!r}.")
        if self.mode not in {"smoke", "full"}:
            raise ValueError("mode must be 'smoke' or 'full'.")
        if self.release_stack != RELEASE_STACK:
            raise ValueError(f"release_stack must be {RELEASE_STACK!r}.")
        if not RUN_NAME.fullmatch(self.run_id):
            raise ValueError(
                "run_id must use lowercase letters, digits, and hyphens."
            )
        if run_root.name != self.run_id:
            raise ValueError(
                f"Run directory {run_root.name!r} must match run_id "
                f"{self.run_id!r}."
            )
        expected_limit = 1 if self.mode == "smoke" else 0
        if self.limit != expected_limit:
            raise ValueError(
                f"{self.mode} mode requires limit={expected_limit}."
            )
        if self.conditions != CONDITIONS:
            raise ValueError(
                "conditions must contain the three publication conditions "
                "once in canonical order."
            )
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive.")
        if self.output_safety_margin_tokens < 0:
            raise ValueError("output_safety_margin_tokens cannot be negative.")
        if self.ontology_example_limit < 0:
            raise ValueError("ontology_example_limit cannot be negative.")
        if self.input_catalog.is_absolute() or ".." in self.input_catalog.parts:
            raise ValueError("input_catalog must be run-relative.")
        if not (run_root / self.input_catalog).is_file():
            raise ValueError(
                f"input_catalog does not exist: {self.input_catalog}."
            )
        if not self.executions:
            raise ValueError("run.toml must declare at least one execution.")
        names = [execution.name for execution in self.executions]
        if len(names) != len(set(names)):
            raise ValueError("run.toml contains duplicate execution names.")
        if not self.enabled_executions:
            raise ValueError("run.toml must enable at least one execution.")
        for execution in self.executions:
            execution.validate(run_root)
        _validate_execution_storage_isolation(self.executions)
        for directory in (
            "INPUTS",
            "locks",
            "environment",
            "analysis/intermediate",
            "analysis/diagnostics",
            "analysis/workbooks",
            "plots",
            "logs",
        ):
            if not (run_root / directory).is_dir():
                raise ValueError(
                    f"Run template is missing directory: {directory}."
                )
        if not (run_root / "run.env").is_file():
            raise ValueError("Run template is missing run.env.")


def load_header_sublemma_run_spec(path: Path) -> HeaderSublemmaRunSpec:
    """Load one strict TOML run contract.

    :param path: ``run.toml`` path inside a copied run directory.
    :return: Parsed immutable run specification.
    :raises ValueError: If the TOML shape is unsupported.
    """
    try:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Cannot read run.toml: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("run.toml must contain a TOML table.")
    expected_keys = {
        "schema_version",
        "study",
        "mode",
        "release_stack",
        "run_id",
        "input_catalog",
        "limit",
        "conditions",
        "max_output_tokens",
        "output_safety_margin_tokens",
        "ontology_example_limit",
        "executions",
    }
    if set(payload) != expected_keys:
        raise ValueError(
            "run.toml top-level keys must match the schema exactly."
        )
    conditions = _string_list(payload, "conditions")
    executions_payload = payload["executions"]
    if not isinstance(executions_payload, dict):
        raise ValueError("run.toml executions must be a table.")
    executions = tuple(
        _execution_from_payload(name, value)
        for name, value in executions_payload.items()
    )
    try:
        return HeaderSublemmaRunSpec(
            schema_version=int(payload["schema_version"]),
            study=str(payload["study"]),
            mode=str(payload["mode"]),
            release_stack=str(payload["release_stack"]),
            run_id=str(payload["run_id"]),
            input_catalog=Path(str(payload["input_catalog"])),
            limit=int(payload["limit"]),
            conditions=tuple(conditions),
            max_output_tokens=int(payload["max_output_tokens"]),
            output_safety_margin_tokens=int(
                payload["output_safety_margin_tokens"]
            ),
            ontology_example_limit=int(payload["ontology_example_limit"]),
            executions=executions,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "run.toml contains an invalid scalar value."
        ) from error


def load_run_spec(run_root: Path) -> HeaderSublemmaRunSpec:
    """Load and validate the contract belonging to ``run_root``.

    :param run_root: Complete copied run directory.
    :return: Validated immutable run specification.
    """
    resolved = run_root.expanduser().resolve()
    spec = load_header_sublemma_run_spec(resolved / RUN_SPEC_FILENAME)
    spec.validate(resolved)
    return spec


def _execution_from_payload(name: str, payload: Any) -> ExecutionSpec:
    """Parse one exact ``executions.<name>`` table.

    :param name: Execution table key.
    :param payload: Decoded TOML table.
    :return: Typed execution settings.
    :raises ValueError: If keys or scalar values are invalid.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"executions.{name} must be a table.")
    expected = {
        "enabled",
        "provider_profile",
        "env_file",
        "source_branch",
        "target_branch",
        "raw_collection",
        "ontology_context_version",
    }
    if set(payload) != expected:
        raise ValueError(
            f"executions.{name} keys must match the schema exactly."
        )
    try:
        enabled = payload["enabled"]
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be boolean")
        return ExecutionSpec(
            name=name,
            enabled=enabled,
            provider_profile=str(payload["provider_profile"]),
            env_file=Path(str(payload["env_file"])),
            source_branch=str(payload["source_branch"]),
            target_branch=str(payload["target_branch"]),
            raw_collection=str(payload["raw_collection"]),
            ontology_context_version=str(payload["ontology_context_version"]),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"executions.{name} contains invalid values."
        ) from error


def _string_list(payload: dict[str, Any], key: str) -> list[str]:
    """Read one TOML string list without coercing invalid values.

    :param payload: Decoded TOML document.
    :param key: Required list key.
    :return: Validated list of strings.
    """
    value = payload[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"run.toml {key} must be a list of strings.")
    return value


def _validate_execution_storage_isolation(
    executions: tuple[ExecutionSpec, ...],
) -> None:
    """Ensure no provider execution reuses writable DMW identities.

    :param executions: All declared execution contracts.
    :return: ``None`` when every writable identity is unique.
    :raises ValueError: If two executions share any writable identity.
    """
    for attribute in (
        "target_branch",
        "raw_collection",
        "annotation_collection",
        "ontology_collection",
    ):
        values = [
            str(getattr(execution, attribute)) for execution in executions
        ]
        if len(values) != len(set(values)):
            raise ValueError(
                f"Provider executions reuse writable identity: {attribute}."
            )
