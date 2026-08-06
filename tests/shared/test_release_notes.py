from pathlib import Path

import pytest

from dmw_experiments.shared.release_notes import extract_release_notes
from dmw_experiments.shared.release_notes import latest_release_version
from dmw_experiments.shared.release_notes import validate_newer_release
from dmw_experiments.shared.release_notes import write_release_notes


CHANGELOG = """# Changelog

# [Unreleased]

### Added

# 0.2.0 - 2026-08-06

- Second release.

# 0.1.0 - 2026-08-01

- First release.
"""


def test_extract_release_notes_stops_at_the_next_release() -> None:
    assert extract_release_notes(CHANGELOG, "0.2.0") == (
        "# 0.2.0 - 2026-08-06\n\n- Second release.\n"
    )


def test_extract_release_notes_requires_one_version_heading() -> None:
    with pytest.raises(ValueError, match="Expected one CHANGELOG.md section"):
        extract_release_notes(CHANGELOG, "9.9.9")


def test_latest_release_version_returns_first_versioned_section() -> None:
    assert latest_release_version(CHANGELOG) == "0.2.0"


def test_validate_newer_release_rejects_a_non_advance() -> None:
    with pytest.raises(ValueError, match="must be newer"):
        validate_newer_release("0.2.0", "0.2.0")


def test_write_release_notes_creates_the_artifact_parent(
    tmp_path: Path,
) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(CHANGELOG, encoding="utf-8")
    output_path = tmp_path / "release" / "notes.md"

    write_release_notes(changelog_path, "0.1.0", output_path)

    assert output_path.read_text(encoding="utf-8") == (
        "# 0.1.0 - 2026-08-01\n\n- First release.\n"
    )
