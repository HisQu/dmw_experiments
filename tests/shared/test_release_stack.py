"""Tests for automatic published-tag evidence checkouts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dmw_experiments.shared.execution.release_stack import (
    ReleaseSource,
    ReleaseStackManager,
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
