"""Recorded runtime-only transitions for an already frozen experiment run."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    REPOSITORY_ROOT,
)

RUNTIME_TRANSITION_SCHEMA_VERSION = 2
RUNTIME_PACKAGE_NAMES = ("datamodel-workflow", "opa", "gta", "haiu")


@dataclass(frozen=True, slots=True)
class RuntimeTransitionReport:
    """Summarize one recorded non-scientific runtime transition.

    :param execution: Provider execution whose resume identity changed.
    :param record: Portable transition-record path.
    :param source_harness_commit: Previously accepted harness commit.
    :param target_harness_commit: Replacement clean harness commit.
    :param source_haiu_version: Haiu version used before the transition.
    :param target_haiu_version: Haiu version used after the transition.
    """

    execution: str
    record: str
    source_harness_commit: str
    target_harness_commit: str
    source_haiu_version: str
    target_haiu_version: str


def record_runtime_transition(
    *,
    run_root: Path,
    execution: str,
    reason: str,
) -> RuntimeTransitionReport:
    """Record the clean harness and runtime patches adopted by a stopped run.

    The environment lock remains unchanged. The transition states the exact
    old and new runtime identities so resume can verify the narrow operational
    patch without weakening the frozen provider or scientific configuration.

    :param run_root: Copied run directory.
    :param execution: Provider execution being transitioned.
    :param reason: Concise factual reason for adopting the patch.
    :return: Durable transition summary.
    :raises ValueError: If evidence is absent, dirty, or contradictory.
    """
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("A runtime transition requires a non-empty reason.")
    environment = run_root.resolve() / "environment"
    lock = _load_json_object(environment / f"{execution}-environment-lock.json")
    source_packages = _locked_package_identities(lock)
    source_harness = _accepted_harness_before_runtime_transition(
        environment=environment,
        execution=execution,
        lock=lock,
    )
    target_harness = clean_harness_identity()
    target_packages = installed_runtime_package_identities()
    path = environment / f"{execution}-runtime-transition.json"
    history: list[dict[str, Any]] = []
    if path.exists():
        existing = _load_json_object(path)
        _validate_transition_source(
            record=existing,
            execution=execution,
            source_harness=source_harness,
            source_packages=source_packages,
        )
        if _transition_already_matches_target(
            record=existing,
            source_harness=source_harness,
            target_harness=target_harness,
            source_packages=source_packages,
            target_packages=target_packages,
            reason=normalized_reason,
        ):
            return _transition_report(
                run_root=run_root,
                execution=execution,
                path=path,
                source_harness=source_harness,
                target_harness=target_harness,
                source_packages=source_packages,
                target_packages=target_packages,
            )
        history = _transition_history(existing)
    payload = {
        "schema_version": RUNTIME_TRANSITION_SCHEMA_VERSION,
        "record_type": "haiu_comparison_runtime_transition",
        "status": "completed",
        "completed_at": datetime.now(UTC).isoformat(),
        "execution": execution,
        "reason": normalized_reason,
        "scientific_contract_changed": False,
        "source_harness": source_harness,
        "target_harness": target_harness,
        "source_packages": source_packages,
        "target_packages": target_packages,
        "history": history,
    }
    _write_json_atomic(path, payload)
    return _transition_report(
        run_root=run_root,
        execution=execution,
        path=path,
        source_harness=source_harness,
        target_harness=target_harness,
        source_packages=source_packages,
        target_packages=target_packages,
    )


def runtime_transition_matches(
    *,
    output_dir: Path,
    frozen_haiu_package: dict[str, Any],
    live_haiu_distribution: dict[str, Any],
    live_harness: dict[str, str | bool],
    frozen_packages: dict[str, Any] | None = None,
    live_distributions: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Validate the exact recorded old-to-new runtime identity.

    :param output_dir: Provider's ``raw-<execution>`` directory.
    :param frozen_haiu_package: Haiu entry from the immutable environment lock.
    :param live_haiu_distribution: Imported Haiu distribution provenance.
    :param live_harness: Clean harness identity running the resume command.
    :param frozen_packages: All runtime packages from the immutable lock.
    :param live_distributions: All installed runtime package provenance.
    :return: Whether a completed transition matches every relevant identity.
    """
    if not output_dir.name.startswith("raw-"):
        return False
    execution = output_dir.name.removeprefix("raw-")
    environment = output_dir.parent / "environment"
    path = environment / f"{execution}-runtime-transition.json"
    if not path.is_file():
        return False
    try:
        record = _load_json_object(path)
        lock = _load_json_object(
            environment / f"{execution}-environment-lock.json"
        )
        source_harness = _accepted_harness_before_runtime_transition(
            environment=environment,
            execution=execution,
            lock=lock,
        )
        frozen_haiu = _package_identity(frozen_haiu_package)
        live_haiu = _distribution_identity(live_haiu_distribution)
        target_harness = record.get("target_harness")
    except (OSError, ValueError):
        return False
    if record.get("schema_version") == 1:
        return _legacy_runtime_transition_matches(
            record=record,
            execution=execution,
            source_harness=source_harness,
            target_harness=target_harness,
            frozen_haiu=frozen_haiu,
            live_haiu=live_haiu,
            live_harness=live_harness,
        )
    if frozen_packages is None or live_distributions is None:
        return False
    try:
        frozen_package_identities = _package_identities(frozen_packages)
        live_package_identities = {
            name: _distribution_identity(live_distributions[name])
            for name in RUNTIME_PACKAGE_NAMES
        }
    except (KeyError, ValueError):
        return False
    return (
        record.get("schema_version") == RUNTIME_TRANSITION_SCHEMA_VERSION
        and record.get("record_type") == "haiu_comparison_runtime_transition"
        and record.get("status") == "completed"
        and record.get("execution") == execution
        and record.get("scientific_contract_changed") is False
        and record.get("source_harness") == source_harness
        and isinstance(target_harness, dict)
        and target_harness.get("commit") == live_harness.get("commit")
        and target_harness.get("worktree_clean") is True
        and live_harness.get("worktree_clean") is True
        and record.get("source_packages") == frozen_package_identities
        and record.get("target_packages") == live_package_identities
    )


def _legacy_runtime_transition_matches(
    *,
    record: dict[str, Any],
    execution: str,
    source_harness: dict[str, Any],
    target_harness: Any,
    frozen_haiu: dict[str, Any],
    live_haiu: dict[str, Any],
    live_harness: dict[str, str | bool],
) -> bool:
    """Validate the Haiu-only transition format shipped by version 0.4.1.

    :param record: Parsed schema-v1 transition record.
    :param execution: Provider execution derived from the raw directory.
    :param source_harness: Harness accepted before the runtime patch.
    :param target_harness: Target harness stored by the transition.
    :param frozen_haiu: Haiu identity from the immutable environment lock.
    :param live_haiu: Haiu identity imported by the runner.
    :param live_harness: Harness identity executing the resume.
    :return: Whether every schema-v1 identity matches exactly.
    """
    return (
        record.get("record_type") == "haiu_comparison_runtime_transition"
        and record.get("status") == "completed"
        and record.get("execution") == execution
        and record.get("scientific_contract_changed") is False
        and record.get("source_harness") == source_harness
        and isinstance(target_harness, dict)
        and target_harness.get("commit") == live_harness.get("commit")
        and target_harness.get("worktree_clean") is True
        and live_harness.get("worktree_clean") is True
        and record.get("source_haiu") == frozen_haiu
        and record.get("target_haiu") == live_haiu
    )


def _validate_transition_source(
    *,
    record: dict[str, Any],
    execution: str,
    source_harness: dict[str, Any],
    source_packages: dict[str, dict[str, Any]],
) -> None:
    """Reject attempts to overwrite a transition for a different frozen run.

    :param record: Existing transition record.
    :param execution: Provider execution being amended.
    :param source_harness: Harness accepted before any runtime transition.
    :param source_packages: Package identities from the immutable lock.
    :return: None.
    :raises ValueError: If the existing record has another source identity.
    """
    common_matches = (
        record.get("record_type") == "haiu_comparison_runtime_transition"
        and record.get("status") == "completed"
        and record.get("execution") == execution
        and record.get("scientific_contract_changed") is False
        and record.get("source_harness") == source_harness
    )
    schema_version = record.get("schema_version")
    if schema_version == 1:
        source_matches = record.get("source_haiu") == source_packages["haiu"]
    elif schema_version == RUNTIME_TRANSITION_SCHEMA_VERSION:
        source_matches = record.get("source_packages") == source_packages
    else:
        source_matches = False
    if not common_matches or not source_matches:
        raise ValueError(
            "Existing runtime transition belongs to another frozen identity."
        )


def _transition_already_matches_target(
    *,
    record: dict[str, Any],
    source_harness: dict[str, Any],
    target_harness: dict[str, Any],
    source_packages: dict[str, dict[str, Any]],
    target_packages: dict[str, dict[str, Any]],
    reason: str,
) -> bool:
    """Return whether a schema-v2 record already describes this target.

    :param record: Existing transition record.
    :param source_harness: Original accepted harness.
    :param target_harness: Current clean harness.
    :param source_packages: Runtime identities frozen at run start.
    :param target_packages: Runtime identities installed now.
    :param reason: Requested factual transition reason.
    :return: Whether rewriting the record would be redundant.
    """
    return (
        record.get("schema_version") == RUNTIME_TRANSITION_SCHEMA_VERSION
        and record.get("reason") == reason
        and record.get("source_harness") == source_harness
        and record.get("target_harness") == target_harness
        and record.get("source_packages") == source_packages
        and record.get("target_packages") == target_packages
    )


def _transition_history(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Retain earlier accepted targets while amending an aggregate transition.

    :param record: Existing schema-v1 or schema-v2 transition record.
    :return: Ordered non-scientific runtime checkpoints.
    """
    existing_history = record.get("history")
    history = (
        list(existing_history) if isinstance(existing_history, list) else []
    )
    checkpoint: dict[str, Any] = {
        "completed_at": record.get("completed_at"),
        "reason": record.get("reason"),
        "target_harness": record.get("target_harness"),
    }
    if record.get("schema_version") == 1:
        checkpoint["target_packages"] = {"haiu": record.get("target_haiu")}
    else:
        checkpoint["target_packages"] = record.get("target_packages")
    if not history or history[-1] != checkpoint:
        history.append(checkpoint)
    return history


def _transition_report(
    *,
    run_root: Path,
    execution: str,
    path: Path,
    source_harness: dict[str, Any],
    target_harness: dict[str, Any],
    source_packages: dict[str, dict[str, Any]],
    target_packages: dict[str, dict[str, Any]],
) -> RuntimeTransitionReport:
    """Build the stable command result from an aggregate transition.

    :param run_root: Copied run directory.
    :param execution: Provider execution being transitioned.
    :param path: Written transition-record path.
    :param source_harness: Original accepted harness.
    :param target_harness: Current clean harness.
    :param source_packages: Runtime identities frozen at run start.
    :param target_packages: Runtime identities installed now.
    :return: Concise transition summary for CLI output.
    """
    return RuntimeTransitionReport(
        execution=execution,
        record=path.relative_to(run_root.resolve()).as_posix(),
        source_harness_commit=str(source_harness["commit"]),
        target_harness_commit=str(target_harness["commit"]),
        source_haiu_version=str(source_packages["haiu"]["version"]),
        target_haiu_version=str(target_packages["haiu"]["version"]),
    )


def clean_harness_identity() -> dict[str, Any]:
    """Capture the current committed experiment harness.

    :return: Commit, branch, and cleanliness evidence.
    :raises ValueError: If Git cannot prove a clean committed checkout.
    """
    commands = {
        "commit": ("git", "rev-parse", "HEAD"),
        "branch": ("git", "branch", "--show-current"),
        "status": ("git", "status", "--porcelain"),
    }
    outputs: dict[str, str] = {}
    for label, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise ValueError(f"Cannot inspect experiment harness Git {label}.")
        outputs[label] = completed.stdout.strip()
    if outputs["status"]:
        raise ValueError(
            "Commit the runtime patch before recording its transition."
        )
    return {
        "commit": outputs["commit"],
        "branch": outputs["branch"],
        "worktree_clean": True,
    }


def installed_runtime_package_identities() -> dict[str, dict[str, Any]]:
    """Read every installed package identity covered by runtime transitions.

    :return: Package identities keyed by distribution name.
    :raises ValueError: If any required distribution identity is unavailable.
    """
    return {
        name: _installed_distribution_identity(name)
        for name in RUNTIME_PACKAGE_NAMES
    }


def _installed_distribution_identity(name: str) -> dict[str, Any]:
    """Read one installed distribution's version and Git source identity.

    :param name: Installed distribution name.
    :return: Minimal non-secret distribution identity.
    :raises ValueError: If installed metadata is absent or malformed.
    """
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError as exc:
        raise ValueError(
            f"The active environment has no {name} distribution."
        ) from exc
    direct_url_text = distribution.read_text("direct_url.json")
    try:
        direct_url = json.loads(direct_url_text) if direct_url_text else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} direct_url.json is invalid.") from exc
    if not isinstance(direct_url, dict):
        raise ValueError(f"{name} direct_url.json is not an object.")
    vcs_info = direct_url.get("vcs_info")
    vcs_info = vcs_info if isinstance(vcs_info, dict) else {}
    dir_info = direct_url.get("dir_info")
    dir_info = dir_info if isinstance(dir_info, dict) else {}
    return {
        "version": distribution.version,
        "url": direct_url.get("url"),
        "requested_revision": vcs_info.get("requested_revision"),
        "commit_id": vcs_info.get("commit_id"),
        "editable": bool(dir_info.get("editable")),
    }


def _accepted_harness_before_runtime_transition(
    *,
    environment: Path,
    execution: str,
    lock: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the latest accepted harness before this transition.

    :param environment: Run environment directory.
    :param execution: Provider execution name.
    :param lock: Parsed immutable environment lock.
    :return: Original or artifact-migration target harness identity.
    """
    migration_path = environment / f"{execution}-artifact-layout-migration.json"
    if migration_path.is_file():
        migration = _load_json_object(migration_path)
        target = migration.get("target_harness")
        if migration.get("status") == "completed" and isinstance(target, dict):
            return target
    original = lock.get("experiment_harness")
    if not isinstance(original, dict):
        raise ValueError("Environment lock has no experiment-harness identity.")
    return original


def _locked_package_identities(
    lock: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Read transition-controlled packages from one environment lock.

    :param lock: Parsed environment lock.
    :return: Minimal identities keyed by distribution name.
    """
    runtime = lock.get("runtime")
    packages = runtime.get("packages") if isinstance(runtime, dict) else None
    if not isinstance(packages, dict):
        raise ValueError("Environment lock has no runtime package identities.")
    return _package_identities(packages)


def _package_identities(
    packages: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Normalize every package governed by a runtime transition.

    :param packages: Frozen package records keyed by distribution name.
    :return: Minimal identities keyed by distribution name.
    :raises ValueError: If a required package record is missing.
    """
    identities: dict[str, dict[str, Any]] = {}
    for name in RUNTIME_PACKAGE_NAMES:
        package = packages.get(name)
        if not isinstance(package, dict):
            raise ValueError(f"Package identity is missing for {name}.")
        identities[name] = _package_identity(package)
    return identities


def _package_identity(package: dict[str, Any]) -> dict[str, Any]:
    """Normalize one environment-lock package record.

    :param package: Frozen package record.
    :return: Minimal version and source identity.
    """
    source = package.get("source")
    if not isinstance(source, dict):
        raise ValueError("Package record has no source identity.")
    return {
        "version": package.get("version"),
        "url": source.get("url"),
        "requested_revision": source.get("requested_revision"),
        "commit_id": source.get("commit_id"),
        "editable": bool(source.get("editable")),
    }


def _distribution_identity(provenance: dict[str, Any]) -> dict[str, Any]:
    """Normalize one live installed-distribution provenance record.

    :param provenance: Runner distribution-provenance mapping.
    :return: Minimal version and source identity.
    """
    return {
        "version": provenance.get("version"),
        "url": provenance.get("direct_url"),
        "requested_revision": provenance.get("requested_revision"),
        "commit_id": provenance.get("commit_id"),
        "editable": bool(provenance.get("editable")),
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    """Read one JSON object.

    :param path: Existing JSON file.
    :return: Parsed object.
    :raises ValueError: If the file does not contain an object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document is not an object: {path.name}")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON object through an adjacent temporary file.

    :param path: Final destination.
    :param payload: JSON-compatible object.
    :return: None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
