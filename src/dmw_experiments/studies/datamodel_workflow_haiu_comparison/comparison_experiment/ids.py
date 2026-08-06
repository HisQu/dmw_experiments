"""Input ID parsing for the datamodel workflow comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HEADER_VALUES = frozenset({"id_RG_all", "regest_id", "id", "dmw_id"})


@dataclass(frozen=True, slots=True)
class ParsedRegestId:
    """One normalized input identifier with source-file context.

    :param line_no: One-based source line number.
    :param raw_id: Identifier text exactly as it appeared after trimming.
    :param regest_id: Numeric datamodel-workflow identifier.
    """

    line_no: int
    raw_id: str
    regest_id: str

    def as_dict(self) -> dict[str, int | str]:
        """Return a JSON-friendly representation.

        :return: Source and normalized identifier fields.
        """
        return {
            "line_no": self.line_no,
            "raw_id": self.raw_id,
            "regest_id": self.regest_id,
        }


def parse_regest_ids(path: Path, *, keep_duplicates: bool = False) -> list[str]:
    """Parse regest IDs from a one-column text file.

    RG-all identifiers such as ``11010116-1`` are normalized to the numeric
    datamodel-workflow ID ``11010116``.

    :param path: UTF-8 text file containing one identifier per line.
    :param keep_duplicates: Preserve repeated normalized identifiers when true.
    :return: Ordered datamodel-workflow identifiers, optionally deduplicated.
    :raises FileNotFoundError: If ``path`` does not exist.
    :raises ValueError: If an identifier cannot be mapped to DMW's numeric ID.
    """
    return [
        entry.regest_id
        for entry in parse_regest_id_entries(
            path, keep_duplicates=keep_duplicates
        )
    ]


def parse_regest_id_entries(
    path: Path, *, keep_duplicates: bool = False
) -> list[ParsedRegestId]:
    """Parse one-column input into normalized identifiers with provenance.

    RG-all identifiers such as ``11010116-1`` are normalized to the numeric
    datamodel-workflow ID ``11010116``.

    :param path: UTF-8 text file containing one identifier per line.
    :param keep_duplicates: Preserve repeated normalized identifiers when true.
    :return: Ordered parsed identifiers, optionally deduplicated.
    :raises FileNotFoundError: If ``path`` does not exist.
    :raises ValueError: If an identifier cannot be mapped to DMW's numeric ID.
    """
    entries: list[ParsedRegestId] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line in HEADER_VALUES:
                continue
            regest_id = normalize_regest_id(line, line_no=line_no)
            if keep_duplicates or regest_id not in seen:
                entries.append(
                    ParsedRegestId(
                        line_no=line_no,
                        raw_id=line,
                        regest_id=regest_id,
                    )
                )
                seen.add(regest_id)
    return entries


def normalize_regest_id(value: str, *, line_no: int | None = None) -> str:
    """Map local RG-all style identifiers to datamodel-workflow IDs.

    :param value: Raw identifier from the input file.
    :param line_no: Optional source line number for error messages.
    :return: Numeric datamodel-workflow regest identifier.
    :raises ValueError: If the value is not numeric or RG-all hyphen style.
    """
    raw_value = value.strip()
    if raw_value.isdigit():
        return raw_value
    if "-" in raw_value:
        stem, suffix = [
            part.strip() for part in raw_value.split("-", maxsplit=1)
        ]
        if stem.isdigit() and suffix.isdigit() and len(suffix) < len(stem):
            return stem
    location = f" at line {line_no}" if line_no is not None else ""
    raise ValueError(
        f"Invalid regest id '{raw_value}'{location}. Expected a DMW numeric "
        "id like 11010116 or an RG-all id like 11010116-1."
    )


def limited_ids(ids: list[str], limit: int) -> list[str]:
    """Apply the experiment limit convention.

    :param ids: Parsed identifiers.
    :param limit: Maximum number to keep. ``0`` means all IDs.
    :return: Limited identifier list.
    """
    if limit < 0:
        raise ValueError("--limit must be >= 0")
    if limit == 0:
        return ids
    return ids[:limit]
