"""Resolve generated entity values against their original source text."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

EntitySpanStatus = Literal["resolved", "ambiguous", "unmatched"]
EntitySpanMatchMethod = Literal[
    "exact",
    "normalized",
    "casefolded",
    "fuzzy",
]


@dataclass(frozen=True, slots=True)
class EntityMention:
    """Describe one generated annotation without assuming source offsets.

    :param mention_id: Stable identifier supplied by the calling pipeline.
    :param entity_type: Generated semantic category.
    :param value: Generated surface form that should occur in the source.
    """

    mention_id: str
    entity_type: str
    value: str


@dataclass(frozen=True, slots=True)
class EntitySpanCandidate:
    """Describe one possible source location for an entity annotation.

    :param candidate_id: Mention-local identifier used during review.
    :param start_offset: Inclusive character offset in the original text.
    :param end_offset: Exclusive character offset in the original text.
    :param source_text: Exact original substring at the offsets.
    :param method: Comparison that produced this candidate.
    :param score: Similarity percentage from zero through 100.
    :param context: Short original-text excerpt around the candidate.
    """

    candidate_id: str
    start_offset: int
    end_offset: int
    source_text: str
    method: EntitySpanMatchMethod
    score: float
    context: str


@dataclass(frozen=True, slots=True)
class ResolvedEntityMention:
    """Report the auditable location result for one generated annotation.

    :param mention: Original annotation record.
    :param status: Automatic decision: resolved, ambiguous, or unmatched.
    :param selected: Accepted location, or ``None`` when human review is
        required.
    :param candidates: Up to five ranked locations retained for audit.
    """

    mention: EntityMention
    status: EntitySpanStatus
    selected: EntitySpanCandidate | None
    candidates: tuple[EntitySpanCandidate, ...]


@dataclass(frozen=True, slots=True)
class _NormalizedText:
    """Keep normalized characters tied to their original source offsets.

    :param value: Normalized text used for comparison.
    :param source_starts: Inclusive original offset for each character.
    :param source_ends: Exclusive original offset for each character.
    """

    value: str
    source_starts: tuple[int, ...]
    source_ends: tuple[int, ...]


class EntitySpanResolver:
    """Infer conservative source offsets for generated entity surface forms.

    Exact and normalization-only matches are preferred. Fuzzy matching is
    limited to token-boundary windows and accepted only when the best result
    clears both a length-aware score threshold and a runner-up margin. This
    makes automatic highlighting useful without hiding uncertainty from a
    reviewer.
    """

    VERSION = "1"
    MAX_CANDIDATES = 5
    FUZZY_MINIMUM_LENGTH = 5
    FUZZY_SHORT_MAXIMUM_LENGTH = 7
    FUZZY_SHORT_MINIMUM_SCORE = 96.0
    FUZZY_LONG_MINIMUM_SCORE = 90.0
    FUZZY_RUNNER_UP_MARGIN = 8.0

    def resolve(
        self,
        text: str,
        mentions: list[EntityMention] | tuple[EntityMention, ...],
    ) -> tuple[ResolvedEntityMention, ...]:
        """Locate annotations within one declared source segment.

        Repeated identical records are assigned left-to-right only when their
        number equals the number of matching source occurrences. Different
        types are grouped separately, so multiple labels may share one span.

        :param text: Original header or sublemma text.
        :param mentions: Generated annotations declared for this segment.
        :return: Results in the same order as ``mentions``.
        """
        grouped: dict[tuple[str, str], list[EntityMention]] = defaultdict(list)
        for mention in mentions:
            grouped[(mention.entity_type, mention.value)].append(mention)

        by_id: dict[str, ResolvedEntityMention] = {}
        for group in grouped.values():
            for result in self._resolve_identical_group(text, group):
                by_id[result.mention.mention_id] = result
        return tuple(by_id[mention.mention_id] for mention in mentions)

    def _resolve_identical_group(
        self,
        text: str,
        mentions: list[EntityMention],
    ) -> tuple[ResolvedEntityMention, ...]:
        """Resolve annotations that have the same type and surface form.

        :param text: Original source segment.
        :param mentions: Same-type, same-value annotations in source order.
        :return: One conservative location result per annotation.
        """
        value = mentions[0].value
        candidates = self._deterministic_candidates(text, value)
        if candidates:
            return self._resolve_by_multiplicity(mentions, candidates)

        fuzzy_candidates = self._fuzzy_candidates(text, value)
        if len(mentions) != 1:
            status: EntitySpanStatus = (
                "ambiguous"
                if self._fuzzy_is_plausible(fuzzy_candidates, value=value)
                else "unmatched"
            )
            return tuple(
                ResolvedEntityMention(
                    mention=mention,
                    status=status,
                    selected=None,
                    candidates=fuzzy_candidates,
                )
                for mention in mentions
            )

        selected = self._accepted_fuzzy_candidate(fuzzy_candidates, value=value)
        if selected is not None:
            return (
                ResolvedEntityMention(
                    mention=mentions[0],
                    status="resolved",
                    selected=selected,
                    candidates=fuzzy_candidates,
                ),
            )
        status = (
            "ambiguous"
            if self._fuzzy_is_plausible(fuzzy_candidates, value=value)
            else "unmatched"
        )
        return (
            ResolvedEntityMention(
                mention=mentions[0],
                status=status,
                selected=None,
                candidates=fuzzy_candidates,
            ),
        )

    def _resolve_by_multiplicity(
        self,
        mentions: list[EntityMention],
        candidates: tuple[EntitySpanCandidate, ...],
    ) -> tuple[ResolvedEntityMention, ...]:
        """Assign deterministic occurrences only when multiplicities agree.

        :param mentions: Identical annotation records.
        :param candidates: Deterministic source occurrences.
        :return: Left-to-right results or ambiguous results for every record.
        """
        if len(mentions) == len(candidates):
            ordered = sorted(candidates, key=lambda item: item.start_offset)
            return tuple(
                ResolvedEntityMention(
                    mention=mention,
                    status="resolved",
                    selected=candidate,
                    candidates=candidates,
                )
                for mention, candidate in zip(mentions, ordered, strict=True)
            )
        return tuple(
            ResolvedEntityMention(
                mention=mention,
                status="ambiguous",
                selected=None,
                candidates=candidates[: self.MAX_CANDIDATES],
            )
            for mention in mentions
        )

    def _deterministic_candidates(
        self, text: str, value: str
    ) -> tuple[EntitySpanCandidate, ...]:
        """Use the first exact or normalization-only comparison with matches.

        :param text: Original source segment.
        :param value: Generated entity surface form.
        :return: All occurrences from the strongest successful comparison.
        """
        methods: tuple[tuple[EntitySpanMatchMethod, bool, bool], ...] = (
            ("exact", False, False),
            ("normalized", True, False),
            ("casefolded", True, True),
        )
        for method, normalize, casefold in methods:
            offsets = (
                self._normalized_occurrences(text, value, casefold=casefold)
                if normalize
                else self._exact_occurrences(text, value)
            )
            if offsets:
                return self._make_candidates(
                    text=text,
                    offsets=offsets,
                    method=method,
                    scores=None,
                )
        return ()

    @staticmethod
    def _exact_occurrences(
        text: str, value: str
    ) -> tuple[tuple[int, int], ...]:
        """Find all literal occurrences, including overlaps.

        :param text: Original source segment.
        :param value: Literal generated value.
        :return: Inclusive-start and exclusive-end offset pairs.
        """
        if not value:
            return ()
        offsets: list[tuple[int, int]] = []
        start = 0
        while (position := text.find(value, start)) >= 0:
            offsets.append((position, position + len(value)))
            start = position + 1
        return tuple(offsets)

    def _normalized_occurrences(
        self, text: str, value: str, *, casefold: bool
    ) -> tuple[tuple[int, int], ...]:
        """Find normalized values while retaining original source offsets.

        :param text: Original source segment.
        :param value: Generated value normalized by the same rule.
        :param casefold: Whether comparison ignores Unicode case distinctions.
        :return: Unique original-source offset pairs.
        """
        source = self._normalize_with_offsets(text, casefold=casefold)
        target = self._normalize(value, casefold=casefold)
        if not target:
            return ()
        offsets: list[tuple[int, int]] = []
        start = 0
        while (position := source.value.find(target, start)) >= 0:
            end_position = position + len(target) - 1
            offsets.append(
                (
                    source.source_starts[position],
                    source.source_ends[end_position],
                )
            )
            start = position + 1
        return tuple(dict.fromkeys(offsets))

    def _fuzzy_candidates(
        self, text: str, value: str
    ) -> tuple[EntitySpanCandidate, ...]:
        """Rank token-boundary windows without making an acceptance decision.

        :param text: Original source segment.
        :param value: Generated value that had no deterministic occurrence.
        :return: Up to five highest-scoring audit candidates.
        """
        target = self._normalize(value, casefold=True)
        target_length = len(target.replace(" ", ""))
        if target_length < self.FUZZY_MINIMUM_LENGTH:
            return ()
        tokens = tuple(re.finditer(r"\S+", text))
        if not tokens:
            return ()
        target_token_count = max(1, len(target.split()))
        lengths = range(
            max(1, target_token_count - 2),
            min(len(tokens), target_token_count + 2) + 1,
        )
        scored: list[tuple[float, int, int]] = []
        for start_index in range(len(tokens)):
            for token_count in lengths:
                end_index = start_index + token_count - 1
                if end_index >= len(tokens):
                    continue
                start_offset = tokens[start_index].start()
                end_offset = tokens[end_index].end()
                candidate = self._normalize(
                    text[start_offset:end_offset], casefold=True
                )
                length_delta = abs(len(candidate) - len(target))
                if length_delta > max(4, round(len(target) * 0.4)):
                    continue
                scored.append(
                    (
                        float(fuzz.ratio(target, candidate)),
                        start_offset,
                        end_offset,
                    )
                )
        best_by_offsets = {
            (start_offset, end_offset): score
            for score, start_offset, end_offset in scored
        }
        ranked = sorted(
            (
                (score, start_offset, end_offset)
                for (start_offset, end_offset), score in best_by_offsets.items()
            ),
            key=lambda item: (-item[0], item[1], item[2]),
        )[: self.MAX_CANDIDATES]
        return self._make_candidates(
            text=text,
            offsets=tuple((start, end) for _, start, end in ranked),
            method="fuzzy",
            scores=tuple(score for score, _, _ in ranked),
        )

    def _accepted_fuzzy_candidate(
        self,
        candidates: tuple[EntitySpanCandidate, ...],
        *,
        value: str,
    ) -> EntitySpanCandidate | None:
        """Accept one candidate only above the score and margin thresholds.

        :param candidates: Ranked fuzzy candidates.
        :param value: Generated value used to select the length-aware floor.
        :return: Accepted best candidate, or ``None`` when review is required.
        """
        if not candidates:
            return None
        best = candidates[0]
        threshold = self._fuzzy_threshold(value)
        runner_up_score = candidates[1].score if len(candidates) > 1 else 0.0
        if (
            best.score >= threshold
            and best.score - runner_up_score >= self.FUZZY_RUNNER_UP_MARGIN
        ):
            return best
        return None

    def _fuzzy_is_plausible(
        self,
        candidates: tuple[EntitySpanCandidate, ...],
        *,
        value: str,
    ) -> bool:
        """Distinguish ambiguous strong candidates from weak unmatched guesses.

        :param candidates: Ranked fuzzy candidates.
        :param value: Generated value used to select the score floor.
        :return: Whether the best score reaches that floor.
        """
        if not candidates:
            return False
        return candidates[0].score >= self._fuzzy_threshold(value)

    def _fuzzy_threshold(self, value: str) -> float:
        """Select the score floor from the generated value length.

        :param value: Generated surface form being aligned.
        :return: Minimum accepted RapidFuzz score.
        """
        normalized_length = len(
            self._normalize(value, casefold=True).replace(" ", "")
        )
        return (
            self.FUZZY_SHORT_MINIMUM_SCORE
            if normalized_length <= self.FUZZY_SHORT_MAXIMUM_LENGTH
            else self.FUZZY_LONG_MINIMUM_SCORE
        )

    @classmethod
    def _make_candidates(
        cls,
        *,
        text: str,
        offsets: tuple[tuple[int, int], ...],
        method: EntitySpanMatchMethod,
        scores: tuple[float, ...] | None,
    ) -> tuple[EntitySpanCandidate, ...]:
        """Attach source substrings, contexts, scores, and candidate IDs.

        :param text: Original source segment.
        :param offsets: Candidate start and end pairs.
        :param method: Comparison that produced the offsets.
        :param scores: Fuzzy scores, or ``None`` for deterministic matches.
        :return: Complete candidate records in supplied order.
        """
        candidates = []
        for index, (start, end) in enumerate(offsets, start=1):
            context_start = max(0, start - 30)
            context_end = min(len(text), end + 30)
            context = text[context_start:context_end]
            if context_start:
                context = f"…{context}"
            if context_end < len(text):
                context = f"{context}…"
            candidates.append(
                EntitySpanCandidate(
                    candidate_id=f"C{index}",
                    start_offset=start,
                    end_offset=end,
                    source_text=text[start:end],
                    method=method,
                    score=(scores[index - 1] if scores is not None else 100.0),
                    context=context,
                )
            )
        return tuple(candidates)

    @staticmethod
    def _normalize(value: str, *, casefold: bool) -> str:
        """Apply the comparison normalization without offset tracking.

        :param value: Source or generated text.
        :param casefold: Whether to apply Unicode case folding.
        :return: NFKC text with collapsed whitespace.
        """
        normalized = unicodedata.normalize("NFKC", value)
        if casefold:
            normalized = normalized.casefold()
        return " ".join(normalized.split())

    @staticmethod
    def _normalize_with_offsets(
        value: str, *, casefold: bool
    ) -> _NormalizedText:
        """Apply comparison normalization with original offset boundaries.

        :param value: Original source text.
        :param casefold: Whether to apply Unicode case folding.
        :return: Normalized characters and their source spans.
        """
        characters: list[str] = []
        source_starts: list[int] = []
        source_ends: list[int] = []
        whitespace_pending = False
        whitespace_start = 0
        whitespace_end = 0
        for start, end, source_cluster in _normalization_clusters(value):
            normalized = unicodedata.normalize("NFKC", source_cluster)
            if casefold:
                normalized = normalized.casefold()
            for character in normalized:
                if character.isspace():
                    if characters:
                        if not whitespace_pending:
                            whitespace_start = start
                        whitespace_pending = True
                        whitespace_end = end
                    continue
                if whitespace_pending:
                    characters.append(" ")
                    source_starts.append(whitespace_start)
                    source_ends.append(whitespace_end)
                    whitespace_pending = False
                characters.append(character)
                source_starts.append(start)
                source_ends.append(end)
        return _NormalizedText(
            "".join(characters),
            tuple(source_starts),
            tuple(source_ends),
        )


def _normalization_clusters(value: str) -> tuple[tuple[int, int, str], ...]:
    """Group base characters with combining marks before Unicode NFKC.

    :param value: Original text whose offsets must survive normalization.
    :return: Source start, source end, and normalization-unit triples.
    """
    clusters: list[tuple[int, int, str]] = []
    start = 0
    while start < len(value):
        end = start + 1
        if value[start].isspace():
            while end < len(value) and value[end].isspace():
                end += 1
        else:
            while end < len(value) and unicodedata.combining(value[end]):
                end += 1
        clusters.append((start, end, value[start:end]))
        start = end
    return tuple(clusters)
