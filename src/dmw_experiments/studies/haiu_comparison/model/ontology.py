"""Ontology serialization and response projection shared by the study."""

from __future__ import annotations

import re

import haiu

TURTLE_PREFIXES = """
@prefix : <http://hisqu.de/rg_ontology/ontology/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rg: <http://hisqu.de/rg_ontology/ontology/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@base <http://hisqu.de/rg_ontology/ontology/> .
""".strip()

_OUTER_TURTLE_FENCE = re.compile(
    r"\A[\t\r\n ]*```(?:ttl|turtle)[\t ]*\r?\n"
    r"(?P<body>.*?)\r?\n```[\t ]*[\t\r\n ]*\Z",
    flags=re.IGNORECASE | re.DOTALL,
)


def strip_outer_turtle_fence(turtle_response: str) -> tuple[str, bool]:
    """Remove one recognized outer Markdown fence from a Turtle response.

    The operation changes no text inside the fence and accepts only a complete
    document wrapper whose opening and closing fences occupy their own lines.
    Partial fences, embedded examples, and every non-Turtle response remain
    byte-for-byte unchanged.

    :param turtle_response: Exact Stage-2 provider text.
    :return: Turtle projection and whether one outer wrapper was removed.
    """
    match = _OUTER_TURTLE_FENCE.fullmatch(turtle_response)
    if match is None:
        return turtle_response, False
    return match.group("body"), True


def turtle_syntax_fields(
    turtle_text: str,
    *,
    prefix: str = "turtle",
) -> dict[str, bool | int | str | None]:
    """Parse a generated Turtle projection and return syntax diagnostics.

    DMW stores TBox and ABox without the prompt's prefix declarations. The
    shared prompt prefix block is therefore prepended when the output has no
    declarations of its own. One complete outer Turtle Markdown wrapper is
    removed before parsing, while the caller retains the exact provider text.

    :param turtle_text: Generated Turtle document or joined TBox/ABox fragments.
    :param prefix: Metric field prefix.
    :return: Syntax status, parsed triple count, and compact parser error.
    """
    turtle_projection, fence_removed = strip_outer_turtle_fence(turtle_text)
    cleaned = turtle_projection.strip()
    if not cleaned:
        return {
            f"{prefix}_syntax_valid": None,
            f"{prefix}_triple_count": None,
            f"{prefix}_syntax_error": None,
            f"{prefix}_outer_fence_removed": fence_removed,
        }
    parse_input = (
        cleaned
        if "@prefix" in cleaned
        else "\n\n".join((TURTLE_PREFIXES, cleaned))
    )
    try:
        graph = haiu.parse_rdf_data(parse_input, format="turtle", log=False)
    except RuntimeError as exc:
        return {
            f"{prefix}_syntax_valid": False,
            f"{prefix}_triple_count": None,
            f"{prefix}_syntax_error": " ".join(str(exc).split()),
            f"{prefix}_outer_fence_removed": fence_removed,
        }
    return {
        f"{prefix}_syntax_valid": True,
        f"{prefix}_triple_count": len(graph),
        f"{prefix}_syntax_error": None,
        f"{prefix}_outer_fence_removed": fence_removed,
    }
