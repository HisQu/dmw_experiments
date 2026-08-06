"""Immutable, non-secret specifications for header--sublemma provider runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STORAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BRANCH_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
STUDY_ID = "haiu_comparison"
RELEASE_STACK = "published-dmw-1.1.3"
CONDITIONS = frozenset(
    {
        "workflow_full_ontology",
        "workflow_rag",
        "haiu_rag_ontologizer",
    }
)
PROVIDERS = frozenset({"academiccloud-qwen36", "lmstudio-qwen36-q6"})


@dataclass(frozen=True, slots=True)
class HeaderSublemmaRunSpec:
    """Describe one isolated header--sublemma smoke or full provider run.

    The specification deliberately excludes credentials, absolute local paths,
    and mutable service unit names. It is the reviewable source for storage
    identities and runner settings before any DMW process starts.

    :param schema_version: Version of this JSON specification format.
    :param study: Stable study identifier that owns this run.
    :param mode: Whether this is a disposable smoke or the complete run.
    :param release_stack: Published dependency-stack contract to validate.
    :param run_id: Result-directory identity for this run.
    :param provider_profile: Pinned provider profile accepted by the runner.
    :param source_branch: Existing DMW branch that owns frozen ontology assets.
    :param target_branch: New isolated DMW database-branch identity.
    :param raw_collection: New isolated DMW raw collection identity.
    :param ontology_context_version: Frozen ontology context used by DMW.
    :param input_catalog: Catalogue path relative to the experiment root.
    :param limit: ``1`` for a disposable smoke or ``0`` for all catalogue rows.
    :param conditions: Exact condition set, in the intended execution order.
    :param max_output_tokens: Configured generation cap before predictive sizing.
    :param output_safety_margin_tokens: Context reservation used by the runner.
    :param ontology_example_limit: Number of ontology examples supplied to DMW.
    """

    schema_version: int
    study: str
    mode: str
    release_stack: str
    run_id: str
    provider_profile: str
    source_branch: str
    target_branch: str
    raw_collection: str
    ontology_context_version: str
    input_catalog: Path
    limit: int
    conditions: tuple[str, ...]
    max_output_tokens: int
    output_safety_margin_tokens: int
    ontology_example_limit: int

    @property
    def annotation_collection(self) -> str:
        """Return the DMW annotation collection derived from the branch.

        :return: Physical collection identity selected by DMW branch scoping.
        """
        return f"annotations__{self.target_branch}"

    @property
    def ontology_collection(self) -> str:
        """Return the DMW ontology collection derived from the branch.

        :return: Physical collection identity selected by DMW branch scoping.
        """
        return f"ontologies__{self.target_branch}"

    def result_directory(self, output_root: Path) -> Path:
        """Resolve this run below the configured storage root.

        :param output_root: Active AppRC storage root.
        :return: Deterministic result directory for the run identity.
        """
        return output_root / "runs" / self.run_id

    def validate(self, study_root: Path) -> None:
        """Reject unsafe, incomplete, or internally inconsistent run settings.

        :param study_root: Tracked directory against which inputs resolve.
        :raises ValueError: If a setting could select incorrect storage or deviate
            from the three-condition publication design.
        """
        if self.schema_version != 2:
            raise ValueError("Unsupported header--sublemma run-spec version.")
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
        if self.provider_profile not in PROVIDERS:
            raise ValueError(
                "provider_profile is not a supported pinned profile."
            )
        if not BRANCH_NAME.fullmatch(self.source_branch):
            raise ValueError("source_branch is not a safe DMW branch identity.")
        if not BRANCH_NAME.fullmatch(self.target_branch):
            raise ValueError("target_branch is not a safe DMW branch identity.")
        if self.source_branch == self.target_branch:
            raise ValueError(
                "source_branch and target_branch must be different."
            )
        if not STORAGE_NAME.fullmatch(self.raw_collection):
            raise ValueError(
                "raw_collection is not a safe MongoDB collection identity."
            )
        if self.limit not in {0, 1}:
            raise ValueError(
                "limit must be 1 for smoke or 0 for the full catalogue."
            )
        expected_limit = 1 if self.mode == "smoke" else 0
        if self.limit != expected_limit:
            raise ValueError(
                f"{self.mode} mode requires limit={expected_limit}."
            )
        if set(self.conditions) != CONDITIONS or len(self.conditions) != 3:
            raise ValueError(
                "conditions must contain each publication condition once."
            )
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive.")
        if self.output_safety_margin_tokens < 0:
            raise ValueError("output_safety_margin_tokens cannot be negative.")
        if self.ontology_example_limit < 0:
            raise ValueError("ontology_example_limit cannot be negative.")
        catalog = study_root / self.input_catalog
        if not catalog.is_file():
            raise ValueError(
                f"input_catalog does not exist: {self.input_catalog}."
            )


def load_header_sublemma_run_spec(path: Path) -> HeaderSublemmaRunSpec:
    """Load and validate one non-secret header--sublemma run specification.

    :param path: JSON file containing schema-version-2 run settings.
    :return: Parsed immutable run specification.
    :raises ValueError: If the JSON shape is not the supported specification.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Run specification must be a JSON object.")
    expected_keys = {
        "schema_version",
        "study",
        "mode",
        "release_stack",
        "run_id",
        "provider_profile",
        "source_branch",
        "target_branch",
        "raw_collection",
        "ontology_context_version",
        "input_catalog",
        "limit",
        "conditions",
        "max_output_tokens",
        "output_safety_margin_tokens",
        "ontology_example_limit",
    }
    if set(payload) != expected_keys:
        raise ValueError(
            "Run specification keys must match the schema exactly; credentials, "
            "paths, and service names do not belong in the specification."
        )
    conditions = payload["conditions"]
    if not isinstance(conditions, list) or not all(
        isinstance(condition, str) for condition in conditions
    ):
        raise ValueError("conditions must be a list of condition names.")
    try:
        return HeaderSublemmaRunSpec(
            schema_version=int(payload["schema_version"]),
            study=str(payload["study"]),
            mode=str(payload["mode"]),
            release_stack=str(payload["release_stack"]),
            run_id=str(payload["run_id"]),
            provider_profile=str(payload["provider_profile"]),
            source_branch=str(payload["source_branch"]),
            target_branch=str(payload["target_branch"]),
            raw_collection=str(payload["raw_collection"]),
            ontology_context_version=str(payload["ontology_context_version"]),
            input_catalog=Path(str(payload["input_catalog"])),
            limit=int(payload["limit"]),
            conditions=tuple(conditions),
            max_output_tokens=int(payload["max_output_tokens"]),
            output_safety_margin_tokens=int(
                payload["output_safety_margin_tokens"]
            ),
            ontology_example_limit=int(payload["ontology_example_limit"]),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Run specification has an invalid scalar value."
        ) from error


def validate_isolated_specs(
    smoke: HeaderSublemmaRunSpec,
    full: HeaderSublemmaRunSpec,
) -> None:
    """Ensure smoke data cannot be reused by the complete run.

    :param smoke: Disposable one-unit contract.
    :param full: Complete 480-unit contract.
    :raises ValueError: If modes or any writable storage identity overlap.
    """
    if smoke.mode != "smoke" or full.mode != "full":
        raise ValueError("Isolation validation requires smoke and full specs.")
    identities = (
        ("run_id", smoke.run_id, full.run_id),
        ("target_branch", smoke.target_branch, full.target_branch),
        ("raw_collection", smoke.raw_collection, full.raw_collection),
        (
            "annotation_collection",
            smoke.annotation_collection,
            full.annotation_collection,
        ),
        (
            "ontology_collection",
            smoke.ontology_collection,
            full.ontology_collection,
        ),
    )
    reused = [name for name, left, right in identities if left == right]
    if reused:
        raise ValueError(
            "Smoke and full specs reuse writable identities: "
            + ", ".join(reused)
        )
