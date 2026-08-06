"""Extract one version section from the project changelog."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


RELEASE_HEADING = re.compile(
    r"^# (?P<version>\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$",
    re.MULTILINE,
)


def latest_release_version(changelog: str) -> str:
    """Return the first versioned section below ``[Unreleased]``.

    :param changelog: Complete changelog text.
    :return: Most recent documented release version.
    :raises ValueError: If no release heading exists.
    """
    match = RELEASE_HEADING.search(changelog)
    if match is None:
        raise ValueError("CHANGELOG.md does not contain a release section.")
    return match.group("version")


def validate_newer_release(current_version: str, prepared_version: str) -> None:
    """Reject a prepared changelog version that does not advance the project.

    :param current_version: Version currently declared by the project.
    :param prepared_version: First release section in the changelog.
    :raises ValueError: If the prepared version is not newer.
    """
    current = tuple(int(part) for part in current_version.split("."))
    prepared = tuple(int(part) for part in prepared_version.split("."))
    if prepared <= current:
        raise ValueError(
            f"Prepared changelog version {prepared_version} must be newer than "
            f"project version {current_version}."
        )


def extract_release_notes(changelog: str, version: str) -> str:
    """Return the complete changelog section for one release.

    The release workflow uses the same checked-in text that maintainers and
    reviewers read. This prevents a tag from acquiring release notes that
    disagree with ``CHANGELOG.md``.

    :param changelog: Complete changelog text.
    :param version: Release version without the leading ``v``.
    :return: Version heading and content, terminated by one newline.
    :raises ValueError: If the changelog does not contain exactly one matching
        version heading.
    """
    matches = [
        match
        for match in RELEASE_HEADING.finditer(changelog)
        if match.group("version") == version
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one CHANGELOG.md section for {version}, found "
            f"{len(matches)}."
        )

    start = matches[0].start()
    next_heading = RELEASE_HEADING.search(changelog, matches[0].end())
    end = len(changelog) if next_heading is None else next_heading.start()
    return f"{changelog[start:end].strip()}\n"


def write_release_notes(
    changelog_path: Path,
    version: str,
    output_path: Path,
) -> None:
    """Write one changelog release section to a workflow artifact.

    :param changelog_path: Project changelog to read.
    :param version: Release version without the leading ``v``.
    :param output_path: Destination used by the GitHub Release workflow.
    """
    notes = extract_release_notes(
        changelog_path.read_text(encoding="utf-8"),
        version,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(notes, encoding="utf-8")


def main() -> None:
    """Extract release notes for the command-line release gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version without a leading v.")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Changelog source. Defaults to CHANGELOG.md.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_release_notes(args.changelog, args.version, args.output)


if __name__ == "__main__":
    main()
