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

RUNTIME_TRANSITION_SCHEMA_VERSION = 1


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
    """Record the clean harness and Haiu patch adopted by a stopped run.

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
    source_haiu = _locked_haiu_identity(lock)
    source_harness = _accepted_harness_before_runtime_transition(
        environment=environment,
        execution=execution,
        lock=lock,
    )
    target_harness = clean_harness_identity()
    target_haiu = installed_haiu_identity()
    path = environment / f"{execution}-runtime-transition.json"
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
        "source_haiu": source_haiu,
        "target_haiu": target_haiu,
    }
    if path.exists():
        existing = _load_json_object(path)
        comparable_fields = (
            "schema_version",
            "record_type",
            "status",
            "execution",
            "reason",
            "scientific_contract_changed",
            "source_harness",
            "target_harness",
            "source_haiu",
            "target_haiu",
        )
        if any(existing.get(key) != payload[key] for key in comparable_fields):
            raise ValueError(
                "Runtime transition record differs from the requested identity."
            )
        payload = existing
    else:
        _write_json_atomic(path, payload)
    return RuntimeTransitionReport(
        execution=execution,
        record=path.relative_to(run_root.resolve()).as_posix(),
        source_harness_commit=str(source_harness["commit"]),
        target_harness_commit=str(target_harness["commit"]),
        source_haiu_version=str(source_haiu["version"]),
        target_haiu_version=str(target_haiu["version"]),
    )


def runtime_transition_matches(
    *,
    output_dir: Path,
    frozen_haiu_package: dict[str, Any],
    live_haiu_distribution: dict[str, Any],
    live_harness: dict[str, str | bool],
) -> bool:
    """Validate the exact recorded old-to-new runtime identity.

    :param output_dir: Provider's ``raw-<execution>`` directory.
    :param frozen_haiu_package: Haiu entry from the immutable environment lock.
    :param live_haiu_distribution: Imported Haiu distribution provenance.
    :param live_harness: Clean harness identity running the resume command.
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
        frozen_haiu = _package_haiu_identity(frozen_haiu_package)
        live_haiu = _distribution_haiu_identity(live_haiu_distribution)
        target_harness = record.get("target_harness")
    except (OSError, ValueError):
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
        and record.get("source_haiu") == frozen_haiu
        and record.get("target_haiu") == live_haiu
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


def installed_haiu_identity() -> dict[str, Any]:
    """Read the installed Haiu version and Git source identity.

    :return: Minimal non-secret distribution identity.
    :raises ValueError: If installed metadata is absent or malformed.
    """
    try:
        distribution = metadata.distribution("haiu")
    except metadata.PackageNotFoundError as exc:
        raise ValueError(
            "The active environment has no Haiu distribution."
        ) from exc
    direct_url_text = distribution.read_text("direct_url.json")
    try:
        direct_url = json.loads(direct_url_text) if direct_url_text else {}
    except json.JSONDecodeError as exc:
        raise ValueError("Haiu direct_url.json is invalid.") from exc
    if not isinstance(direct_url, dict):
        raise ValueError("Haiu direct_url.json is not an object.")
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


def _locked_haiu_identity(lock: dict[str, Any]) -> dict[str, Any]:
    """Read the frozen Haiu package identity from one environment lock.

    :param lock: Parsed environment lock.
    :return: Minimal version and source identity.
    """
    runtime = lock.get("runtime")
    packages = runtime.get("packages") if isinstance(runtime, dict) else None
    package = packages.get("haiu") if isinstance(packages, dict) else None
    if not isinstance(package, dict):
        raise ValueError("Environment lock has no Haiu package identity.")
    return _package_haiu_identity(package)


def _package_haiu_identity(package: dict[str, Any]) -> dict[str, Any]:
    """Normalize an environment-lock Haiu package record.

    :param package: Frozen package record.
    :return: Minimal version and source identity.
    """
    source = package.get("source")
    if not isinstance(source, dict):
        raise ValueError("Haiu package record has no source identity.")
    return {
        "version": package.get("version"),
        "url": source.get("url"),
        "requested_revision": source.get("requested_revision"),
        "commit_id": source.get("commit_id"),
        "editable": bool(source.get("editable")),
    }


def _distribution_haiu_identity(provenance: dict[str, Any]) -> dict[str, Any]:
    """Normalize live runner Haiu provenance.

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
