"""Resolve and verify source evidence for the published runtime stack."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseRepositories:
    """Point environment-lock capture at clean tagged source trees.

    :param datamodel_workflow: Clean DMW v1.1.4 checkout.
    :param opa: Clean OPA v2.1.3 checkout.
    :param gta: Clean GTA v0.2.5 checkout.
    :param haiu: Clean Haiu v1.8.1 checkout.
    """

    datamodel_workflow: Path
    opa: Path
    gta: Path
    haiu: Path


@dataclass(frozen=True, slots=True)
class ReleaseSource:
    """Describe one remote repository and the required published tag.

    :param url: Public repository containing the published release.
    :param revision: Published tag required by the study contract.
    :param destination_name: Stable ignored checkout-directory name.
    """

    url: str
    revision: str
    destination_name: str


RELEASE_SOURCES = {
    "datamodel_workflow": ReleaseSource(
        url="https://github.com/HisQu/datamodel-workflow.git",
        revision="v1.1.4",
        destination_name="datamodel-workflow-v1.1.4",
    ),
    "opa": ReleaseSource(
        url="https://github.com/HisQu/OPA.git",
        revision="v2.1.3",
        destination_name="opa-v2.1.3",
    ),
    "gta": ReleaseSource(
        url="https://github.com/HisQu/GTA.git",
        revision="v0.2.5",
        destination_name="gta-v0.2.5",
    ),
    "haiu": ReleaseSource(
        url="https://github.com/HisQu/haiu.git",
        revision="v1.8.1",
        destination_name="haiu-v1.8.1",
    ),
}


class ReleaseStackManager:
    """Create ignored release checkouts without requiring sibling repositories."""

    def __init__(self, *, output_root: Path) -> None:
        self.checkout_root = output_root / "runtime" / "release-checkouts"

    def ensure(self) -> ReleaseRepositories:
        """Return clean checkouts at every release required by the study.

        :return: Verified source paths for environment-lock capture.
        :raises RuntimeError: If a source, tag, checkout, or cleanliness check
            does not match the release contract.
        """
        paths = {
            name: self._ensure_checkout(source)
            for name, source in RELEASE_SOURCES.items()
        }
        return ReleaseRepositories(**paths)

    def _ensure_checkout(self, release: ReleaseSource) -> Path:
        """Create or verify one reusable release checkout.

        :param release: Source repository and required tag.
        :return: Clean checkout at the tag's exact commit.
        """
        destination = self.checkout_root / release.destination_name
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--filter=blob:none",
                    "--single-branch",
                    "--branch",
                    release.revision,
                    release.url,
                    str(destination),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(
                    f"Cannot clone {release.revision} evidence checkout: "
                    f"{detail}"
                )
        expected_commit = _git(
            destination,
            "rev-parse",
            f"{release.revision}^{{commit}}",
        )
        actual_commit = _git(destination, "rev-parse", "HEAD")
        if actual_commit != expected_commit:
            raise RuntimeError(
                f"Release evidence checkout differs from {release.revision}: "
                f"{destination}"
            )
        if _git(destination, "status", "--porcelain"):
            raise RuntimeError(
                f"Release evidence checkout is dirty: {destination}"
            )
        return destination


def _git(repository: Path, *arguments: str) -> str:
    """Run one read-only Git inspection and return stripped output.

    :param repository: Checkout used as the command working directory.
    :param arguments: Git subcommand and arguments.
    :return: Standard output without surrounding whitespace.
    :raises RuntimeError: If Git rejects the request.
    """
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Git inspection failed in {repository}: {detail}")
    return completed.stdout.strip()
