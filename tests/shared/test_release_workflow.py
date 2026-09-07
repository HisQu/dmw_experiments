"""Tests for the repository release contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _just_recipe(name: str) -> str:
    """Return one recipe body from the project justfile."""
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^{re.escape(name)}(?:[ \t][^\n]*)?:\n(?P<body>.*?)(?=^\S|\Z)",
        justfile,
    )
    assert match is not None
    return match.group("body")


def test_release_workflow_uses_tracked_policy_and_existing_assets() -> None:
    """Tag and recovery jobs should publish the artifacts they receive."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    checks, remainder = workflow.split("  build:", maxsplit=1)
    build, remainder = remainder.split("  github-release:", maxsplit=1)
    github_release, remainder = remainder.split("  pypi-publish:", maxsplit=1)
    pypi_publish, publish_existing = remainder.split(
        "  publish-existing-release:", maxsplit=1
    )

    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow
    assert "if: github.event_name == 'push'" in checks
    assert "just --evaluate RELEASE_PYPI" in build
    assert "actions/upload-artifact@v7" in build
    assert "actions/download-artifact@v8" in github_release
    assert "actions/download-artifact@v8" in pypi_publish
    assert "needs.build.outputs.release_pypi == 'true'" in pypi_publish
    assert "if: github.event_name == 'workflow_dispatch'" in publish_existing
    assert "gh release download" in publish_existing
    assert "exactly one wheel and one source archive" in publish_existing
    assert "dmw_experiments-${version}-*.whl" in publish_existing
    assert '"dmw_experiments-${version}.tar.gz"' in publish_existing
    assert "twine check" in publish_existing
    assert "uv build" not in publish_existing
    assert "actions/checkout" not in publish_existing
    assert "--check-url https://pypi.org/simple/dmw-experiments/" in workflow
    assert "artifact@v4" not in workflow
    assert "PUBLISH_PYPI" not in workflow


def test_release_recipes_split_preparation_push_and_recovery() -> None:
    """Each release phase should remain explicit and retryable."""
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    release = _just_recipe("release")
    release_prepare = _just_recipe("release-prepare")
    release_push = _just_recipe("release-push")
    publish_pypi = _just_recipe("publish-pypi")

    assert 'RELEASE_PYPI := "false"' in justfile
    assert 'just release-prepare "{{ level }}"' in release
    assert 'just release-push "$tag"' in release
    assert re.search(r"(?m)^\s+git push\b", release_prepare) is None
    assert 'git push --atomic origin main "$tag"' in release_push
    assert "git branch --show-current" in release_push
    assert 'git cat-file -e "${tag}^{tag}"' in release_push
    assert "just --evaluate RELEASE_PYPI" in release_push
    assert "gh workflow run release.yml" in publish_pypi
    assert "isDraft" in publish_pypi
    assert "exactly one wheel and one source archive" in publish_pypi
    assert "PUBLISH_PYPI" not in justfile


def test_release_prepare_keeps_dmw_result_messages() -> None:
    """The split preparation command should retain the concise handoff."""
    recipe = _just_recipe("release-prepare")

    assert 'echo "Prepared $tag locally; nothing was uploaded."' in recipe
    assert 'echo "Review the commit and tag, then run:"' in recipe
    assert 'echo "  just release-push $tag"' in recipe
    assert (
        'echo "GitHub will rerun CI and create the GitHub Release."' in recipe
    )
