"""Tests for conservative generated-entity source alignment."""

from __future__ import annotations

import pytest

from dmw_experiments.shared.analysis import EntityMention, EntitySpanResolver


def _mention(
    value: str, *, mention_id: str = "M1", entity_type: str = "Person"
) -> EntityMention:
    return EntityMention(
        mention_id=mention_id,
        entity_type=entity_type,
        value=value,
    )


@pytest.mark.parametrize(
    ("text", "value", "method", "source"),
    (
        ("Albertus marchio", "Albertus", "exact", "Albertus"),
        ("s.\u00a0Gumperti", "s. Gumperti", "normalized", "s.\u00a0Gumperti"),
        ("MAGUNTIA", "Maguntia", "casefolded", "MAGUNTIA"),
        ("Cafe\u0301", "Café", "normalized", "Cafe\u0301"),
        (
            "Johannes de Lapide",
            "Johanes de Lapide",
            "fuzzy",
            "Johannes de Lapide",
        ),
    ),
)
def test_resolver_retains_original_offsets(
    text: str,
    value: str,
    method: str,
    source: str,
) -> None:
    """Every accepted match round-trips to the untouched source substring."""
    result = EntitySpanResolver().resolve(text, [_mention(value)])[0]

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.method == method
    assert result.selected.source_text == source
    assert (
        text[result.selected.start_offset : result.selected.end_offset]
        == source
    )


def test_repeated_mentions_resolve_only_with_equal_multiplicity() -> None:
    """Equal repeated records map left-to-right; surplus text stays ambiguous."""
    resolver = EntitySpanResolver()
    mentions = [
        _mention("Maguntia", mention_id="M1"),
        _mention("Maguntia", mention_id="M2"),
    ]

    resolved = resolver.resolve("Maguntia et Maguntia", mentions)
    ambiguous = resolver.resolve("Maguntia et Maguntia et Maguntia", mentions)

    assert [item.status for item in resolved] == ["resolved", "resolved"]
    assert [
        item.selected.start_offset for item in resolved if item.selected
    ] == [
        0,
        12,
    ]
    assert {item.status for item in ambiguous} == {"ambiguous"}
    assert all(item.selected is None for item in ambiguous)


def test_different_types_may_share_the_same_span() -> None:
    """Multi-label annotations do not compete for a source occurrence."""
    results = EntitySpanResolver().resolve(
        "Maguntia",
        [
            _mention("Maguntia", mention_id="M1", entity_type="Ort"),
            _mention("Maguntia", mention_id="M2", entity_type="Diözese"),
        ],
    )

    assert {item.status for item in results} == {"resolved"}
    assert {
        (item.selected.start_offset, item.selected.end_offset)
        for item in results
        if item.selected
    } == {(0, 8)}


def test_short_values_are_never_fuzzy_matched() -> None:
    """Small abbreviations require deterministic evidence."""
    result = EntitySpanResolver().resolve("eccl", [_mention("ecll")])[0]

    assert result.status == "unmatched"
    assert result.selected is None
    assert result.candidates == ()


def test_short_fuzzy_threshold_uses_generated_value_length() -> None:
    """A seven-character value cannot inherit a longer candidate's threshold."""
    result = EntitySpanResolver().resolve("Johannes", [_mention("Johanes")])[0]

    assert result.status == "unmatched"
    assert result.selected is None
    assert result.candidates[0].score < 96


def test_close_fuzzy_runner_up_remains_ambiguous() -> None:
    """An otherwise strong fuzzy score cannot hide two plausible locations."""
    result = EntitySpanResolver().resolve(
        "Johannes de Lapide; Johanes de Lapide",
        [_mention("Johannes de Lapidae")],
    )[0]

    assert result.status == "ambiguous"
    assert result.selected is None
    assert len(result.candidates) >= 2


def test_unmatched_value_retains_ranked_audit_candidates() -> None:
    """A rejected fuzzy guess remains visible without becoming a highlight."""
    result = EntitySpanResolver().resolve(
        "Albertus marchio Brandenburgensis",
        [_mention("Completely unrelated institution")],
    )[0]

    assert result.status == "unmatched"
    assert result.selected is None
    assert len(result.candidates) <= EntitySpanResolver.MAX_CANDIDATES
