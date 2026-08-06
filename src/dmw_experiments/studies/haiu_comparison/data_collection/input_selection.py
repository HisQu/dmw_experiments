"""Availability preflight for datamodel-workflow regest IDs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.client import (
    RegestNotFoundError,
)

MissingIdPolicy = Literal["skip", "fail"]


class InputCandidate(Protocol):
    """Identifier metadata shared by legacy IDs and pair catalogue units."""

    @property
    def raw_id(self) -> str:
        """Return the identifier as supplied by its input source.

        :return: Unmodified source identifier.
        """
        ...

    @property
    def regest_id(self) -> str:
        """Return the identifier submitted to DMW.

        :return: DMW lookup identifier.
        """
        ...

    def as_dict(self) -> dict[str, Any]:
        """Return portable selection metadata.

        :return: JSON-compatible identifier evidence.
        """
        ...


class RegestPayloadClient(Protocol):
    """Minimal client contract needed for ID availability checks."""

    def get_regest_payload(self, regest_id: str) -> dict[str, Any]:
        """Fetch one regest payload.

        :param regest_id: Datamodel regest identifier.
        :return: API response payload.
        """
        ...


@dataclass(frozen=True, slots=True)
class SkippedRegestId:
    """A candidate that cannot be used for comparable experiment conditions.

    :param candidate: Source identifier metadata.
    :param reason: Human-readable skip reason.
    """

    candidate: InputCandidate
    reason: str

    def as_dict(self) -> dict[str, int | str]:
        """Return a JSON-friendly representation.

        :return: Source, normalized identifier, and reason fields.
        """
        return {**self.candidate.as_dict(), "reason": self.reason}


@dataclass(frozen=True, slots=True)
class IDSelection:
    """Validated ID set for one experiment run.

    :param candidates: Parsed input candidates.
    :param available: Candidates present in datamodel-workflow.
    :param selected: Available candidates selected for this run.
    :param skipped: Candidates missing from datamodel-workflow.
    :param limit: Requested runnable-ID limit. ``0`` means all available IDs.
    :param missing_id_policy: Policy used for missing candidates.
    """

    candidates: tuple[InputCandidate, ...]
    available: tuple[InputCandidate, ...]
    selected: tuple[InputCandidate, ...]
    skipped: tuple[SkippedRegestId, ...]
    limit: int
    missing_id_policy: MissingIdPolicy

    @property
    def selected_ids(self) -> list[str]:
        """Return selected datamodel-workflow IDs.

        :return: Selected normalized identifiers in run order.
        """
        return [entry.regest_id for entry in self.selected]

    def as_dict(self, *, source_file: Path) -> dict[str, Any]:
        """Return a JSON-friendly report.

        :param source_file: Input file used for this selection.
        :return: Selection metadata and candidate lists.
        """
        return {
            "source_file": (
                source_file.name
                if source_file.is_absolute()
                else source_file.as_posix()
            ),
            "limit": self.limit,
            "missing_id_policy": self.missing_id_policy,
            "total_candidates": len(self.candidates),
            "available_count": len(self.available),
            "selected_count": len(self.selected),
            "skipped_count": len(self.skipped),
            "available_unselected_count": (
                len(self.available) - len(self.selected)
            ),
            "selected_ids": self.selected_ids,
            "selected": [entry.as_dict() for entry in self.selected],
            "skipped": [entry.as_dict() for entry in self.skipped],
        }


class MissingRegestIdsError(RuntimeError):
    """Raised when fail-fast policy sees unavailable input IDs.

    :param selection: Completed ID preflight result.
    """

    def __init__(self, selection: IDSelection) -> None:
        self.selection = selection
        super().__init__(format_missing_ids(selection))


def resolve_available_regest_ids(
    *,
    client: RegestPayloadClient,
    candidates: Sequence[InputCandidate],
    limit: int,
    missing_id_policy: MissingIdPolicy,
) -> IDSelection:
    """Validate candidates against datamodel-workflow and select run IDs.

    Missing 404s are recorded. Non-404 datamodel errors are intentionally not
    swallowed, because they indicate an experiment environment problem.

    :param client: Authenticated datamodel-workflow client.
    :param candidates: Parsed input identifiers.
    :param limit: Maximum runnable IDs to select. ``0`` means all available.
    :param missing_id_policy: Whether missing IDs are skipped or fail the run.
    :return: Completed ID selection.
    :raises ValueError: If ``limit`` or ``missing_id_policy`` is invalid.
    :raises MissingRegestIdsError: If policy is ``fail`` and IDs are missing.
    """
    if limit < 0:
        raise ValueError("--limit must be >= 0")
    if missing_id_policy not in ("skip", "fail"):
        raise ValueError("--missing-id-policy must be 'skip' or 'fail'")

    available: list[InputCandidate] = []
    skipped: list[SkippedRegestId] = []
    for candidate in candidates:
        try:
            client.get_regest_payload(candidate.regest_id)
        except RegestNotFoundError as exc:
            skipped.append(
                SkippedRegestId(candidate=candidate, reason=str(exc))
            )
            continue
        available.append(candidate)

    selected = available if limit == 0 else available[:limit]
    selection = IDSelection(
        candidates=tuple(candidates),
        available=tuple(available),
        selected=tuple(selected),
        skipped=tuple(skipped),
        limit=limit,
        missing_id_policy=missing_id_policy,
    )
    if missing_id_policy == "fail" and skipped:
        raise MissingRegestIdsError(selection)
    return selection


def format_missing_ids(selection: IDSelection) -> str:
    """Format missing IDs for console output.

    :param selection: Completed ID preflight result.
    :return: Compact human-readable report.
    """
    missing = ", ".join(
        f"{item.candidate.raw_id}->{item.candidate.regest_id}"
        for item in selection.skipped[:10]
    )
    suffix = ""
    if len(selection.skipped) > 10:
        suffix = f", ... ({len(selection.skipped)} total)"
    return (
        "Missing datamodel-workflow regest IDs: "
        f"{missing}{suffix}. Use --missing-id-policy skip to continue."
    )
