#!/usr/bin/env python3
"""Capture the non-secret, frozen execution evidence for one provider run.

This command deliberately records hashes and stable identities instead of
copying dotenv files, endpoint URLs, tokens, or absolute local paths.  The
comparison runner copies its resulting JSON document into the immutable run
provenance directory under the ``environment_lock`` label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dmw_experiments.studies.haiu_comparison.model.providers import (
    PROVIDER_PROFILES,
    provider_profile,
)
from dmw_experiments.studies.haiu_comparison.model.inputs import (
    load_dmw_pair_import_manifest,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    RUN_TEMPLATE_ROOT,
)

EXPERIMENT_ROOT = RUN_TEMPLATE_ROOT

APPROVED_DISTRIBUTIONS = {
    "datamodel-workflow": {
        "version": "1.1.4",
        "url": "https://github.com/HisQu/datamodel-workflow.git",
        "revision": "v1.1.4",
        "repository": "datamodel_workflow",
    },
    "opa": {
        "version": "2.1.3",
        "url": "https://github.com/HisQu/OPA.git",
        "revision": "v2.1.3",
        "repository": "opa",
    },
    "gta": {
        "version": "0.2.4",
        "url": "https://github.com/HisQu/GTA.git",
        "revision": "v0.2.4",
        "repository": "gta",
    },
    "haiu": {
        "version": "1.8.1",
        "url": "https://github.com/HisQu/haiu.git",
        "revision": "v1.8.1",
        "repository": "haiu",
    },
}
REPORTED_DISTRIBUTIONS = tuple(APPROVED_DISTRIBUTIONS)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for one environment snapshot.

    :return: Configured parser with explicit mutable experiment identities.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Write a non-secret DMW/OPA/Haiu environment-lock JSON document "
            "for one publication comparison provider run."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--provider-profile",
        choices=tuple(PROVIDER_PROFILES),
        required=True,
    )
    parser.add_argument("--dmw-ontology-branch", required=True)
    parser.add_argument("--dmw-ontology-collection", required=True)
    parser.add_argument("--dmw-raw-collection", default="RG_raw")
    parser.add_argument("--dmw-annotation-collection", default="")
    parser.add_argument("--ontology-context-version", default="")
    parser.add_argument("--input-catalog", type=Path, default=None)
    parser.add_argument("--dmw-input-manifest", type=Path, default=None)
    parser.add_argument("--chat-endpoint", required=True)
    parser.add_argument("--embedding-endpoint", required=True)
    parser.add_argument(
        "--provider-environment-file",
        type=Path,
        required=True,
        help="Provider-specific non-secret profile file; only its hash is recorded.",
    )
    parser.add_argument(
        "--dmw-repo",
        type=Path,
        required=True,
    )
    parser.add_argument("--opa-repo", type=Path, required=True)
    parser.add_argument("--gta-repo", type=Path, required=True)
    parser.add_argument("--haiu-repo", type=Path, required=True)
    parser.add_argument(
        "--experiment-repo",
        type=Path,
        required=True,
        help=(
            "Clean dmw_experiments checkout containing the harness; distinct "
            "from --haiu-repo, which remains at the published v1.8.1 tag."
        ),
    )
    parser.add_argument(
        "--dmw-python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable serving DMW; its path is never recorded.",
    )
    parser.add_argument(
        "--lmstudio-model-file",
        type=Path,
        default=None,
        help="Required only for the LM Studio Q6 profile; only SHA-256 is recorded.",
    )
    parser.add_argument(
        "--lmstudio-model-file-sha256",
        default="",
        help=(
            "Previously verified model-file SHA-256 for an LM Studio linked "
            "device whose file is not locally readable."
        ),
    )
    parser.add_argument(
        "--lmstudio-runtime-version",
        default="",
        help="Required only for the LM Studio Q6 profile.",
    )
    parser.add_argument(
        "--lmstudio-context-window-tokens",
        type=int,
        default=None,
        help="Required only for the LM Studio Q6 profile.",
    )
    return parser


def _sha256_bytes(content: bytes) -> str:
    """Calculate a portable SHA-256 content identity.

    :param content: Source bytes to identify.
    :return: Lowercase hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash one required file without retaining its local path.

    :param path: Existing regular file to identify.
    :return: Lowercase hexadecimal SHA-256 digest.
    :raises SystemExit: If the requested file does not exist.
    """
    if not path.is_file():
        raise SystemExit(f"Required file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_command(command: list[str], *, cwd: Path | None = None) -> str:
    """Run a small local inspection command and return stripped stdout.

    :param command: Non-mutating command and arguments.
    :param cwd: Optional working directory for the command.
    :return: Standard output without surrounding whitespace.
    :raises SystemExit: If inspection fails or emits an error.
    """
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(f"Inspection failed: {' '.join(command)}: {detail}")
    return completed.stdout.strip()


def _frozen_repository(repo: Path, *, label: str) -> dict[str, Any]:
    """Return commit and dependency-lock identities for one clean source tree.

    :param repo: Repository whose checked-in lock files must be frozen.
    :param label: Human-readable repository label for error messages.
    :return: Non-secret commit, cleanliness, and file-hash evidence.
    :raises SystemExit: If the repository is absent or has uncommitted changes.
    """
    if not repo.is_dir():
        raise SystemExit(f"{label} repository does not exist: {repo}")
    status = _run_command(["git", "status", "--porcelain"], cwd=repo)
    if status:
        raise SystemExit(
            f"{label} repository has uncommitted changes; commit or stash them "
            "before freezing the publication environment."
        )
    commit = _run_command(["git", "rev-parse", "HEAD"], cwd=repo)
    lock_files: dict[str, str] = {}
    for filename in ("pyproject.toml", "uv.lock", "pylock.toml"):
        candidate = repo / filename
        if candidate.is_file():
            lock_files[filename] = _sha256_file(candidate)
    return {
        "commit": commit,
        "worktree_clean": True,
        "dependency_file_sha256": lock_files,
    }


def _frozen_experiment_harness(repo: Path) -> dict[str, Any]:
    """Capture the clean commit that owns the experiment orchestration.

    This identity is separate from the installed ``haiu==1.8.1`` package
    evidence. The experiment branch may advance without changing the runtime
    package used by the measured conditions.

    :param repo: Clean ``dmw_experiments`` checkout containing the harness.
    :return: Commit and branch identity without a local path.
    :raises SystemExit: If the checkout is absent or dirty.
    """
    if not repo.is_dir():
        raise SystemExit(f"Experiment repository does not exist: {repo}")
    status = _run_command(["git", "status", "--porcelain"], cwd=repo)
    if status:
        raise SystemExit(
            "Experiment repository has uncommitted changes; commit them before "
            "freezing the pair-run environment."
        )
    return {
        "commit": _run_command(["git", "rev-parse", "HEAD"], cwd=repo),
        "branch": _run_command(
            ["git", "branch", "--show-current"],
            cwd=repo,
        ),
        "worktree_clean": True,
    }


def _package_report(python_executable: Path) -> dict[str, Any]:
    """Read selected installed-distribution identities from the DMW runtime.

    The subprocess emits no local installation paths.  VCS provenance is
    retained because the release-gated stack intentionally pins every package
    to a published tag and resolved commit.

    :param python_executable: Interpreter used by the running DMW service.
    :return: Installed package versions, hashes, and non-secret source data.
    :raises SystemExit: If the interpreter cannot provide all required packages.
    """
    if not python_executable.is_file():
        raise SystemExit(
            f"DMW Python executable does not exist: {python_executable}"
        )
    script = """
import hashlib
import importlib.metadata as metadata
import json

names = (\"datamodel-workflow\", \"opa\", \"gta\", \"haiu\")
report = {}
for name in names:
    distribution = metadata.distribution(name)
    direct_url = distribution.read_text(\"direct_url.json\") or \"{}\"
    try:
        source = json.loads(direct_url)
    except json.JSONDecodeError:
        source = {}
    archive = source.get(\"archive_info\") or {}
    directory = source.get(\"dir_info\") or {}
    vcs = source.get(\"vcs_info\") or {}
    report[name] = {
        \"version\": distribution.version,
        \"record_sha256\": hashlib.sha256(
            (distribution.read_text(\"RECORD\") or \"\").encode(\"utf-8\")
        ).hexdigest(),
        \"source\": {
            \"url\": source.get(\"url\") if str(source.get(\"url\") or \"\").startswith(\"https://\") else None,
            \"archive_hash\": archive.get(\"hash\"),
            \"editable\": bool(directory.get(\"editable\")),
            \"vcs\": vcs.get(\"vcs\"),
            \"requested_revision\": vcs.get(\"requested_revision\"),
            \"commit_id\": vcs.get(\"commit_id\"),
        },
    }
print(json.dumps({\"python_version\": __import__(\"sys\").version, \"packages\": report}))
"""
    payload = _run_command([str(python_executable), "-c", script])
    try:
        report = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit("DMW package report was not valid JSON.") from exc
    packages = report.get("packages")
    if not isinstance(packages, dict) or set(packages) != set(
        REPORTED_DISTRIBUTIONS
    ):
        raise SystemExit(
            "DMW package report is missing a required distribution."
        )
    return report


def _require_approved_distributions(
    package_report: dict[str, Any],
    repositories: dict[str, dict[str, Any]],
) -> None:
    """Reject runtime packages outside the released, commit-matched stack.

    :param package_report: Parsed installed-package evidence.
    :param repositories: Frozen source-tree evidence keyed by repository.
    :return: None.
    :raises SystemExit: If a package is editable, unpinned, or commit-mismatched.
    """
    for distribution_name, expected in APPROVED_DISTRIBUTIONS.items():
        package = package_report["packages"][distribution_name]
        source = package["source"]
        repository = repositories[str(expected["repository"])]
        if (
            package["version"] != expected["version"]
            or source["editable"]
            or source["vcs"] != "git"
            or source["url"] != expected["url"]
            or source["requested_revision"] != expected["revision"]
            or not _is_git_commit_id(source["commit_id"])
            or source["commit_id"] != repository["commit"]
        ):
            raise SystemExit(
                f"DMW must import non-editable {distribution_name}=="
                f"{expected['version']} from {expected['revision']} at the "
                "same commit recorded for its clean source repository."
            )


def validated_stack_packages(
    package_report: dict[str, Any],
    expected_versions: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the installed package table after version-contract checks.

    The subprocess report wraps packages beside its Python version. Keeping
    that shape interpretation here prevents lifecycle callers from comparing
    stack names against the outer report object.

    :param package_report: Output from :func:`_package_report`.
    :param expected_versions: Distribution versions from ``stack-lock.json``.
    :return: Installed package records keyed by distribution name.
    :raises ValueError: If the report shape or a pinned version differs.
    """
    packages = package_report.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("Installed package report has no packages table.")
    for name, expected_version in expected_versions.items():
        package = packages.get(name)
        approved = APPROVED_DISTRIBUTIONS.get(name)
        if (
            not isinstance(package, dict)
            or package.get("version") != expected_version
            or approved is None
            or approved.get("version") != expected_version
        ):
            raise ValueError(f"Installed publication package differs: {name}.")
    return packages


def _is_git_commit_id(value: object) -> bool:
    """Return whether one value is a full lowercase Git object identifier.

    :param value: Candidate value from installed-package provenance.
    :return: Whether the value is a 40-character hexadecimal Git commit ID.
    """
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{40}", value) is not None
    )


def _provider_runtime(args: argparse.Namespace) -> dict[str, Any]:
    """Build provider-specific evidence without retaining local locations.

    :param args: Parsed command-line arguments.
    :return: Non-secret profile, endpoint-hash, and quantization evidence.
    :raises SystemExit: If LM Studio Q6 evidence is incomplete or misplaced.
    """
    profile = provider_profile(args.provider_profile)
    runtime: dict[str, Any] = {
        "profile": profile.manifest_entry(),
        "chat_endpoint_sha256": _sha256_bytes(
            args.chat_endpoint.encode("utf-8")
        ),
        "embedding_endpoint_sha256": _sha256_bytes(
            args.embedding_endpoint.encode("utf-8")
        ),
        "provider_environment_file_sha256": _sha256_file(
            args.provider_environment_file
        ),
    }
    lmstudio_requested = any(
        value is not None and value != ""
        for value in (
            args.lmstudio_model_file,
            args.lmstudio_model_file_sha256,
            args.lmstudio_runtime_version,
            args.lmstudio_context_window_tokens,
        )
    )
    if profile.name == "lmstudio-qwen36-q6":
        if args.lmstudio_model_file is not None:
            model_file_sha256 = _sha256_file(args.lmstudio_model_file)
        elif re.fullmatch(
            r"[0-9a-f]{64}",
            args.lmstudio_model_file_sha256,
        ):
            model_file_sha256 = args.lmstudio_model_file_sha256
        else:
            model_file_sha256 = ""
        if (
            not model_file_sha256
            or not args.lmstudio_runtime_version
            or args.lmstudio_context_window_tokens is None
        ):
            raise SystemExit(
                "LM Studio Q6 requires --lmstudio-model-file or a valid "
                "--lmstudio-model-file-sha256, "
                "--lmstudio-runtime-version, and "
                "--lmstudio-context-window-tokens."
            )
        if (
            args.lmstudio_model_file is not None
            and args.lmstudio_model_file_sha256
        ):
            raise SystemExit(
                "Provide either --lmstudio-model-file or "
                "--lmstudio-model-file-sha256, not both."
            )
        runtime["lmstudio"] = {
            "model_file_sha256": model_file_sha256,
            "runtime_version": args.lmstudio_runtime_version,
            "context_window_tokens": args.lmstudio_context_window_tokens,
        }
    elif lmstudio_requested:
        raise SystemExit(
            "LM Studio runtime fields are only valid for "
            "--provider-profile lmstudio-qwen36-q6."
        )
    return runtime


def _pair_input_evidence(args: argparse.Namespace) -> dict[str, Any] | None:
    """Validate and identify the prepared header--sublemma population.

    Pair-run capture is activated only when both pair inputs are supplied. The
    import manifest must bind the exact catalogue to the collection identities
    passed on this command line.

    :param args: Parsed environment-capture arguments.
    :return: Portable input and DMW storage identity, or ``None`` for the
        existing complete-regest protocol.
    :raises SystemExit: If pair evidence is incomplete or inconsistent.
    """
    requested = (
        args.input_catalog is not None or args.dmw_input_manifest is not None
    )
    if not requested:
        return None
    if args.input_catalog is None or args.dmw_input_manifest is None:
        raise SystemExit(
            "Pair-run capture requires both --input-catalog and "
            "--dmw-input-manifest."
        )
    if args.provider_profile != "academiccloud-qwen36":
        raise SystemExit(
            "The header--sublemma replication is restricted to "
            "--provider-profile academiccloud-qwen36."
        )
    if args.dmw_raw_collection == "RG_raw":
        raise SystemExit(
            "Pair-run capture requires an isolated --dmw-raw-collection."
        )
    if not args.dmw_annotation_collection:
        raise SystemExit(
            "Pair-run capture requires --dmw-annotation-collection."
        )
    if not args.ontology_context_version:
        raise SystemExit(
            "Pair-run capture requires --ontology-context-version."
        )

    try:
        catalog = load_header_sublemma_catalog(args.input_catalog)
        manifest = load_dmw_pair_import_manifest(
            args.dmw_input_manifest,
            catalog=catalog,
        )
    except ValueError as exc:
        raise SystemExit(
            f"Cannot validate pair-run input evidence: {exc}"
        ) from exc
    collections = manifest.collections
    target_branch = manifest.target_branch
    expected_catalogue = {
        "schema_version": 1,
        "unit_kind": "header_sublemma_pair",
        "file_sha256": catalog.file_sha256,
        "catalogue_content_sha256": catalog.content_sha256,
        "input_unit_count": len(catalog.records),
    }
    expected_storage = {
        "branch": args.dmw_ontology_branch,
        "raw": args.dmw_raw_collection,
        "annotation": args.dmw_annotation_collection,
        "ontology": args.dmw_ontology_collection,
        "ontology_context_version": args.ontology_context_version,
    }
    observed_storage = {
        "branch": target_branch.get("branch_slug"),
        "raw": collections.get("raw"),
        "annotation": collections.get("annotation"),
        "ontology": collections.get("ontology"),
        "ontology_context_version": manifest.ontology_context_version,
    }
    if observed_storage != expected_storage:
        raise SystemExit(
            "DMW pair import manifest differs from the requested branch, "
            "collections, or ontology context version."
        )
    return {
        "input_population": {
            **expected_catalogue,
            "dmw_import_manifest_file_sha256": manifest.file_sha256,
            "dmw_import_manifest_content_sha256": manifest.content_sha256,
        },
        "dmw_data_identity": expected_storage,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write the snapshot atomically while keeping its output path external.

    :param path: Requested JSON output file.
    :param payload: Non-secret evidence to serialize.
    :return: None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Capture a validated environment-lock artifact for one clean provider run.

    :param argv: Optional command-line arguments for tests and direct use.
    :return: Zero after writing the JSON artifact.
    """
    args = _build_parser().parse_args(argv)
    repositories = {
        "datamodel_workflow": _frozen_repository(
            args.dmw_repo,
            label="DMW",
        ),
        "opa": _frozen_repository(args.opa_repo, label="OPA"),
        "gta": _frozen_repository(args.gta_repo, label="GTA"),
        "haiu": _frozen_repository(args.haiu_repo, label="Haiu"),
    }
    installed = _package_report(args.dmw_python)
    _require_approved_distributions(installed, repositories)
    pair_evidence = _pair_input_evidence(args)
    payload = {
        "schema_version": 2 if pair_evidence is not None else 1,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "DMW–Haiu publication comparison environment lock",
        "repositories": repositories,
        "dmw_ontology_identity": {
            "branch": args.dmw_ontology_branch,
            "collection": args.dmw_ontology_collection,
        },
        "runtime": installed,
        "provider": _provider_runtime(args),
        "model_catalogue": {
            "capture": "live DMW API at experiment preflight",
            "recorded_in": "provenance_manifest.json and run_manifest.json",
        },
    }
    if pair_evidence is not None:
        payload.update(pair_evidence)
        payload["experiment_harness"] = _frozen_experiment_harness(
            args.experiment_repo
        )
    _write_json(args.output, payload)
    print(f"Wrote environment lock: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
