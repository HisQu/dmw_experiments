"""Shared data containers for comparison experiment outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenMeasurement:
    """Token count plus provenance.

    :param tokens: Token count.
    :param source: Provenance label, usually ``provider`` or ``estimated``.
    """

    tokens: int
    source: str

    def as_dict(self, prefix: str) -> dict[str, int | str]:
        """Return a flattened representation for result rows.

        :param prefix: Field-name prefix.
        :return: Two flattened token fields.
        """
        return {
            f"{prefix}_tokens": self.tokens,
            f"{prefix}_tokens_source": self.source,
        }


@dataclass(slots=True)
class ExperimentResult:
    """Normalized result for one condition and regest.

    :param condition: Stable condition name.
    :param regest_id: Datamodel regest identifier.
    :param success: Whether the condition finished successfully.
    :param payload: JSON-friendly normalized payload.
    """

    condition: str
    regest_id: str
    success: bool
    payload: dict[str, Any] = field(default_factory=dict)
