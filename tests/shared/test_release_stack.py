"""Tests for automatic published-tag evidence checkouts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dmw_experiments.shared.execution.release_stack import (
    RELEASE_SOURCES,
    ReleaseSource,
    ReleaseStackManager,
)
from dmw_experiments.studies.haiu_comparison.data_collection.protocol import (
    APPROVED_RUNTIME_DISTRIBUTIONS,
)
from dmw_experiments.studies.haiu_comparison.operations.environment_lock import (
    APPROVED_DISTRIBUTIONS,
)


def _git(repository: Path, *arguments: str) -> None:
    """Run one test-repository mutation and require success.

    :param repository: Temporary repository used as command working directory.
    :param arguments: Git subcommand and arguments.
    :return: ``None`` after a successful command.
    """
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _tagged_origin(tmp_path: Path) -> Path:
    """Create a local tagged origin without relying on network access.

    :param tmp_path: Isolated pytest directory.
    :return: Repository containing one commit at ``v1.0.0``.
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "--quiet")
    _git(origin, "config", "user.name", "Experiment Test")
    _git(origin, "config", "user.email", "experiment@example.invalid")
    _git(origin, "config", "commit.gpgsign", "false")
    (origin / "release.txt").write_text("published\n", encoding="utf-8")
    _git(origin, "add", "release.txt")
    _git(origin, "commit", "--quiet", "-m", "Publish test release")
    _git(origin, "tag", "v1.0.0")
    return origin


def test_release_checkout_is_cloned_once_and_reused(tmp_path: Path) -> None:
    """A remote tag becomes a clean ignored checkout without sibling repos."""
    origin = _tagged_origin(tmp_path)
    manager = ReleaseStackManager(output_root=tmp_path / "output")
    release = ReleaseSource(
        url=str(origin),
        revision="v1.0.0",
        destination_name="component-v1.0.0",
    )

    first = manager._ensure_checkout(release)
    second = manager._ensure_checkout(release)

    assert first == second
    assert (first / "release.txt").read_text(encoding="utf-8") == "published\n"


def test_release_checkout_rejects_local_changes(tmp_path: Path) -> None:
    """Provenance capture cannot silently accept a dirty release checkout."""
    origin = _tagged_origin(tmp_path)
    manager = ReleaseStackManager(output_root=tmp_path / "output")
    release = ReleaseSource(
        url=str(origin),
        revision="v1.0.0",
        destination_name="component-v1.0.0",
    )
    checkout = manager._ensure_checkout(release)
    (checkout / "release.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="dirty"):
        manager._ensure_checkout(release)


def test_published_stack_uses_one_approved_release_contract() -> None:
    """Collection validation and evidence checkouts cannot drift by version."""
    assert APPROVED_DISTRIBUTIONS is APPROVED_RUNTIME_DISTRIBUTIONS
    distribution_names = {
        "datamodel_workflow": "datamodel-workflow",
        "opa": "opa",
        "gta": "gta",
        "haiu": "haiu",
    }
    for repository_name, distribution_name in distribution_names.items():
        release = RELEASE_SOURCES[repository_name]
        approved = APPROVED_RUNTIME_DISTRIBUTIONS[distribution_name]
        assert release.url == approved["url"]
        assert release.revision == approved["revision"]
