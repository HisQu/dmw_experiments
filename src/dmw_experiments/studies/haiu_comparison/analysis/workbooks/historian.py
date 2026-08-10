"""Historian-facing workbook rendering for blinded ontology review."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import xlsxwriter
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from haiu.rdf.fmt_utils import frag_uri
from dmw_experiments.studies.haiu_comparison.analysis.workbooks.results import (
    CONDITIONS,
    CONDITION_EXPLANATIONS,
    HISTORIAN_REVIEW_COMPARISON_CONDITIONS,
    HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER,
    HISTORIAN_REVIEW_FALSE_ASSIGNMENT_GUIDANCE,
    HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER,
    HISTORIAN_REVIEW_FROZEN_COLUMN_COUNT,
    HISTORIAN_REVIEW_GENERATED_NAME_PROPERTY,
    HISTORIAN_REVIEW_GRADE_DEFINITIONS,
    HISTORIAN_REVIEW_GRADING_CORE_RULE,
    HISTORIAN_REVIEW_HEADERS,
    HISTORIAN_REVIEW_HEADER_ROW,
    HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS,
    HISTORIAN_REVIEW_RESOURCE_HEADERS,
    _FrozenReferenceOntology,
    _HistorianReviewPacket,
    _HistorianReviewSource,
    _ReviewRelationship,
    _STANDARD_RDF_NAMESPACES,
    _SourceOrderedGraph,
    _formats,
    _load_json,
    _reference_ontology_catalogue_guidance,
    _sha256_file,
)


def _write_historian_quality_review_workbook(
    *,
    path: Path,
    observations: list[dict[str, Any]],
    run_manifest: dict[str, Any],
    run_dir: Path,
    partial: bool,
    reference_ontology: _FrozenReferenceOntology,
) -> tuple[list[list[_HistorianReviewPacket]], dict[str, dict[str, str]]]:
    """Write a condition-masked, non-Turtle ontology review worksheet.

    :param path: Workbook destination in the derived analysis directory.
    :param observations: Normalized authoritative result rows.
    :param run_manifest: Experiment manifest used for deterministic masking.
    :param run_dir: Run root that owns exact Turtle and regest sidecars.
    :param partial: Whether the run is an explicitly diagnostic partial export.
    :param reference_ontology: Frozen ontology supporting reviewer labels.
    :return: Visible review packets and their hidden condition mappings.
    """
    packets, reveal_key = _historian_review_packets(
        observations=observations,
        run_manifest=run_manifest,
        run_dir=run_dir,
        reference_labels=reference_ontology.labels,
    )
    workbook = xlsxwriter.Workbook(path, {"strings_to_urls": False})
    try:
        formats = _formats(workbook)
        sheet: Any = workbook.add_worksheet("Historian_Review")
        _write_historian_review_rows(sheet, packets, formats)
    finally:
        workbook.close()
    return packets, reveal_key


def _historian_review_packets(
    *,
    observations: list[dict[str, Any]],
    run_manifest: dict[str, Any],
    run_dir: Path,
    reference_labels: dict[URIRef, str],
) -> tuple[
    list[list[_HistorianReviewPacket]],
    dict[str, dict[str, str]],
]:
    """Build readable review rows for valid triplets and planned pairs.

    The canonical Turtle sidecars are parsed independently of stored validity
    flags. A regest enters as a complete three-condition group when every
    sidecar parses. Otherwise, it enters as a two-condition group for either
    pre-specified comparison: DMW versus DMW + Haiu RAG, or DMW + Haiu RAG
    versus standalone Haiu RAG. A full-ontology and standalone-Haiu row never
    form a group without DMW + Haiu RAG, because that is not a study contrast.

    :param observations: Normalized authoritative result rows.
    :param run_manifest: Experiment manifest used to seed packet masking.
    :param run_dir: Run root that owns the frozen source artifacts.
    :param reference_labels: Preferred labels from the frozen reference ontology.
    :return: Visible packets plus their hidden condition mapping.
    """
    rows_by_key = {
        (str(row["condition"]), str(row["regest_id"])): row
        for row in observations
    }
    candidate_groups: list[
        tuple[str, list[tuple[dict[str, Any], _SourceOrderedGraph]]]
    ] = []
    regest_ids = sorted({str(row["regest_id"]) for row in observations})
    for regest_id in regest_ids:
        for comparison_conditions in (
            CONDITIONS,
            *HISTORIAN_REVIEW_COMPARISON_CONDITIONS,
        ):
            parsed_rows: list[tuple[dict[str, Any], _SourceOrderedGraph]] = []
            for condition in comparison_conditions:
                row = rows_by_key.get((condition, regest_id))
                if row is None:
                    break
                graph = _canonical_turtle_graph(run_dir=run_dir, row=row)
                if graph is None:
                    break
                parsed_rows.append((row, graph))
            if len(parsed_rows) == len(comparison_conditions):
                candidate_groups.append((regest_id, parsed_rows))
                break
    if not candidate_groups:
        return [], {}

    regest_texts = _frozen_regest_texts(
        run_dir=run_dir,
        run_manifest=run_manifest,
        regest_ids=[regest_id for regest_id, _ in candidate_groups],
    )
    packet_groups: list[list[_HistorianReviewPacket]] = []
    reveal_key: dict[str, dict[str, str]] = {}
    review_index = 1
    for regest_id, parsed_rows in candidate_groups:
        regest_text = regest_texts[regest_id]
        input_lineage = _shared_input_lineage(parsed_rows)
        unmasked_group: list[tuple[_HistorianReviewPacket, dict[str, str]]] = []
        for row, graph in parsed_rows:
            resource_lists = _human_readable_resource_lists(
                graph, reference_labels
            )
            packet = {
                "regest_id": regest_id,
                "regest_text": regest_text,
                **resource_lists,
                "relationships": _human_readable_relationships(
                    graph, reference_labels
                ),
                "grade_1_best_6_worst": "",
                "historian_verdict_and_notes": "",
                HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER: "",
                HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER: "",
            }
            if input_lineage is not None:
                packet.update(
                    {
                        "source_regest_id": input_lineage["source_regest_id"],
                        "source_sublemma_number": input_lineage[
                            "source_sublemma_number"
                        ],
                    }
                )
            hidden = {
                "regest_id": regest_id,
                "condition": str(row["condition"]),
                "raw_ttl_artifact_path": str(row["raw_ttl_artifact_path"]),
            }
            if input_lineage is not None:
                hidden.update(input_lineage)
            unmasked_group.append((packet, hidden))

        random.Random(
            _review_seed(
                run_manifest,
                purpose=f"historian_quality_review:{regest_id}",
            )
        ).shuffle(unmasked_group)
        packet_group: list[_HistorianReviewPacket] = []
        for packet, hidden in unmasked_group:
            review_id = f"R{review_index:04d}"
            review_index += 1
            packet_group.append({"review_id": review_id, **packet})
            reveal_key[review_id] = hidden
        packet_groups.append(packet_group)
    return packet_groups, reveal_key


def _shared_input_lineage(
    parsed_rows: list[tuple[dict[str, Any], _SourceOrderedGraph]],
) -> dict[str, str] | None:
    """Return pair lineage shared by every condition in one review packet.

    :param parsed_rows: Condition observations and their parsed graphs.
    :return: Human-facing source identity, or ``None`` for complete regesta.
    :raises ValueError: If pair rows disagree about their frozen source unit.
    """
    lineages = [row.get("input_lineage") for row, _graph in parsed_rows]
    if all(lineage is None for lineage in lineages):
        return None
    if not all(isinstance(lineage, dict) for lineage in lineages):
        raise ValueError("Historian review pair rows have incomplete lineage.")
    normalized = [
        {
            "source_regest_id": str(lineage.get("source_regest_id") or ""),
            "source_sublemma_number": str(
                lineage.get("source_sublemma_number") or ""
            ),
        }
        for lineage in lineages
        if isinstance(lineage, dict)
    ]
    if (
        any(not all(item.values()) for item in normalized)
        or len({tuple(item.items()) for item in normalized}) != 1
    ):
        raise ValueError("Historian review pair rows disagree about lineage.")
    return normalized[0]


def _review_seed(run_manifest: dict[str, Any], *, purpose: str) -> int:
    """Derive a deterministic random seed for one masked review surface.

    :param run_manifest: Immutable run identity and configuration metadata.
    :param purpose: Distinguishes independent masked workbook orderings.
    :return: Stable pseudo-random seed.
    """
    payload = json.dumps(
        {"purpose": purpose, "run_manifest": run_manifest}, sort_keys=True
    )
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16)


def _canonical_turtle_graph(
    *, run_dir: Path, row: dict[str, Any]
) -> _SourceOrderedGraph | None:
    """Parse one canonical Turtle projection while retaining source order.

    :param run_dir: Root directory of the experiment run.
    :param row: Observation that identifies the canonical Turtle projection.
    :return: Parsed source-ordered graph, or None when the sidecar is absent
        or not valid Turtle.
    """
    relative = row.get("ontology_artifact_path") or row.get(
        "raw_ttl_artifact_path"
    )
    if not isinstance(relative, str):
        return None
    path = run_dir / relative
    if not path.is_file():
        return None
    graph = _SourceOrderedGraph()
    try:
        graph.parse(path, format="turtle")
    except Exception:
        return None
    return graph


def _frozen_regest_texts(
    *,
    run_dir: Path,
    run_manifest: dict[str, Any],
    regest_ids: list[str],
) -> dict[str, str]:
    """Load verified full source text for historian-review regests.

    :param run_dir: Root directory of the experiment run.
    :param run_manifest: Run manifest with raw-regest snapshot metadata.
    :param regest_ids: Complete-triplet identifiers selected for review.
    :return: Full raw regest text keyed by identifier.
    :raises ValueError: If frozen source text is missing, malformed, or changed.
    """
    snapshot = run_manifest.get("raw_regest_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("Run manifest has no frozen raw-regest snapshot.")
    relative = snapshot.get("path")
    expected_hash = snapshot.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError("Frozen raw-regest snapshot metadata is invalid.")
    manifest_path = run_dir / relative
    if (
        not manifest_path.is_file()
        or _sha256_file(manifest_path) != expected_hash
    ):
        raise ValueError("Frozen raw-regest snapshot manifest has changed.")
    snapshot_manifest = _load_json(manifest_path)
    records = snapshot_manifest.get("records")
    if not isinstance(records, dict):
        raise ValueError("Frozen raw-regest snapshot has no record mapping.")

    texts: dict[str, str] = {}
    for regest_id in regest_ids:
        record = records.get(regest_id)
        if not isinstance(record, dict):
            raise ValueError(
                f"Frozen raw-regest snapshot is missing {regest_id}."
            )
        artifact = record.get("path")
        artifact_hash = record.get("sha256")
        if not isinstance(artifact, str) or not isinstance(artifact_hash, str):
            raise ValueError(
                f"Frozen raw-regest record is invalid: {regest_id}."
            )
        artifact_path = run_dir / artifact
        if (
            not artifact_path.is_file()
            or _sha256_file(artifact_path) != artifact_hash
        ):
            raise ValueError(
                f"Frozen raw-regest artifact has changed: {regest_id}."
            )
        payload = _load_json(artifact_path)
        header = payload.get("header")
        subentries = payload.get("subentries")
        if (
            not isinstance(header, str)
            or not isinstance(subentries, list)
            or not all(isinstance(value, str) for value in subentries)
        ):
            raise ValueError(
                f"Frozen raw-regest text is malformed: {regest_id}."
            )
        texts[regest_id] = "\n".join((header, *subentries)).strip()
    return texts


def _human_readable_resource_lists(
    graph: _SourceOrderedGraph,
    reference_labels: dict[URIRef, str],
) -> dict[str, list[str]]:
    """Group generated ontology resources into source-ordered review lists.

    :param graph: Directly parsed canonical Turtle with source-order metadata.
    :param reference_labels: Preferred labels from the frozen reference ontology.
    :return: Source-ordered resource entries keyed by sheet header.
    """
    bnode_labels = _blank_node_labels(graph)
    fallback_display_names = _fallback_resource_display_names(
        graph,
        reference_labels,
    )
    lists = {header: [] for header in HISTORIAN_REVIEW_RESOURCE_HEADERS}
    for subject in graph.subjects_in_source_order:
        category = _resource_category(graph, subject)
        if category is None:
            continue
        display = _human_readable_main_entry(
            graph,
            subject,
            bnode_labels,
            reference_labels,
            fallback_display_names,
        )
        lists[category].append(display)
    return lists


def _resource_category(graph: _SourceOrderedGraph, subject: Any) -> str | None:
    """Classify a Turtle subject for the compact historian review surface.

    :param graph: Parsed ontology graph.
    :param subject: Candidate subject in source order.
    :return: Target worksheet category, or None for the ontology document.
    """
    types = set(_ordered_objects(graph, subject, RDF.type))
    if OWL.Ontology in types:
        return None
    if isinstance(subject, BNode):
        return "other_resources"
    if not isinstance(subject, URIRef):
        return "other_resources"
    if OWL.Class in types or RDFS.Class in types:
        return "classes"
    if OWL.ObjectProperty in types:
        return "object_properties"
    if OWL.DatatypeProperty in types:
        return "datatype_properties"
    if OWL.AnnotationProperty in types:
        return "annotation_properties"
    if RDF.Property in types:
        return "rdf_properties"
    if OWL.NamedIndividual in types or any(
        isinstance(type_iri, URIRef) and not _is_standard_rdf_iri(type_iri)
        for type_iri in types
    ):
        return "individuals"
    return "other_resources"


def _human_readable_relationships(
    graph: _SourceOrderedGraph,
    reference_labels: dict[URIRef, str],
) -> list[_ReviewRelationship]:
    """Render application-resource links without exposing Turtle syntax.

    :param graph: Parsed ontology graph with source-order metadata.
    :param reference_labels: Preferred labels from the frozen reference ontology.
    :return: Readable application relations in statement order.
    """
    bnode_labels = _blank_node_labels(graph)
    fallback_display_names = _fallback_resource_display_names(
        graph,
        reference_labels,
    )
    relationships: list[_ReviewRelationship] = []
    for subject, predicate, obj in graph.triples_in_source_order:
        if (
            not isinstance(predicate, URIRef)
            or _is_standard_rdf_iri(predicate)
            or not isinstance(subject, URIRef | BNode)
            or not isinstance(obj, URIRef | BNode)
            or _resource_category(graph, subject) is None
        ):
            continue
        relationships.append(
            _ReviewRelationship(
                subject=_human_readable_main_entry(
                    graph,
                    subject,
                    bnode_labels,
                    reference_labels,
                    fallback_display_names,
                ),
                predicate=_human_readable_main_entry(
                    graph,
                    predicate,
                    bnode_labels,
                    reference_labels,
                    fallback_display_names,
                ),
                object=_human_readable_main_entry(
                    graph,
                    obj,
                    bnode_labels,
                    reference_labels,
                    fallback_display_names,
                ),
            )
        )
    return relationships


def _human_readable_main_entry(
    graph: _SourceOrderedGraph,
    resource: Any,
    bnode_labels: dict[BNode, str],
    reference_labels: dict[URIRef, str],
    fallback_display_names: dict[URIRef, str] | None = None,
) -> str:
    """Render one resource with the closest available ontology label.

    :param graph: Parsed ontology graph.
    :param resource: URI or blank-node resource to render.
    :param bnode_labels: Stable local names for anonymous resources.
    :param reference_labels: Preferred labels from the frozen reference ontology.
    :param fallback_display_names: Display-only names for generated resources
        that omit both a label and a name property.
    :return: Reference label first, then generated ``rdfs:label`` or
        ``hat_Namen``, then local identifier.
    """
    if isinstance(resource, BNode):
        return bnode_labels[resource]
    if not isinstance(resource, URIRef):
        return str(resource)
    reference_label = reference_labels.get(resource)
    if reference_label is not None:
        return reference_label
    if fallback_display_names is None:
        fallback_display_names = _fallback_resource_display_names(
            graph,
            reference_labels,
        )
    return (
        _existing_resource_name(graph, resource)
        or fallback_display_names.get(resource)
        or frag_uri(resource)
    )


def _existing_resource_name(
    graph: _SourceOrderedGraph,
    resource: URIRef,
) -> str | None:
    """Read explicit generated names without inventing a display fallback.

    :param graph: Parsed generated Turtle in original statement order.
    :param resource: Generated resource whose explicit naming is inspected.
    :return: Preferred ``rdfs:label`` or ``hat_Namen`` value, if present.
    """
    labels = [
        value
        for value in _ordered_objects(graph, resource, RDFS.label)
        if isinstance(value, Literal)
    ]
    return _primary_label(labels) or _generated_resource_name(graph, resource)


def _fallback_resource_display_names(
    graph: _SourceOrderedGraph,
    reference_labels: dict[URIRef, str],
) -> dict[URIRef, str]:
    """Name unlabelled generated resources for a no-Turtle review surface.

    Structural records and events often carry only a declared ontology type.
    Their internal identifiers are needed in RDF but obscure the review. This
    renderer uses the declared type's readable label and, when needed, an
    ordinal in source order. It never writes a label to the graph.

    :param graph: Parsed generated Turtle in original statement order.
    :param reference_labels: Preferred frozen-ontology labels.
    :return: Reader-facing names keyed by otherwise unnamed generated IRIs.
    """
    resources = _uri_resources_in_source_order(graph)
    candidates: list[tuple[URIRef, str]] = []
    for resource in resources:
        if (
            _is_standard_rdf_iri(resource)
            or resource in reference_labels
            or _existing_resource_name(graph, resource)
        ):
            continue
        type_name = _resource_type_display_name(
            graph,
            resource,
            reference_labels,
        )
        candidates.append((resource, type_name or "Unlabelled resource"))

    totals = Counter(type_name for _, type_name in candidates)
    ordinals: defaultdict[str, int] = defaultdict(int)
    display_names: dict[URIRef, str] = {}
    for resource, type_name in candidates:
        ordinals[type_name] += 1
        suffix = f" {ordinals[type_name]}" if totals[type_name] > 1 else ""
        display_names[resource] = f"{type_name}{suffix}"
    return display_names


def _uri_resources_in_source_order(
    graph: _SourceOrderedGraph,
) -> list[URIRef]:
    """List every generated URI resource in first-Turtle-appearance order.

    :param graph: Parsed generated Turtle with ordered statements.
    :return: Unique URI resources in their first statement appearance.
    """
    resources: list[URIRef] = []
    seen: set[URIRef] = set()
    for subject, predicate, obj in graph.triples_in_source_order:
        for value in (subject, predicate, obj):
            if isinstance(value, URIRef) and value not in seen:
                seen.add(value)
                resources.append(value)
    return resources


def _resource_type_display_name(
    graph: _SourceOrderedGraph,
    resource: URIRef,
    reference_labels: dict[URIRef, str],
) -> str | None:
    """Resolve one generated resource's declared type to a readable name.

    :param graph: Parsed generated Turtle in original statement order.
    :param resource: Generated resource with one or more RDF types.
    :param reference_labels: Preferred frozen-ontology labels.
    :return: First non-infrastructure type label, if that type is named.
    """
    for resource_type in _ordered_objects(graph, resource, RDF.type):
        if not isinstance(resource_type, URIRef) or _is_standard_rdf_iri(
            resource_type
        ):
            continue
        return reference_labels.get(resource_type) or _existing_resource_name(
            graph,
            resource_type,
        )
    return None


def _generated_resource_name(
    graph: _SourceOrderedGraph,
    resource: URIRef,
) -> str | None:
    """Read an AI-generated name when an output omits ``rdfs:label``.

    The historian review is not an RDF inspection surface. Standalone Haiu
    outputs often provide a readable ``hat_Namen`` literal but no
    ``rdfs:label``; using it here prevents the review from exposing an internal
    ``i_<regest>_...`` IRI. This affects display only and never changes raw
    Turtle, workbook keys, or evaluation calculations.

    :param graph: Parsed generated Turtle in original statement order.
    :param resource: Generated resource needing a reader-facing display name.
    :return: Preferred generated name or ``None`` when none is available.
    """
    names = [
        obj
        for subject, predicate, obj in graph.triples_in_source_order
        if subject == resource
        and isinstance(predicate, URIRef)
        and frag_uri(predicate) == HISTORIAN_REVIEW_GENERATED_NAME_PROPERTY
        and isinstance(obj, Literal)
    ]
    return _primary_label(names)


def _primary_label(labels: list[Literal]) -> str | None:
    """Select an existing preferred name without spelling normalization.

    :param labels: Labels in their source-ontology or Turtle appearance order.
    :return: German label first, then language-neutral or first available label.
    """
    for language in ("de", None):
        for label in labels:
            if label.language == language:
                return str(label)
    return str(labels[0]) if labels else None


def _ordered_objects(
    graph: _SourceOrderedGraph, subject: Any, predicate: Any
) -> list[Any]:
    """Read graph objects without losing their first Turtle appearance.

    :param graph: Parsed ontology graph with ordered statements.
    :param subject: RDF subject to inspect.
    :param predicate: RDF predicate to inspect.
    :return: Stable object sequence for the requested statement pattern.
    """
    return [
        obj
        for candidate_subject, candidate_predicate, obj in graph.triples_in_source_order
        if candidate_subject == subject and candidate_predicate == predicate
    ]


def _blank_node_labels(graph: _SourceOrderedGraph) -> dict[BNode, str]:
    """Assign short stable labels to anonymous nodes in source order.

    :param graph: Parsed ontology graph with source-order metadata.
    :return: Blank-node display labels keyed by RDFLib node identity.
    """
    labels: dict[BNode, str] = {}
    for triple in graph.triples_in_source_order:
        for term in triple:
            if isinstance(term, BNode) and term not in labels:
                labels[term] = f"Unnamed resource {len(labels) + 1}"
    return labels


def _is_standard_rdf_iri(resource: URIRef) -> bool:
    """Return whether an IRI belongs to an RDF serialization namespace.

    :param resource: Predicate or type candidate to classify.
    :return: True for RDF, RDFS, OWL, or SKOS infrastructure terms.
    """
    return str(resource).startswith(_STANDARD_RDF_NAMESPACES)


def _write_historian_review_guide(
    *,
    sheet: Any,
    formats: dict[str, Any],
    run_manifest: dict[str, Any],
    packet_groups: list[list[_HistorianReviewPacket]],
    partial: bool,
    reference_ontology: _FrozenReferenceOntology,
) -> None:
    """Write the blinded reviewer instructions and experiment context.

    :param sheet: Target guide worksheet.
    :param formats: Workbook formats shared by all exported sheets.
    :param run_manifest: Immutable run metadata used for population counts.
    :param packet_groups: Masked review rows grouped by compared regest.
    :param partial: Whether the source run is an explicit diagnostic export.
    :param reference_ontology: Frozen ontology catalogue shown to reviewers.
    :raises ValueError: If the manifest has no frozen review population.
    """
    scheduled_regests = run_manifest.get("regest_ids")
    if not isinstance(scheduled_regests, list):
        raise ValueError("Run manifest has no regest population.")

    complete_triplet_count, additional_pair_count, review_packet_count = (
        _historian_review_population_counts(packet_groups)
    )
    status = (
        "PARTIAL DIAGNOSTIC EXPORT — NOT PUBLICATION EVIDENCE"
        if partial
        else "Completed clean-run analysis export"
    )
    metadata = (
        (
            "Purpose",
            "Assess the generated ontology for historical research quality "
            "without reading Turtle syntax.",
        ),
        (
            "Workbook layout",
            "This evaluation sidecar contains the review guide and frozen "
            "ontology catalogue. Enter grades and comments only in the "
            "companion Historian_Review workbook.",
        ),
        (
            "Population",
            "Include complete three-condition groups whenever every canonical "
            "Stage-2 Turtle parses. Also include either planned two-condition "
            "group when its canonical sidecars parse: DMW versus DMW + Haiu "
            "RAG, or DMW + Haiu RAG versus standalone Haiu RAG.",
        ),
        (
            "Review sample",
            f"{complete_triplet_count} complete regest triplets; "
            f"{additional_pair_count} additional planned two-condition pairs; "
            f"{review_packet_count} "
            "condition-masked review rows.",
        ),
        (
            "Scheduled population",
            f"{len(scheduled_regests)} frozen raw regests in the run.",
        ),
        (
            "Source artifacts",
            "Frozen raw-regest snapshots and canonical, unmodified Stage-2 "
            "Turtle sidecars parsed directly for this export.",
        ),
        (
            "Resource display",
            "Use the frozen reference ontology's preferred label for reused "
            "terms; otherwise use the generated rdfs:label or hat_Namen "
            "literal exactly. If neither exists, show the declared resource "
            "type plus a source-order number instead of an internal IRI.",
        ),
        (
            "Study design",
            "Matched replication. The two DMW conditions share one frozen "
            "annotation per regest; the standalone condition does not use "
            "DMW annotations or workflow responses.",
        ),
        (
            "Blinding",
            "Review IDs are shuffled and condition labels are masked. Do not "
            "use the separate reveal key until the review is complete.",
        ),
        (
            "Rating",
            "Apply the detailed grading scheme below, enter one grade from 1 "
            "(best) to 6 (worst), then record a free historian verdict and "
            "notes. Also record false_assertions when exact atomic counting "
            "is feasible and false_interpretations as 0, 1, 2, or 3+.",
        ),
        (
            "Comparison emphasis",
            "Underlining marks a resource entry or relationship triple that "
            "is absent from at least one other reviewed row for the same "
            "regest. Bold underlined text occurs only in the current condition "
            "and is absent from every compared row.",
        ),
        ("Export status", status),
    )
    _write_historian_review_guide_content(
        sheet=sheet,
        formats=formats,
        metadata=metadata,
        reference_ontology=reference_ontology,
    )


def _write_provider_historian_review_guide(
    *,
    sheet: Any,
    formats: dict[str, Any],
    sources: tuple[_HistorianReviewSource, _HistorianReviewSource],
    partial: bool,
    reference_ontology: _FrozenReferenceOntology,
) -> None:
    """Write context for a workbook that keeps provider reviews separate.

    :param sheet: Target guide worksheet.
    :param formats: Workbook formats shared by all exported sheets.
    :param sources: AcademicCloud and LM Studio review packet sources.
    :param partial: Whether either source is an explicit diagnostic export.
    :param reference_ontology: Shared frozen ontology catalogue shown to
        reviewers.
    :return: None.
    :raises ValueError: If a provider manifest has no frozen population.
    """
    provider_samples: list[tuple[str, str]] = []
    for source in sources:
        scheduled_regests = source.run_manifest.get("regest_ids")
        if not isinstance(scheduled_regests, list):
            raise ValueError("Run manifest has no regest population.")
        complete_triplet_count, additional_pair_count, review_packet_count = (
            _historian_review_population_counts(source.packet_groups)
        )
        provider_samples.append(
            (
                f"{source.provider_name} review sample",
                f"{complete_triplet_count} complete regest triplets; "
                f"{additional_pair_count} additional planned two-condition "
                f"pairs; {review_packet_count} "
                f"condition-masked review rows from {len(scheduled_regests)} "
                "frozen raw regests.",
            )
        )
    status = (
        "PARTIAL DIAGNOSTIC EXPORT — NOT PUBLICATION EVIDENCE"
        if partial
        else "Completed clean-run analysis export"
    )
    metadata = (
        (
            "Purpose",
            "Assess the generated ontology for historical research quality "
            "without reading Turtle syntax.",
        ),
        (
            "Workbook layout",
            "This evaluation sidecar contains the review guide and frozen "
            "ontology catalogue. Enter grades and comments only in the "
            "companion AcademicCloud and LM Studio review workbook.",
        ),
        (
            "Provider layout",
            "AcademicCloud and LM Studio have separate review sheets. "
            "Provider labels are visible as requested; condition labels remain "
            "masked within each sheet.",
        ),
        (
            "Population",
            "Include complete three-condition groups whenever every canonical "
            "Stage-2 Turtle parses. Also include either planned two-condition "
            "group when its canonical sidecars parse: DMW versus DMW + Haiu "
            "RAG, or DMW + Haiu RAG versus standalone Haiu RAG.",
        ),
        *provider_samples,
        (
            "Source artifacts",
            "Frozen raw-regest snapshots and canonical, unmodified Stage-2 "
            "Turtle sidecars parsed directly for this export.",
        ),
        (
            "Resource display",
            "Use the frozen reference ontology's preferred label for reused "
            "terms; otherwise use the generated rdfs:label or hat_Namen "
            "literal exactly. If neither exists, show the declared resource "
            "type plus a source-order number instead of an internal IRI.",
        ),
        (
            "Study design",
            "Matched replication. The two DMW conditions share one frozen "
            "annotation per regest; the standalone condition does not use "
            "DMW annotations or workflow responses.",
        ),
        (
            "Blinding",
            "Review IDs are shuffled and condition labels are masked within "
            "each provider sheet. Do not use the separate reveal key until the "
            "review is complete.",
        ),
        (
            "Rating",
            "Apply the detailed grading scheme below, enter one grade from 1 "
            "(best) to 6 (worst), then record a free historian verdict and "
            "notes. Also record false_assertions when exact atomic counting "
            "is feasible and false_interpretations as 0, 1, 2, or 3+.",
        ),
        (
            "Comparison emphasis",
            "Underlining marks a resource entry or relationship triple that "
            "is absent from at least one other reviewed row for the same "
            "regest. Bold underlined text occurs only in the current condition "
            "and is absent from every compared row.",
        ),
        ("Export status", status),
    )
    _write_historian_review_guide_content(
        sheet=sheet,
        formats=formats,
        metadata=metadata,
        reference_ontology=reference_ontology,
    )


def _historian_review_population_counts(
    packet_groups: list[list[_HistorianReviewPacket]],
) -> tuple[int, int, int]:
    """Count triplet and pair packets for one transparent review population.

    :param packet_groups: Masked groups containing either three conditions or
        one planned two-condition comparison.
    :return: Complete-triplet count, additional-pair count, and total row count.
    :raises ValueError: If a caller constructs an unsupported group size.
    """
    group_sizes = [len(packet_group) for packet_group in packet_groups]
    unsupported_sizes = sorted(
        set(group_sizes).difference(
            {
                len(CONDITIONS),
                len(HISTORIAN_REVIEW_COMPARISON_CONDITIONS[0]),
            }
        )
    )
    if unsupported_sizes:
        raise ValueError(
            "Historian review packets must contain either three conditions or "
            "one planned two-condition comparison."
        )
    return (
        group_sizes.count(len(CONDITIONS)),
        group_sizes.count(len(HISTORIAN_REVIEW_COMPARISON_CONDITIONS[0])),
        sum(group_sizes),
    )


def _write_historian_review_guide_content(
    *,
    sheet: Any,
    formats: dict[str, Any],
    metadata: tuple[tuple[str, str], ...],
    reference_ontology: _FrozenReferenceOntology,
) -> None:
    """Render shared guide layout for individual and provider review exports.

    :param sheet: Target guide worksheet.
    :param formats: Workbook formats shared by all exported sheets.
    :param metadata: Ordered labels and descriptions for this review surface.
    :param reference_ontology: Frozen ontology whose catalogue sheets are
        attached to this workbook.
    :return: None.
    """
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 1, 110, formats["wrap"])
    sheet.set_column(2, 2, 34, formats["wrap"])
    sheet.set_row(0, 26)
    sheet.write(
        0,
        0,
        "Historian ontology quality review guide",
        formats["title"],
    )
    sheet.write(2, 0, "Review metadata", formats["header"])
    sheet.write(2, 1, "Details", formats["header"])
    for row_index, (label, detail) in enumerate(metadata, start=3):
        sheet.write(row_index, 0, label, formats["header"])
        sheet.write(row_index, 1, detail, formats["wrap"])
    condition_header_row = 4 + len(metadata)
    sheet.write(
        condition_header_row, 0, "Conditions included", formats["header"]
    )
    sheet.write(condition_header_row, 1, "Explanation", formats["header"])
    for row_index, (condition, explanation) in enumerate(
        CONDITION_EXPLANATIONS,
        start=condition_header_row + 1,
    ):
        sheet.write(row_index, 0, condition, formats["wrap"])
        sheet.write(row_index, 1, explanation, formats["wrap"])
    catalogue_row = condition_header_row + len(CONDITION_EXPLANATIONS) + 2
    _write_historian_review_guide_row(
        sheet=sheet,
        row_index=catalogue_row,
        label="Frozen ontology reference",
        detail=_reference_ontology_catalogue_guidance(reference_ontology),
        formats=formats,
        height=90,
    )
    _write_historian_review_grading_scheme(
        sheet=sheet,
        formats=formats,
        start_row=catalogue_row + 2,
    )
    sheet.freeze_panes(1, 0)


def _write_historian_review_grading_scheme(
    *,
    sheet: Any,
    formats: dict[str, Any],
    start_row: int,
) -> None:
    """Write the shared decision rule and 1–6 historian-grade definitions.

    The same guide serves single-provider blinded reviews and provider-separated
    reviews. Keeping this rule here ensures graders receive the exact same
    false-assignment threshold in every generated workbook.

    :param sheet: Guide worksheet receiving the grading instructions.
    :param formats: Workbook formats shared by all guide cells.
    :param start_row: Zero-based row where the grading section begins.
    :return: None.
    """
    row_index = start_row
    sheet.write(
        row_index,
        0,
        "Grading Scheme for Regest Models",
        formats["title"],
    )
    sheet.set_row(row_index, 24)
    row_index += 2
    _write_historian_review_guide_row(
        sheet=sheet,
        row_index=row_index,
        label="Core rule",
        detail=HISTORIAN_REVIEW_GRADING_CORE_RULE,
        formats=formats,
        height=84,
    )
    row_index += 2
    sheet.write(row_index, 0, "Grade", formats["header"])
    sheet.write(
        row_index, 1, "Definition and operational meaning", formats["header"]
    )
    sheet.write(row_index, 2, "Recommended action", formats["header"])
    row_index += 1
    grade_row_heights = {
        "1": 60,
        "2": 60,
        "3": 72,
        "4": 108,
        "5": 96,
        "6": 120,
    }
    for grade, definition, action in HISTORIAN_REVIEW_GRADE_DEFINITIONS:
        sheet.write(row_index, 0, grade, formats["header"])
        sheet.write(row_index, 1, definition, formats["wrap"])
        sheet.write(row_index, 2, action, formats["wrap"])
        sheet.set_row(row_index, grade_row_heights[grade])
        row_index += 1
    for label, detail in HISTORIAN_REVIEW_FALSE_ASSIGNMENT_GUIDANCE:
        row_index += 1
        height = {
            "What counts as a false assignment?": 120,
            "How to assign a grade": 144,
            "Grade 4 versus grade 5": 66,
            "Grade 5 versus grade 6": 72,
            "Additional guidance": 108,
            "False-assertion and interpretation counts": 150,
            "Substantive historical assertions": 72,
        }.get(label, 72)
        _write_historian_review_guide_row(
            sheet=sheet,
            row_index=row_index,
            label=label,
            detail=detail,
            formats=formats,
            height=height,
        )
        row_index += 1


def _write_historian_review_guide_row(
    *,
    sheet: Any,
    row_index: int,
    label: str,
    detail: str,
    formats: dict[str, Any],
    height: float,
) -> None:
    """Write one labelled, wrapped review-guide row at a readable height.

    :param sheet: Guide worksheet receiving the row.
    :param row_index: Zero-based row to populate.
    :param label: Short section or grade label placed in the first column.
    :param detail: Wrapped instructions placed in the second column.
    :param formats: Workbook formats shared by the guide.
    :param height: Explicit height that keeps the wrapped guide text visible.
    :return: None.
    """
    sheet.write(row_index, 0, label, formats["header"])
    sheet.write(row_index, 1, detail, formats["wrap"])
    sheet.set_row(row_index, height)


def _historian_review_headers(
    packet_groups: list[list[_HistorianReviewPacket]],
) -> tuple[str, ...]:
    """Select source columns without changing legacy workbook layouts.

    :param packet_groups: Review packets derived from one experiment run.
    :return: Legacy headers or pair-aware headers with source lineage.
    """
    packets = [packet for group in packet_groups for packet in group]
    if not packets or not any(
        "source_regest_id" in packet for packet in packets
    ):
        return HISTORIAN_REVIEW_HEADERS
    if not all(
        all(
            header in packet for header in HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS
        )
        for packet in packets
    ):
        raise ValueError("Historian review packets have partial pair lineage.")
    insertion_index = HISTORIAN_REVIEW_HEADERS.index("regest_text")
    return (
        *HISTORIAN_REVIEW_HEADERS[:insertion_index],
        *HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS,
        *HISTORIAN_REVIEW_HEADERS[insertion_index:],
    )


def _write_historian_review_rows(
    sheet: Any,
    packet_groups: list[list[_HistorianReviewPacket]],
    formats: dict[str, Any],
) -> None:
    """Write grouped historian comparison rows and input controls.

    :param sheet: Target XlsxWriter worksheet.
    :param packet_groups: Sorted regest groups with two or three masked rows.
    :param formats: Workbook formats shared by all exported sheets.
    """
    headers = _historian_review_headers(packet_groups)
    frozen_column_count = HISTORIAN_REVIEW_FROZEN_COLUMN_COUNT
    if headers != HISTORIAN_REVIEW_HEADERS:
        frozen_column_count += len(HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS)
    sheet.freeze_panes(
        HISTORIAN_REVIEW_HEADER_ROW + 1,
        frozen_column_count,
    )
    widths = {
        "review_id": 12,
        "regest_id": 16,
        "source_regest_id": 16,
        "source_sublemma_number": 11,
        "regest_text": 40,
        "relationships": 90,
        "grade_1_best_6_worst": 12,
        "historian_verdict_and_notes": 31.5,
        HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER: 15,
        HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER: 18,
    }
    for column, header in enumerate(headers):
        width = widths.get(header, 40)
        sheet.set_column(column, column, width, formats["review_cell"])
        sheet.write(
            HISTORIAN_REVIEW_HEADER_ROW, column, header, formats["header"]
        )
    if not packet_groups:
        sheet.write(
            HISTORIAN_REVIEW_HEADER_ROW + 1,
            0,
            "No complete triplets or directly parseable planned two-condition "
            "pairs are available.",
            formats["warning"],
        )
        return

    first_data_row = HISTORIAN_REVIEW_HEADER_ROW + 1
    row_index = first_data_row
    for packet_group in packet_groups:
        row_heights = _write_historian_review_group(
            sheet=sheet,
            start_row=row_index,
            packet_group=packet_group,
            formats=formats,
            headers=headers,
        )
        _merge_historian_regest_cells(
            sheet=sheet,
            start_row=row_index,
            packet_group=packet_group,
            row_heights=row_heights,
            formats=formats,
            headers=headers,
        )
        row_index += len(packet_group)

    grade_column = headers.index("grade_1_best_6_worst")
    false_assertions_column = headers.index(
        HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER
    )
    false_interpretations_column = headers.index(
        HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER
    )
    sheet.data_validation(
        first_data_row,
        grade_column,
        row_index - 1,
        grade_column,
        {
            "validate": "list",
            "source": [1, 2, 3, 4, 5, 6],
            "input_title": "Historian grade",
            "input_message": "1 is best; 6 is worst.",
            "error_title": "Choose a grade from 1 to 6",
            "error_message": "Use 1 for best and 6 for worst.",
        },
    )
    sheet.data_validation(
        first_data_row,
        false_assertions_column,
        row_index - 1,
        false_assertions_column,
        {
            "validate": "integer",
            "criteria": ">=",
            "value": 0,
            "input_title": "False atomic assertions",
            "input_message": "Count incorrect class, property, or value assertions; leave blank when not counted.",
            "error_title": "Use a non-negative whole number",
            "error_message": "Enter 0 or a positive whole number.",
        },
    )
    sheet.data_validation(
        first_data_row,
        false_interpretations_column,
        row_index - 1,
        false_interpretations_column,
        {
            "validate": "list",
            "source": [0, 1, 2, "3+"],
            "input_title": "False interpretations",
            "input_message": "Count independent historical misunderstandings, not propagated false triples.",
            "error_title": "Choose 0, 1, 2, or 3+",
            "error_message": "Use the listed interpretation-count bands.",
        },
    )


def _write_historian_review_group(
    *,
    sheet: Any,
    start_row: int,
    packet_group: list[_HistorianReviewPacket],
    formats: dict[str, Any],
    headers: tuple[str, ...],
) -> list[int]:
    """Write one contiguous masked condition comparison group.

    :param sheet: Target review worksheet.
    :param start_row: Zero-based first row of the regest group.
    :param packet_group: Two or three condition-masked packets for one regest.
    :param formats: Workbook formats shared by all exported sheets.
    :param headers: Legacy or pair-aware worksheet columns.
    :return: Calculated row heights before merging shared regest cells.
    """
    shared_resources = {
        header: _shared_resource_entries(packet_group, header)
        for header in HISTORIAN_REVIEW_RESOURCE_HEADERS
    }
    unique_resources = {
        header: _unique_resource_entries(packet_group, header)
        for header in HISTORIAN_REVIEW_RESOURCE_HEADERS
    }
    shared_relationships = _shared_relationships(packet_group)
    unique_relationships = _unique_relationships(packet_group)
    row_heights: list[int] = []
    grade_column = headers.index("grade_1_best_6_worst")
    notes_column = headers.index("historian_verdict_and_notes")
    false_assertions_column = headers.index(
        HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER
    )
    false_interpretations_column = headers.index(
        HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER
    )
    for group_offset, packet in enumerate(packet_group):
        row_index = start_row + group_offset
        max_lines = 1
        for column, header in enumerate(headers):
            value = packet[header]
            if header in {
                "regest_id",
                "source_regest_id",
                "source_sublemma_number",
                "regest_text",
            }:
                continue
            if column == grade_column:
                sheet.write_blank(
                    row_index, column, None, formats["numeric_input"]
                )
            elif column == notes_column:
                sheet.write_blank(
                    row_index, column, None, formats["review_input"]
                )
            elif column in {
                false_assertions_column,
                false_interpretations_column,
            }:
                sheet.write_blank(
                    row_index, column, None, formats["numeric_input"]
                )
            elif header == "relationships":
                assert isinstance(value, list)
                relationships = _relationship_entries(value)
                max_lines = max(max_lines, len(relationships))
                _write_historian_relationship_cell(
                    sheet=sheet,
                    row_index=row_index,
                    column=column,
                    relationships=relationships,
                    shared_relationships=shared_relationships,
                    unique_relationships=unique_relationships,
                    formats=formats,
                )
            elif header in HISTORIAN_REVIEW_RESOURCE_HEADERS:
                assert isinstance(value, list)
                entries = _resource_entries(value)
                _write_historian_resource_cell(
                    sheet=sheet,
                    row_index=row_index,
                    column=column,
                    entries=entries,
                    shared_entries=shared_resources[header],
                    unique_entries=unique_resources[header],
                    formats=formats,
                )
            else:
                assert isinstance(value, str)
                max_lines = max(max_lines, value.count("\n") + 1)
                sheet.write(row_index, column, value, formats["review_cell"])
        row_heights.append(min(max(18, max_lines * 15), 409))
    return row_heights


def _merge_historian_regest_cells(
    *,
    sheet: Any,
    start_row: int,
    packet_group: list[_HistorianReviewPacket],
    row_heights: list[int],
    formats: dict[str, Any],
    headers: tuple[str, ...],
) -> None:
    """Merge the source identifiers that are common to one comparison block.

    :param sheet: Target review worksheet.
    :param start_row: Zero-based first row of the regest group.
    :param packet_group: Two or three condition-masked packets for one regest.
    :param row_heights: Per-row display heights before merging.
    :param formats: Workbook formats shared by all exported sheets.
    :param headers: Legacy or pair-aware worksheet columns.
    """
    regest_id = packet_group[0]["regest_id"]
    regest_text = packet_group[0]["regest_text"]
    assert isinstance(regest_id, str)
    assert isinstance(regest_text, str)
    assert all(packet["regest_id"] == regest_id for packet in packet_group)
    assert all(packet["regest_text"] == regest_text for packet in packet_group)

    required_height = max(
        sum(row_heights),
        max(18, (regest_text.count("\n") + 1) * 15),
    )
    height_deficit = required_height - sum(row_heights)
    for index in range(height_deficit):
        row_heights[index % len(row_heights)] += 1
    for group_offset, height in enumerate(row_heights):
        sheet.set_row(start_row + group_offset, height)

    end_row = start_row + len(packet_group) - 1
    shared_headers = ["regest_id"]
    shared_headers.extend(
        header
        for header in HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS
        if header in headers
    )
    shared_headers.append("regest_text")
    for header in shared_headers:
        value = packet_group[0][header]
        assert isinstance(value, str)
        assert all(packet[header] == value for packet in packet_group)
        column = headers.index(header)
        sheet.merge_range(
            start_row,
            column,
            end_row,
            column,
            value,
            formats["merged_regest"],
        )


def _shared_resource_entries(
    packet_group: list[_HistorianReviewPacket], header: str
) -> set[str]:
    """Find resource entries shared by every row in one regest group.

    :param packet_group: Two or three condition-masked packets for one regest.
    :param header: Resource category to compare.
    :return: Values present in every condition row.
    """
    return set.intersection(
        *[set(_resource_entries(packet[header])) for packet in packet_group]
    )


def _shared_relationships(
    packet_group: list[_HistorianReviewPacket],
) -> set[_ReviewRelationship]:
    """Find relation triples shared by every row in one regest group.

    :param packet_group: Two or three condition-masked packets for one regest.
    :return: Triples present in every condition row.
    """
    return set.intersection(
        *[
            set(_relationship_entries(packet["relationships"]))
            for packet in packet_group
        ]
    )


def _unique_resource_entries(
    packet_group: list[_HistorianReviewPacket], header: str
) -> set[str]:
    """Find resource entries that occur in only one condition row.

    :param packet_group: Three condition-masked packets for one regest.
    :param header: Resource category to compare.
    :return: Values present in exactly one condition row.
    """
    occurrence_counts: defaultdict[str, int] = defaultdict(int)
    for packet in packet_group:
        for entry in set(_resource_entries(packet[header])):
            occurrence_counts[entry] += 1
    return {entry for entry, count in occurrence_counts.items() if count == 1}


def _unique_relationships(
    packet_group: list[_HistorianReviewPacket],
) -> set[_ReviewRelationship]:
    """Find triples that occur in only one condition row.

    :param packet_group: Three condition-masked packets for one regest.
    :return: Triples present in exactly one condition row.
    """
    occurrence_counts: defaultdict[_ReviewRelationship, int] = defaultdict(int)
    for packet in packet_group:
        for relationship in set(_relationship_entries(packet["relationships"])):
            occurrence_counts[relationship] += 1
    return {
        relationship
        for relationship, count in occurrence_counts.items()
        if count == 1
    }


def _resource_entries(
    value: str | list[str] | list[_ReviewRelationship],
) -> list[str]:
    """Narrow one structured resource-cell value to readable names.

    :param value: Packet value for a resource category.
    :return: Resource entries in original Turtle appearance order.
    """
    assert isinstance(value, list)
    assert all(isinstance(entry, str) for entry in value)
    return [entry for entry in value if isinstance(entry, str)]


def _relationship_entries(
    value: str | list[str] | list[_ReviewRelationship],
) -> list[_ReviewRelationship]:
    """Narrow one structured relationship-cell value to relation triples.

    :param value: Packet value for the relationships category.
    :return: Relationship triples in original Turtle appearance order.
    """
    assert isinstance(value, list)
    assert all(isinstance(entry, _ReviewRelationship) for entry in value)
    return [entry for entry in value if isinstance(entry, _ReviewRelationship)]


def _write_historian_resource_cell(
    *,
    sheet: Any,
    row_index: int,
    column: int,
    entries: list[str],
    shared_entries: set[str],
    unique_entries: set[str],
    formats: dict[str, Any],
) -> None:
    """Write one compact resource list with comparison emphasis.

    :param sheet: Target review worksheet.
    :param row_index: Zero-based destination row.
    :param column: Zero-based destination column.
    :param entries: Source-ordered values in the current condition row.
    :param shared_entries: Values common to every compared condition row.
    :param unique_entries: Values that occur in only this condition row.
    :param formats: Workbook formats for cell and comparison emphasis.
    """
    if not entries:
        sheet.write_blank(row_index, column, None, formats["review_cell"])
        return
    cell_value = " — ".join(entries)
    suffixes = [
        _comparison_emphasis_suffix(
            in_all_conditions=entry in shared_entries,
            unique_to_current_condition=entry in unique_entries,
        )
        for entry in entries
    ]
    if not any(suffixes):
        sheet.write(row_index, column, cell_value, formats["review_cell"])
        return
    if len(entries) == 1:
        sheet.write(
            row_index,
            column,
            cell_value,
            formats[f"review{suffixes[0]}_cell"],
        )
        return

    fragments: list[Any] = []
    for index, entry in enumerate(entries):
        if index:
            fragments.append(" — ")
        if suffixes[index]:
            fragments.extend((formats[f"review{suffixes[index]}"], entry))
        else:
            fragments.append(entry)
    sheet.write_rich_string(
        row_index,
        column,
        *fragments,
        formats["review_cell"],
    )


def _write_historian_relationship_cell(
    *,
    sheet: Any,
    row_index: int,
    column: int,
    relationships: list[_ReviewRelationship],
    shared_relationships: set[_ReviewRelationship],
    unique_relationships: set[_ReviewRelationship],
    formats: dict[str, Any],
) -> None:
    """Write bullet-separated, color-coded relationship triples.

    :param sheet: Target review worksheet.
    :param row_index: Zero-based destination row.
    :param column: Zero-based destination column.
    :param relationships: Source-ordered relationship triples to display.
    :param shared_relationships: Triples common to every compared condition row.
    :param unique_relationships: Triples that occur in only this condition row.
    :param formats: Workbook formats for cell and triple terms.
    """
    if not relationships:
        sheet.write_blank(row_index, column, None, formats["wrap"])
        return
    fragments: list[Any] = []
    for index, relationship in enumerate(relationships):
        if index:
            fragments.append("\n")
        relationship_suffix = _comparison_emphasis_suffix(
            in_all_conditions=relationship in shared_relationships,
            unique_to_current_condition=relationship in unique_relationships,
        )
        fragments.extend(
            (
                "• ",
                formats[f"relationship_subject{relationship_suffix}"],
                relationship.subject,
                " — ",
                formats[f"relationship_predicate{relationship_suffix}"],
                relationship.predicate,
                " → ",
                formats[f"relationship_object{relationship_suffix}"],
                relationship.object,
            )
        )
    sheet.write_rich_string(
        row_index,
        column,
        *fragments,
        formats["review_cell"],
    )


def _comparison_emphasis_suffix(
    *, in_all_conditions: bool, unique_to_current_condition: bool
) -> str:
    """Select a rich-text format suffix for one comparison value.

    :param in_all_conditions: Whether every condition row contains the value.
    :param unique_to_current_condition: Whether neither peer row contains it.
    :return: Empty, underlined, or bold-underlined format suffix.
    """
    if unique_to_current_condition:
        return "_unique"
    if not in_all_conditions:
        return "_not_shared"
    return ""
