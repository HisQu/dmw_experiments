#!/usr/bin/env python3
"""Export one comparison run into reproducible CSV and Excel analysis views."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import xlsxwriter
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from dmw_experiments.studies.haiu_comparison.model.ontology import (
    TURTLE_PREFIXES,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    provider_prompt_token_measurement,
)
from haiu.rdf.fmt_utils import frag_uri

CONDITIONS = (
    "workflow_full_ontology",
    "workflow_rag",
    "haiu_rag_ontologizer",
)
HISTORIAN_REVIEW_COMPARISON_CONDITIONS = (
    (
        "workflow_full_ontology",
        "workflow_rag",
    ),
    (
        "workflow_rag",
        "haiu_rag_ontologizer",
    ),
)
CONDITION_EXPLANATIONS = (
    (
        "workflow_full_ontology",
        "DMW reference condition with the complete frozen ontology.",
    ),
    (
        "workflow_rag",
        "The same frozen DMW pipeline using Haiu retrieval.",
    ),
    (
        "haiu_rag_ontologizer",
        "Standalone Haiu retrieval plus direct two-stage generation.",
    ),
)
RETRIEVAL_CONDITIONS = frozenset({"workflow_rag", "haiu_rag_ontologizer"})
SCHEMA_TYPES = {
    OWL.Class: "class",
    RDFS.Class: "class",
    OWL.ObjectProperty: "property",
    OWL.DatatypeProperty: "property",
    RDF.Property: "property",
}
REFERENCE_ONTOLOGY_CLASS_TYPES = frozenset({OWL.Class, RDFS.Class})
REFERENCE_ONTOLOGY_PROPERTY_TYPES = (
    ("Object property", OWL.ObjectProperty),
    ("Datatype property", OWL.DatatypeProperty),
    ("Annotation property", OWL.AnnotationProperty),
    ("RDF property", RDF.Property),
)
REFERENCE_ONTOLOGY_RG_EXPRESSION_NAMES = frozenset(
    {"stringInRG", "stringInRGX"}
)
HISTORIAN_REVIEW_GENERATED_NAME_PROPERTY = "hat_Namen"
CORE_OUTPUT_FILENAMES = (
    "overview.xlsx",
    "masked_historian_quality_review.xlsx",
    "masked_historian_quality_review_evaluation_sidecar.xlsx",
    "historian_quality_review_reveal_key.json",
    "analysis_manifest.json",
    "README.md",
)


@dataclass(frozen=True, slots=True)
class _RunLayout:
    """Resolve one provider execution inside a complete copied run.

    :param root: Directory containing ``run.toml`` and both provider areas.
    :param output: Flat ``raw-<execution>`` source directory.
    :param execution: Provider execution slug.
    """

    root: Path
    output: Path
    execution: str

    @classmethod
    def from_output(cls, output: Path) -> _RunLayout:
        """Validate and resolve one execution source.

        :param output: Flat ``raw-<execution>`` directory.
        :return: Paths used by the raw-data exporter.
        """
        resolved = output.expanduser().resolve()
        if not resolved.is_dir() or not resolved.name.startswith("raw-"):
            raise ValueError("Source must be a raw-<execution> directory.")
        root = resolved.parent
        if not (root / "run.toml").is_file():
            raise ValueError("Provider output is not inside a copied run.")
        return cls(
            root=root,
            output=resolved,
            execution=resolved.name.removeprefix("raw-"),
        )

    @property
    def manifest(self) -> Path:
        """Return the immutable runner manifest for this provider."""
        return self.root / "environment" / f"{self.execution}-run-manifest.json"

    @property
    def provenance(self) -> Path:
        """Return the frozen input-provenance manifest for this provider."""
        return (
            self.output
            / "intermediates-haiu_rag_ontologizer"
            / "provenance"
            / "provenance_manifest.json"
        )

    @property
    def analysis(self) -> Path:
        """Return the provider-specific workbook directory."""
        return self.root / "analysis" / "workbooks" / self.execution


AUDIT_CSV_FILENAMES = (
    "observations.csv",
    "pairs.csv",
    "schema_declarations.csv",
)
PREVIOUS_OUTPUT_FILENAMES = (
    "masked_case_review.xlsx",
    "reveal_key.json",
    "comparison_workbook.xlsx",
    "case_review_blinded.xlsx",
    "case_review_key.json",
    "condition_observations.csv",
    "schema_declarations.csv",
    "novel_schema_declarations.csv",
    "metric_definitions.csv",
)
HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER = "false_assertions"
HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER = "false_interpretations"
HISTORIAN_REVIEW_HEADERS = (
    "review_id",
    "regest_id",
    "regest_text",
    "grade_1_best_6_worst",
    "historian_verdict_and_notes",
    HISTORIAN_REVIEW_FALSE_ASSERTIONS_HEADER,
    HISTORIAN_REVIEW_FALSE_INTERPRETATIONS_HEADER,
    "classes",
    "object_properties",
    "individuals",
    "relationships",
    "datatype_properties",
    "annotation_properties",
    "rdf_properties",
    "other_resources",
)
HISTORIAN_REVIEW_PAIR_LINEAGE_HEADERS = (
    "source_regest_id",
    "source_sublemma_number",
)
HISTORIAN_REVIEW_RESOURCE_HEADERS = (
    "classes",
    "object_properties",
    "individuals",
    "datatype_properties",
    "annotation_properties",
    "rdf_properties",
    "other_resources",
)
HISTORIAN_REVIEW_HEADER_ROW = 0
HISTORIAN_REVIEW_FROZEN_COLUMN_COUNT = 7
HISTORIAN_REVIEW_GRADING_CORE_RULE = "\n".join(
    (
        "Grades range from 1 (best) to 6 (worst).",
        "Grades 1–3 contain no clearly false assignments; distinguish them by completeness and modelling quality.",
        "Grades 4–6 contain at least one clearly false assignment; distinguish them by the kind of historical-quality failure: bounded local or formal error, plausible historical misinformation, or gross source-reading failure.",
        "A model with a clearly false assignment cannot receive a grade better than 4, even when the remainder is excellent.",
        "A missing assignment is an omission, not a false assignment.",
    )
)
HISTORIAN_REVIEW_GRADE_DEFINITIONS = (
    (
        "1",
        "Correct and essentially complete. The central event, actors, institutions, roles, duration, place, chronology, and provenance are modelled appropriately. No false assignments. Only trivial cleanup may remain.",
        "Merge-ready. Perform only routine validation or trivial cleanup.",
    ),
    (
        "2",
        "Correct with minor omissions or defensible simplifications. No false assignments. Some secondary information may be absent, broadly classified, or represented less precisely than ideal.",
        "Merge after limited cleanup or enrichment. No historical assertions need deletion.",
    ),
    (
        "3",
        "Materially incomplete but factually safe. Important actors, events, roles, conditions, institutional relations, durations, or provenance details are missing, but the assignments that are present are defensible. Repair is primarily additive.",
        "Complete manually or regenerate for greater coverage. Existing assignments may be retained.",
    ),
    (
        "4",
        "Formally or locally incorrect, with the central historical proposition substantially intact. At least one false assignment affects ontology structure, predicate choice, documentary organization, or another bounded aspect without materially changing the central event, actors, roles, institutional target, duration, or chronology. The error is readily identifiable and patchable.",
        "Patch manually. Manual correction is clearly feasible and preferable to regeneration.",
    ),
    (
        "5",
        "Substantively historically wrong, but plausibly so. A central actor, event, role, institution, identity, duration, chronology, beneficiary, grantor, petitioner, or institutional relation is wrong. The graph communicates a plausible but materially false historical proposition and requires substantial reconstruction.",
        "Major manual reconstruction or regeneration. Regeneration may be preferable.",
    ),
    (
        "6",
        "Gross source-reading failure. The model fails at an interpretation directly recoverable from the regest or official RG conventions, and the failure dominates or seriously contaminates the graph. Central actors or events may be fabricated, explicit relations reversed, editorial headings treated as people, or basic abbreviations grossly misconstrued. The model is not a trustworthy historical representation or repair basis.",
        "Regenerate. Investigate the pipeline when the same failure recurs systematically.",
    ),
)
HISTORIAN_REVIEW_FALSE_ASSIGNMENT_GUIDANCE = (
    (
        "What counts as a false assignment?",
        "A false assignment is a class, relation, role, property value, or entity interpretation for which no defensible reading of the regest provides support, or which directly contradicts the regest.\n\nExamples:\n• Interpreting a place heading as a person.\n• Assigning the wrong entity type, such as modelling a chapel as an office.\n• Identifying the wrong petitioner, grantor, beneficiary, or institutional target.\n• Reversing the direction of a relation.\n• Modelling a requested duration as a granted duration.\n• Assigning an event to the wrong place or date.\n• Inventing an office, death, membership, patronage, or institutional dependency.\n• Conflating an earlier grant with the current petition, grant, or confirmation.\n• Grossly misconstruing an explicit standard abbreviation or RG convention.",
    ),
    (
        "Not automatically false",
        "• Omitted information.\n• An overly broad but defensible class.\n• An unresolved ambiguity.\n• A disconnected but correctly identified entity.\n• Duplicated entities.\n• Incomplete provenance.\n• Technically awkward but semantically defensible modelling.",
    ),
    (
        "How to assign a grade",
        "1. Are all present assignments defensible?\n   • Yes: assign grade 1, 2, or 3 according to completeness.\n   • No: continue with grades 4–6.\n2. Does a bounded local or formal error leave the central historical proposition correct and readily recoverable?\n   • Yes: grade 4.\n3. Does the graph instead communicate a plausible but materially false central historical proposition?\n   • Yes: grade 5.\n4. Does an obvious source-reading failure dominate the graph or make it untrustworthy as a repair basis?\n   • Yes: grade 6.",
    ),
    (
        "Grade 4 versus grade 5",
        "Ask whether the graph still communicates the correct central historical proposition after mentally discounting the bounded local error. If yes, grade 4. If it communicates a plausible but materially wrong historical proposition, grade 5.",
    ),
    (
        "Grade 5 versus grade 6",
        "Grade 5 is credible historical misinformation that may require expert knowledge to detect. Grade 6 is a gross failure directly recoverable from the source or standard RG conventions and serious enough that the graph is not a trustworthy repair basis.",
    ),
    (
        "Additional guidance",
        "Judge errors by their historical and semantic impact, centrality, and the trustworthiness of the resulting graph, not merely by the number of RDF triples involved. One mistaken interpretation may generate several dependent triples; treat these as one propagated error. When an interpretation is genuinely ambiguous, do not classify it as false unless it is clearly indefensible. Duplicate entities, disconnected but correctly identified entities, broad classes, incomplete provenance, or awkward yet defensible predicates do not automatically constitute false historical assignments.",
    ),
    (
        "False-assertion and interpretation counts",
        "false_assertions counts individual incorrect atomic class, property, or value assertions. It estimates literal graph-cleaning work; enter an exact count when feasible and otherwise leave it blank. false_interpretations counts independent underlying historical misunderstandings: use 0, 1, 2, or 3+. One mistaken interpretation may generate several false triples but still counts as one false_interpretation. For example, interpreting ‘Glusingk Glusingk’ as a person and petitioner can create several false triples but is one independent interpretation error. Neither count mechanically determines the grade.",
    ),
    (
        "Substantive historical assertions",
        "For a normalized false-assertion rate, divide false_assertions by all substantive historical assertions. These include entity types; event–actor roles; institutional affiliations; locations; institutional dependencies; durations; dates; patronages; and grant, petition, and beneficiary relations.",
    ),
)
_STANDARD_RDF_NAMESPACES = tuple(
    str(namespace) for namespace in (RDF, RDFS, OWL, SKOS)
)


class _SourceOrderedGraph(Graph):
    """RDFLib graph that retains Turtle statement order for reviewer output."""

    def __init__(self) -> None:
        super().__init__()
        self.triples_in_source_order: list[tuple[Any, Any, Any]] = []
        self.subjects_in_source_order: list[Any] = []
        self._seen_subjects: set[Any] = set()

    def add(self, triple: tuple[Any, Any, Any]) -> Graph:
        """Record one parsed triple before adding it to the RDF graph.

        :param triple: RDF statement emitted by RDFLib's Turtle parser.
        :return: This graph after storing the statement.
        """
        self.triples_in_source_order.append(triple)
        if triple[0] not in self._seen_subjects:
            self._seen_subjects.add(triple[0])
            self.subjects_in_source_order.append(triple[0])
        return super().add(triple)


@dataclass(frozen=True, slots=True)
class _ReviewRelationship:
    """One displayed ontology relation with separately formatted triple terms."""

    subject: str
    predicate: str
    object: str


_HistorianReviewPacket = dict[str, str | list[str] | list[_ReviewRelationship]]


@dataclass(frozen=True, slots=True)
class ExportPaths:
    """Paths emitted by one workbook export.

    :param workbook: Main readable workbook.
    :param historian_review_workbook: Label-masked, human-readable ontology
        review workbook.
    :param historian_review_evaluation_sidecar: Reviewer instructions and
        frozen-ontology catalogue for the historian review workbook.
    :param historian_review_reveal_key: Condition mapping for the historian
        review workbook.
    :param manifest: Reproducibility manifest.
    :param readme: Reader-orientation file in the analysis directory.
    """

    workbook: Path
    historian_review_workbook: Path
    historian_review_evaluation_sidecar: Path
    historian_review_reveal_key: Path
    manifest: Path
    readme: Path


@dataclass(frozen=True, slots=True)
class HistorianProviderComparisonPaths:
    """Paths emitted by a provider-separated historian review export.

    :param workbook: Workbook with one review worksheet per provider.
    :param evaluation_sidecar: Shared reviewer instructions and
        frozen-ontology catalogue for ``workbook``.
    :param reveal_key: Provider-scoped mappings from review IDs to conditions.
    """

    workbook: Path
    evaluation_sidecar: Path
    reveal_key: Path


@dataclass(frozen=True, slots=True)
class _HistorianReviewSource:
    """Validated review packets and immutable metadata for one provider run."""

    provider_name: str
    run_manifest: dict[str, Any]
    reference_ontology: _FrozenReferenceOntology
    packet_groups: list[list[_HistorianReviewPacket]]
    reveal_key: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class _FrozenReferenceOntology:
    """Immutable provenance-backed ontology used for reviewer display.

    :param source_path: Exact frozen Turtle path inside one experiment run.
    :param sha256: Provenance-verified SHA-256 for the frozen Turtle source.
    :param graph: Parsed reference ontology used only for human-readable views.
    :param reference_iris: Every URIRef found in the frozen graph.
    :param labels: Preferred display labels keyed by ontology resource.
    """

    source_path: Path
    sha256: str
    graph: Graph
    reference_iris: set[URIRef]
    labels: dict[URIRef, str]


def main(argv: list[str] | None = None) -> int:
    """Run the command-line exporter.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    export_run(
        Path(args.run_dir),
        allow_partial=args.allow_partial,
        audit_csv=args.audit_csv,
        overwrite=args.overwrite,
    )
    return 0


def export_run(
    run_dir: Path,
    *,
    allow_partial: bool = False,
    audit_csv: bool = False,
    overwrite: bool = False,
) -> ExportPaths:
    """Build analysis artifacts from authoritative raw experiment JSON.

    :param run_dir: Completed experiment run directory.
    :param allow_partial: Permit a clearly labelled diagnostic export.
    :param audit_csv: Write compact machine-readable audit tables.
    :param overwrite: Replace only known derived-export files.
    :return: Paths to the main results.
    :raises ValueError: If required inputs, raw artifacts, or pair matrix cells
        are missing in a normal completed export.
    """
    layout = _RunLayout.from_output(run_dir)
    run_dir = layout.root
    manifest = _load_json(layout.manifest)
    provenance = _load_json(layout.provenance, allow_missing=allow_partial)
    rows, source_hashes = _load_rows(layout)
    _validate_provenance(provenance=provenance, run_dir=layout.root)
    _validate_raw_contract(
        layout=layout, rows=rows, allow_partial=allow_partial
    )
    reference_ontology = _load_frozen_reference_ontology(
        run_dir=run_dir,
        provenance=provenance,
    )
    declarations = _schema_declarations(
        rows=rows,
        reference_iris=reference_ontology.reference_iris,
    )
    _attach_observation_metrics(rows=rows, declarations=declarations)
    pair_dmw = _paired_rows(
        rows=rows,
        left="workflow_full_ontology",
        right="workflow_rag",
        pair_name="DMW full ontology vs DMW RAG",
    )
    pair_system = _paired_rows(
        rows=rows,
        left="workflow_rag",
        right="haiu_rag_ontologizer",
        pair_name="DMW RAG vs standalone Haiu RAG",
    )
    timing_rows = _timing_rows(rows)
    token_rows = _token_rows(rows)
    summary_rows = _summary_rows(
        rows=rows,
        pair_dmw=pair_dmw,
        pair_system=pair_system,
    )
    analysis_dir = layout.analysis
    _prepare_output_dir(analysis_dir, overwrite=overwrite)
    definitions = _metric_definitions()
    workbook = analysis_dir / "overview.xlsx"
    _write_main_workbook(
        path=workbook,
        manifest=manifest,
        provenance=provenance,
        partial=allow_partial,
        summary_rows=summary_rows,
        pair_dmw=pair_dmw,
        pair_system=pair_system,
        observations=rows,
        timing_rows=timing_rows,
        token_rows=token_rows,
        declarations=declarations,
        definitions=definitions,
    )
    historian_review_workbook = (
        analysis_dir / "masked_historian_quality_review.xlsx"
    )
    historian_review_evaluation_sidecar = _evaluation_sidecar_path(
        historian_review_workbook
    )
    historian_review_packets, historian_review_key = (
        _write_historian_quality_review_workbook(
            path=historian_review_workbook,
            observations=rows,
            run_manifest=manifest,
            run_dir=run_dir,
            partial=allow_partial,
            reference_ontology=reference_ontology,
        )
    )
    _write_evaluation_sidecar_workbook(
        path=historian_review_evaluation_sidecar,
        reference_ontology=reference_ontology,
        write_guide=lambda sheet, formats: _write_historian_review_guide(
            sheet=sheet,
            formats=formats,
            run_manifest=manifest,
            packet_groups=historian_review_packets,
            partial=allow_partial,
            reference_ontology=reference_ontology,
        ),
    )
    historian_review_key_path = (
        analysis_dir / "historian_quality_review_reveal_key.json"
    )
    _write_json(historian_review_key_path, historian_review_key)
    readme_path = analysis_dir / "README.md"
    _write_analysis_readme(
        path=readme_path,
        title="Experiment analysis",
        status=(
            "PARTIAL DIAGNOSTIC EXPORT — NOT PUBLICATION EVIDENCE"
            if allow_partial
            else "Completed clean-run analysis export"
        ),
        audit_csv=audit_csv,
    )
    audit_paths = _write_audit_csv(
        analysis_dir=analysis_dir,
        observations=rows,
        pairs=[*pair_dmw, *pair_system],
        declarations=declarations,
        audit_csv=audit_csv,
    )
    output_paths = [
        workbook,
        historian_review_workbook,
        historian_review_evaluation_sidecar,
        historian_review_key_path,
        readme_path,
        *audit_paths,
    ]
    analysis_manifest = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exporter_sha256": _sha256_file(Path(__file__)),
        "allow_partial": allow_partial,
        "audit_csv_enabled": audit_csv,
        "run_manifest_sha256": _sha256_file(layout.manifest),
        "provenance_manifest_sha256": _sha256_file(layout.provenance)
        if layout.provenance.exists()
        else None,
        "source_raw_sha256": source_hashes,
        "provenance_input_sha256": provenance.get("inputs", {}),
        "row_count": len(rows),
        "condition_counts": _condition_counts(rows),
        "pair_denominators": {
            "dmw_full_vs_rag": _pair_denominator(pair_dmw),
            "workflow_rag_vs_haiu_rag": _pair_denominator(pair_system),
        },
        "metric_definitions": definitions,
        "outputs": {
            path.relative_to(layout.root).as_posix(): _sha256_file(path)
            for path in output_paths
        },
    }
    analysis_manifest_path = analysis_dir / "analysis_manifest.json"
    _write_json(analysis_manifest_path, analysis_manifest)
    return ExportPaths(
        workbook=workbook,
        historian_review_workbook=historian_review_workbook,
        historian_review_evaluation_sidecar=historian_review_evaluation_sidecar,
        historian_review_reveal_key=historian_review_key_path,
        manifest=analysis_manifest_path,
        readme=readme_path,
    )


def export_provider_historian_review_workbook(
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    *,
    workbook_path: Path,
    allow_partial: bool = False,
    overwrite: bool = False,
) -> HistorianProviderComparisonPaths:
    """Export one workbook with separate masked reviews for both providers.

    The provider names are intentionally visible because the requested surface
    compares provider runs. Condition identities remain masked inside each
    review worksheet and retain their separate reveal-key namespaces.

    :param academiccloud_run_dir: AcademicCloud experiment-run directory.
    :param lmstudio_run_dir: LM Studio experiment-run directory.
    :param workbook_path: Destination for the combined review workbook. Its
        adjacent evaluation sidecar is derived automatically.
    :param allow_partial: Permit clearly labelled diagnostic source runs.
    :param overwrite: Replace only this export's workbook, sidecar, and key.
    :return: Paths to the provider-separated workbook, sidecar, and key.
    :raises ValueError: If source artifacts are invalid or output exists.
    """
    sources = _load_provider_historian_review_sources(
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        allow_partial=allow_partial,
    )
    reference_ontology = _shared_reference_ontology(sources)
    workbook_path = workbook_path.resolve()
    evaluation_sidecar_path = _evaluation_sidecar_path(workbook_path)
    reveal_key_path = workbook_path.with_name(
        f"{workbook_path.stem}_reveal_key.json"
    )
    _prepare_historian_evaluation_outputs(
        paths=(workbook_path, evaluation_sidecar_path, reveal_key_path),
        overwrite=overwrite,
    )

    workbook = xlsxwriter.Workbook(workbook_path, {"strings_to_urls": False})
    try:
        formats = _formats(workbook)
        for source in sources:
            sheet: Any = workbook.add_worksheet(source.provider_name)
            _write_historian_review_rows(sheet, source.packet_groups, formats)
    finally:
        workbook.close()
    _write_evaluation_sidecar_workbook(
        path=evaluation_sidecar_path,
        reference_ontology=reference_ontology,
        write_guide=lambda sheet, formats: (
            _write_provider_historian_review_guide(
                sheet=sheet,
                formats=formats,
                sources=sources,
                partial=allow_partial,
                reference_ontology=reference_ontology,
            )
        ),
    )

    reveal_key = {source.provider_name: source.reveal_key for source in sources}
    _write_json(reveal_key_path, reveal_key)
    return HistorianProviderComparisonPaths(
        workbook=workbook_path,
        evaluation_sidecar=evaluation_sidecar_path,
        reveal_key=reveal_key_path,
    )


def export_provider_historian_evaluation_sidecar(
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    *,
    review_workbook_path: Path,
    allow_partial: bool = False,
    overwrite: bool = False,
) -> Path:
    """Refresh one review workbook's adjacent guide and ontology catalogue.

    This is intended for a workbook that already contains manual grades or
    notes. It writes only the adjacent evaluation sidecar and never reads,
    replaces, or modifies the review workbook or its reveal key.

    :param academiccloud_run_dir: AcademicCloud experiment-run directory.
    :param lmstudio_run_dir: LM Studio experiment-run directory.
    :param review_workbook_path: Existing or planned combined review workbook.
    :param allow_partial: Permit clearly labelled diagnostic source runs.
    :param overwrite: Replace only an existing adjacent sidecar.
    :return: Path of the written evaluation sidecar.
    :raises ValueError: If source artifacts are invalid or the sidecar exists.
    """
    sources = _load_provider_historian_review_sources(
        academiccloud_run_dir=academiccloud_run_dir,
        lmstudio_run_dir=lmstudio_run_dir,
        allow_partial=allow_partial,
    )
    reference_ontology = _shared_reference_ontology(sources)
    evaluation_sidecar_path = _evaluation_sidecar_path(
        review_workbook_path.resolve()
    )
    _prepare_historian_evaluation_outputs(
        paths=(evaluation_sidecar_path,),
        overwrite=overwrite,
    )
    _write_evaluation_sidecar_workbook(
        path=evaluation_sidecar_path,
        reference_ontology=reference_ontology,
        write_guide=lambda sheet, formats: (
            _write_provider_historian_review_guide(
                sheet=sheet,
                formats=formats,
                sources=sources,
                partial=allow_partial,
                reference_ontology=reference_ontology,
            )
        ),
    )
    return evaluation_sidecar_path


def _load_provider_historian_review_sources(
    *,
    academiccloud_run_dir: Path,
    lmstudio_run_dir: Path,
    allow_partial: bool,
) -> tuple[_HistorianReviewSource, _HistorianReviewSource]:
    """Load the two provider review sources through the same validation path.

    :param academiccloud_run_dir: AcademicCloud experiment-run directory.
    :param lmstudio_run_dir: LM Studio experiment-run directory.
    :param allow_partial: Permit clearly labelled diagnostic source runs.
    :return: Validated AcademicCloud and LM Studio review sources.
    """
    return (
        _load_historian_review_source(
            provider_name="AcademicCloud",
            run_dir=academiccloud_run_dir,
            allow_partial=allow_partial,
        ),
        _load_historian_review_source(
            provider_name="LM Studio",
            run_dir=lmstudio_run_dir,
            allow_partial=allow_partial,
        ),
    )


def _load_historian_review_source(
    *, provider_name: str, run_dir: Path, allow_partial: bool
) -> _HistorianReviewSource:
    """Validate one run and derive its masked historian-review packets.

    :param provider_name: Visible provider label for the combined workbook.
    :param run_dir: Root directory of the provider-specific experiment run.
    :param allow_partial: Permit a clearly labelled diagnostic source run.
    :return: Validated packets and reveal key for one provider worksheet.
    """
    layout = _RunLayout.from_output(run_dir)
    run_dir = layout.root
    run_manifest = _load_json(layout.manifest)
    provenance = _load_json(layout.provenance, allow_missing=allow_partial)
    rows, _ = _load_rows(layout)
    _validate_provenance(provenance=provenance, run_dir=layout.root)
    _validate_raw_contract(
        layout=layout,
        rows=rows,
        allow_partial=allow_partial,
    )
    reference_ontology = _load_frozen_reference_ontology(
        run_dir=run_dir,
        provenance=provenance,
    )
    packet_groups, reveal_key = _historian_review_packets(
        observations=rows,
        run_manifest=run_manifest,
        run_dir=run_dir,
        reference_labels=reference_ontology.labels,
    )
    return _HistorianReviewSource(
        provider_name=provider_name,
        run_manifest=run_manifest,
        reference_ontology=reference_ontology,
        packet_groups=packet_groups,
        reveal_key=reveal_key,
    )


def _prepare_historian_evaluation_outputs(
    *, paths: tuple[Path, ...], overwrite: bool
) -> None:
    """Create the destination parent and replace only named owned outputs.

    :param paths: Review, sidecar, and/or reveal-key destinations owned by this
        export operation.
    :param overwrite: Whether existing owned artifacts may be replaced.
    :return: None.
    :raises ValueError: If an output exists without explicit replacement.
    """
    if len({path.parent for path in paths}) != 1:
        raise ValueError("Historian evaluation outputs must share a directory.")
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise ValueError(
            f"Provider historian-review export already exists: {names}. "
            "Pass overwrite=True to replace only these files."
        )
    for path in existing:
        path.unlink()


def _evaluation_sidecar_path(review_workbook_path: Path) -> Path:
    """Name the companion guide and ontology catalogue workbook.

    :param review_workbook_path: Main workbook containing editable review rows.
    :return: Adjacent evaluation-sidecar workbook path.
    """
    return review_workbook_path.with_name(
        f"{review_workbook_path.stem}_evaluation_sidecar.xlsx"
    )


def _write_evaluation_sidecar_workbook(
    *,
    path: Path,
    reference_ontology: _FrozenReferenceOntology,
    write_guide: Callable[[Any, dict[str, Any]], None],
) -> None:
    """Write non-editable review guidance apart from the editable model rows.

    Keeping instructions and the frozen ontology catalogue in a separate file
    leaves the historian's primary workbook limited to editable review sheets
    while retaining one auditable, provenance-backed reference surface.

    :param path: Destination for the sidecar workbook.
    :param reference_ontology: Frozen vocabulary rendered for review support.
    :param write_guide: Variant-specific callback that writes ``Review_Guide``.
    :return: None.
    """
    workbook = xlsxwriter.Workbook(path, {"strings_to_urls": False})
    try:
        formats = _formats(workbook)
        guide: Any = workbook.add_worksheet("Review_Guide")
        write_guide(guide, formats)
        _write_reference_ontology_catalogue_sheets(
            workbook=workbook,
            formats=formats,
            reference_ontology=reference_ontology,
        )
    finally:
        workbook.close()


def _validate_provenance(*, provenance: dict[str, Any], run_dir: Path) -> None:
    """Verify every frozen provenance input before calculating metrics.

    :param provenance: Stored provenance manifest.
    :param run_dir: Experiment run directory.
    :return: None.
    :raises ValueError: If a frozen source file is missing or changed.
    """
    inputs = provenance.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("Provenance manifest has no input-hash mapping.")
    for label, entry in inputs.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Provenance entry is malformed: {label}")
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        path = run_dir / str(relative)
        if not isinstance(relative, str) or not path.is_file():
            raise ValueError(f"Frozen provenance input is missing: {label}")
        if expected_hash != _sha256_file(path):
            raise ValueError(f"Frozen provenance input hash changed: {label}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export reproducible workbook views from one experiment run."
    )
    parser.add_argument("run_dir", help="RESULTS/<run_id> directory")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Create a labelled diagnostic workbook for an incomplete matrix.",
    )
    parser.add_argument(
        "--audit-csv",
        action="store_true",
        help="Write observations, pairs, and schema declarations under audit_csv/.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only known derived-export files in analysis/.",
    )
    return parser


def _load_rows(
    layout: _RunLayout,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    raw_dir = layout.output
    rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in sorted(raw_dir.glob("result-*/*.json")):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"Raw result is not an object: {path}")
        condition = str(
            payload.get("condition") or path.parent.name.removeprefix("result-")
        )
        regest_id = str(payload.get("regest_id") or path.stem)
        if _is_retry_pending(
            layout=layout,
            condition=condition,
            regest_id=regest_id,
        ):
            continue
        row = dict(payload)
        row["condition"] = condition
        row["regest_id"] = regest_id
        row["raw_artifact_path"] = path.relative_to(layout.root).as_posix()
        row["raw_ttl_artifact_path"] = _raw_ttl_path(
            layout, condition, regest_id
        )
        _reconcile_turtle_generation_input_tokens(row)
        rows.append(row)
        hashes[path.relative_to(layout.root).as_posix()] = _sha256_file(path)
    if not rows:
        raise ValueError(f"No raw result JSON found under {raw_dir}.")
    return rows, hashes


def _reconcile_turtle_generation_input_tokens(
    row: dict[str, Any],
) -> None:
    """Prefer complete Stage-2 provider input usage in derived exports.

    Older workflow records stored a locally rendered Stage-2 instruction
    instead of its full retained conversation. The stage-level provider usage
    was nevertheless captured in the same immutable raw record, so derived
    exports can correct the final-generation input metric without modifying
    source evidence.

    :param row: Raw observation copied into the derived analysis view.
    :return: ``None`` after updating complete provider-backed token fields.
    """
    generation_budget = row.get("generation_budget")
    if not isinstance(generation_budget, dict):
        return
    stage2 = generation_budget.get("stage2")
    if not isinstance(stage2, dict):
        return
    stage2_tokens = stage2.get("provider_prompt_tokens")
    measurement = provider_prompt_token_measurement(stage2_tokens)
    if measurement is None:
        return
    row.update(
        {
            "prompt_tokens": measurement.tokens,
            "prompt_tokens_source": measurement.source,
            "prompt_tokens_complete": True,
        }
    )


def _is_retry_pending(
    *, layout: _RunLayout, condition: str, regest_id: str
) -> bool:
    """Keep a recoverable failed attempt out of a derived analysis view.

    The runner writes its raw failure checkpoint before scheduling a retry so a
    machine restart cannot lose the error. That checkpoint is not a terminal
    experimental observation and will be replaced when the next attempt
    completes.

    :param layout: Provider paths that own the attempt state.
    :param condition: Condition directory that owns the raw checkpoint.
    :param regest_id: Stable source identifier for the condition cell.
    :return: Whether the matching attempt state explicitly requests a retry.
    """
    attempt_state = _load_json(
        layout.output
        / f"intermediates-{condition}"
        / f"{regest_id}.attempt.json",
        allow_missing=True,
    )
    return attempt_state.get("status") == "retry_pending"


def _validate_raw_contract(
    *, layout: _RunLayout, rows: list[dict[str, Any]], allow_partial: bool
) -> None:
    expected_ids = {
        str(value)
        for value in _load_json(layout.manifest).get("regest_ids", [])
    }
    observed: set[tuple[str, str]] = set()
    failures: list[str] = []
    for row in rows:
        condition = str(row["condition"])
        regest_id = str(row["regest_id"])
        observed.add((condition, regest_id))
        result_dir = layout.output / f"result-{condition}"
        intermediate_dir = layout.output / f"intermediates-{condition}"
        raw_yaml = result_dir / f"{regest_id}.yaml"
        if not raw_yaml.is_file():
            failures.append(f"missing raw YAML: {condition}/{regest_id}")
        if condition in RETRIEVAL_CONDITIONS:
            retrieval_base = intermediate_dir / f"{regest_id}.retrieved"
            for suffix in (".ttl", ".yaml"):
                if not Path(f"{retrieval_base}{suffix}").is_file():
                    failures.append(
                        f"missing retrieval {suffix}: {condition}/{regest_id}"
                    )
        if (
            bool(row.get("success"))
            and not (result_dir / f"{regest_id}.ttl").is_file()
        ):
            failures.append(
                f"missing successful Turtle: {condition}/{regest_id}"
            )
        if bool(row.get("success")) and not bool(
            row.get("raw_ttl_capture_complete")
        ):
            failures.append(
                f"missing exact Stage-2 Turtle capture: {condition}/{regest_id}"
            )
    missing_matrix = [
        f"{condition}/{regest_id}"
        for condition in CONDITIONS
        for regest_id in expected_ids
        if (condition, regest_id) not in observed
    ]
    failures.extend(
        f"missing condition matrix cell: {cell}" for cell in missing_matrix
    )
    if failures and not allow_partial:
        raise ValueError("Raw-artifact contract failed: " + "; ".join(failures))


def _load_frozen_reference_ontology(
    *, run_dir: Path, provenance: dict[str, Any]
) -> _FrozenReferenceOntology:
    """Load the exact reference ontology frozen with one experiment run.

    The review catalogue must describe the ontology that the experiment used,
    rather than an OPA working copy that may have different resource IRIs.

    :param run_dir: Root directory that owns the frozen provenance artifacts.
    :param provenance: Provenance manifest that identifies the ontology file.
    :return: Parsed, provenance-verified reference ontology and display labels.
    :raises ValueError: If the required source is absent or has changed.
    """
    inputs = provenance.get("inputs") if isinstance(provenance, dict) else None
    entry = (
        inputs.get("reference_ontology") if isinstance(inputs, dict) else None
    )
    relative = entry.get("path") if isinstance(entry, dict) else None
    expected_sha256 = entry.get("sha256") if isinstance(entry, dict) else None
    if not isinstance(relative, str) or not isinstance(expected_sha256, str):
        raise ValueError(
            "The exporter requires frozen provenance input 'reference_ontology'."
        )
    source_path = run_dir / relative
    if not source_path.is_file():
        raise ValueError(
            "Frozen provenance input is missing: reference_ontology"
        )
    source_sha256 = _sha256_file(source_path)
    if source_sha256 != expected_sha256:
        raise ValueError(
            "Frozen provenance input hash changed: reference_ontology"
        )
    graph = Graph()
    graph.parse(source_path, format="turtle")
    reference_iris = {
        term
        for subject, predicate, obj in graph
        for term in (subject, predicate, obj)
        if isinstance(term, URIRef)
    }
    labels_by_resource: defaultdict[URIRef, list[Literal]] = defaultdict(list)
    for resource, label in graph.subject_objects(RDFS.label):
        if isinstance(resource, URIRef) and isinstance(label, Literal):
            labels_by_resource[resource].append(label)
    reference_labels = {
        resource: label
        for resource, labels in labels_by_resource.items()
        if (label := _primary_label(labels)) is not None
    }
    return _FrozenReferenceOntology(
        source_path=source_path,
        sha256=source_sha256,
        graph=graph,
        reference_iris=reference_iris,
        labels=reference_labels,
    )


def _shared_reference_ontology(
    sources: tuple[_HistorianReviewSource, _HistorianReviewSource],
) -> _FrozenReferenceOntology:
    """Return the one ontology valid for a provider-comparison workbook.

    A shared vocabulary sheet would be misleading if the provider runs used
    different frozen ontologies, so this comparison export requires byte-level
    equality of their provenance-backed reference snapshots.

    :param sources: Exactly two validated provider review sources.
    :return: The common frozen ontology snapshot.
    :raises ValueError: If the sources froze different ontology snapshots.
    """
    first, second = sources
    if first.reference_ontology.sha256 != second.reference_ontology.sha256:
        raise ValueError(
            "Provider review sources use different frozen reference ontologies: "
            f"{first.provider_name}={first.reference_ontology.sha256}; "
            f"{second.provider_name}={second.reference_ontology.sha256}."
        )
    return first.reference_ontology


def _write_reference_ontology_catalogue_sheets(
    *,
    workbook: Any,
    formats: dict[str, Any],
    reference_ontology: _FrozenReferenceOntology,
) -> None:
    """Add concise, no-Turtle views of the frozen reference vocabulary.

    :param workbook: Workbook receiving the three reference worksheets.
    :param formats: Workbook formats shared by catalogue cells.
    :param reference_ontology: Provenance-backed ontology used by the run.
    :return: None.
    """
    for sheet_name, rows, widths in (
        (
            "Ontology_Classes",
            _reference_class_rows(reference_ontology),
            (30, 62, 30, 38, 78),
        ),
        (
            "Ontology_Properties",
            _reference_property_rows(reference_ontology),
            (20, 30, 62, 28, 28, 38),
        ),
        (
            "Ontology_Individuals",
            _reference_individual_rows(reference_ontology),
            (34, 34, 62, 38),
        ),
    ):
        sheet: Any = workbook.add_worksheet(sheet_name)
        _write_reference_ontology_catalogue_sheet(
            sheet=sheet,
            rows=rows,
            widths=widths,
            formats=formats,
            table_name=sheet_name,
        )


def _write_reference_ontology_catalogue_sheet(
    *,
    sheet: Any,
    rows: list[dict[str, str]],
    widths: tuple[int, ...],
    formats: dict[str, Any],
    table_name: str,
) -> None:
    """Write one filterable reviewer-facing ontology catalogue worksheet.

    :param sheet: Target worksheet for one resource category.
    :param rows: Human-readable vocabulary rows in their stable display order.
    :param widths: Explicit reader-oriented widths for every displayed column.
    :param formats: Workbook formats shared by catalogue cells.
    :param table_name: Excel-safe logical table name.
    :return: None.
    """
    headers = _fieldnames(rows)
    sheet.freeze_panes(1, 0)
    sheet.set_default_row(42)
    for column, (header, width) in enumerate(zip(headers, widths, strict=True)):
        sheet.write(0, column, header, formats["header"])
        sheet.set_column(column, column, width, formats["wrap"])
    for row_index, row in enumerate(rows, start=1):
        for column, header in enumerate(headers):
            sheet.write(row_index, column, row[header], formats["wrap"])
    sheet.add_table(
        0,
        0,
        len(rows),
        len(headers) - 1,
        {
            "name": _safe_table_name(table_name),
            "style": "Table Style Medium 2",
            "columns": [{"header": header} for header in headers],
        },
    )


def _reference_class_rows(
    reference_ontology: _FrozenReferenceOntology,
) -> list[dict[str, str]]:
    """Build readable class records from the frozen reference graph.

    :param reference_ontology: Parsed provenance-backed ontology snapshot.
    :return: Alphabetically ordered class rows without Turtle identifiers.
    """
    graph = reference_ontology.graph
    resources = _declared_reference_resources(
        graph=graph,
        type_iris=REFERENCE_ONTOLOGY_CLASS_TYPES,
    )
    rows = [
        {
            "Class": _reference_resource_label(resource, reference_ontology),
            "Definition": _reference_literal(graph, resource, SKOS.definition),
            "Parent class(es)": _reference_resource_list(
                resources=graph.objects(resource, RDFS.subClassOf),
                reference_ontology=reference_ontology,
            ),
            "RG expression(s)": _reference_rg_expressions(
                graph=graph,
                resource=resource,
            ),
            "RG example": _reference_literal(graph, resource, SKOS.example),
        }
        for resource in resources
    ]
    return _sort_reference_rows(rows, "Class")


def _reference_property_rows(
    reference_ontology: _FrozenReferenceOntology,
) -> list[dict[str, str]]:
    """Build readable property records from the frozen reference graph.

    :param reference_ontology: Parsed provenance-backed ontology snapshot.
    :return: Alphabetically ordered property rows with declared type and scope.
    """
    graph = reference_ontology.graph
    rows: list[dict[str, str]] = []
    seen_resources: set[URIRef] = set()
    for property_type, type_iri in REFERENCE_ONTOLOGY_PROPERTY_TYPES:
        resources = _declared_reference_resources(
            graph=graph,
            type_iris=frozenset({type_iri}),
        )
        for resource in resources - seen_resources:
            seen_resources.add(resource)
            rows.append(
                {
                    "Property type": property_type,
                    "Property": _reference_resource_label(
                        resource, reference_ontology
                    ),
                    "Definition": _reference_literal(
                        graph, resource, SKOS.definition
                    ),
                    "Domain": _reference_resource_list(
                        resources=graph.objects(resource, RDFS.domain),
                        reference_ontology=reference_ontology,
                    ),
                    "Range": _reference_resource_list(
                        resources=graph.objects(resource, RDFS.range),
                        reference_ontology=reference_ontology,
                    ),
                    "RG expression(s)": _reference_rg_expressions(
                        graph=graph,
                        resource=resource,
                    ),
                }
            )
    return _sort_reference_rows(rows, "Property")


def _reference_individual_rows(
    reference_ontology: _FrozenReferenceOntology,
) -> list[dict[str, str]]:
    """Build readable named-individual records from the frozen graph.

    :param reference_ontology: Parsed provenance-backed ontology snapshot.
    :return: Alphabetically ordered controlled-vocabulary individual rows.
    """
    graph = reference_ontology.graph
    resources = _declared_reference_resources(
        graph=graph,
        type_iris=frozenset({OWL.NamedIndividual}),
    )
    rows = [
        {
            "Individual": _reference_resource_label(
                resource, reference_ontology
            ),
            "Type(s)": _reference_resource_list(
                resources=(
                    resource_type
                    for resource_type in graph.objects(resource, RDF.type)
                    if resource_type != OWL.NamedIndividual
                ),
                reference_ontology=reference_ontology,
            ),
            "Definition": _reference_literal(graph, resource, SKOS.definition),
            "RG expression(s)": _reference_rg_expressions(
                graph=graph,
                resource=resource,
            ),
        }
        for resource in resources
    ]
    return _sort_reference_rows(rows, "Individual")


def _declared_reference_resources(
    *, graph: Graph, type_iris: frozenset[URIRef]
) -> set[URIRef]:
    """Select URI resources explicitly declared with one ontology type.

    :param graph: Frozen reference ontology graph.
    :param type_iris: RDF types that define the requested resource category.
    :return: URI resources declared with at least one requested RDF type.
    """
    return {
        resource
        for type_iri in type_iris
        for resource in graph.subjects(RDF.type, type_iri)
        if isinstance(resource, URIRef)
    }


def _reference_resource_label(
    resource: URIRef, reference_ontology: _FrozenReferenceOntology
) -> str:
    """Return the reviewer-facing name for one frozen ontology resource.

    :param resource: URI resource from the frozen ontology graph.
    :param reference_ontology: Label index for the frozen ontology snapshot.
    :return: Preferred label or a concise local identifier when unlabelled.
    """
    return reference_ontology.labels.get(resource, frag_uri(resource))


def _reference_resource_list(
    *,
    resources: Iterable[Any],
    reference_ontology: _FrozenReferenceOntology,
) -> str:
    """Render referenced resources as a deterministic label-only list.

    :param resources: Candidate range, domain, parent, or type resources.
    :param reference_ontology: Label index for the frozen ontology snapshot.
    :return: Unique labels joined with em dashes; blank-node restrictions omitted.
    """
    labels = {
        _reference_resource_label(resource, reference_ontology)
        for resource in resources
        if isinstance(resource, URIRef)
    }
    return " — ".join(sorted(labels, key=str.casefold))


def _reference_literal(
    graph: Graph, resource: URIRef, predicate: URIRef
) -> str:
    """Select one preferred annotation literal without exposing RDF syntax.

    :param graph: Frozen reference ontology graph.
    :param resource: Resource receiving the requested annotation.
    :param predicate: Annotation predicate such as ``skos:definition``.
    :return: German, language-neutral, or first available annotation text.
    """
    literals = [
        value
        for value in graph.objects(resource, predicate)
        if isinstance(value, Literal)
    ]
    return _primary_label(literals) or ""


def _reference_rg_expressions(*, graph: Graph, resource: URIRef) -> str:
    """Collect documented RG strings for one ontology resource.

    :param graph: Frozen reference ontology graph.
    :param resource: Resource whose source-language indicators are displayed.
    :return: Unique ``stringInRG`` and ``stringInRGX`` values in stable order.
    """
    expressions = {
        str(value)
        for predicate, value in graph.predicate_objects(resource)
        if isinstance(predicate, URIRef)
        and frag_uri(predicate) in REFERENCE_ONTOLOGY_RG_EXPRESSION_NAMES
        and isinstance(value, Literal)
    }
    return " — ".join(sorted(expressions, key=str.casefold))


def _sort_reference_rows(
    rows: list[dict[str, str]], label_column: str
) -> list[dict[str, str]]:
    """Sort a catalogue by its human-facing label, not an internal IRI.

    :param rows: Catalogue records with one designated display-label column.
    :param label_column: Key holding the resource's human-readable label.
    :return: Rows in a deterministic case-insensitive display order.
    """
    return sorted(rows, key=lambda row: row[label_column].casefold())


def _reference_ontology_catalogue_guidance(
    reference_ontology: _FrozenReferenceOntology,
) -> str:
    """Explain how the blinded review may use the vocabulary catalogue.

    :param reference_ontology: Frozen ontology providing the catalogue.
    :return: Concise reviewer-facing instructions and resource counts.
    """
    graph = reference_ontology.graph
    class_count = len(
        _declared_reference_resources(
            graph=graph,
            type_iris=REFERENCE_ONTOLOGY_CLASS_TYPES,
        )
    )
    property_count = len(
        _declared_reference_resources(
            graph=graph,
            type_iris=frozenset(
                type_iri for _, type_iri in REFERENCE_ONTOLOGY_PROPERTY_TYPES
            ),
        )
    )
    individual_count = len(
        _declared_reference_resources(
            graph=graph,
            type_iris=frozenset({OWL.NamedIndividual}),
        )
    )
    return (
        "Ontology_Classes, Ontology_Properties, and Ontology_Individuals list "
        f"the {class_count} classes, {property_count} properties, and "
        f"{individual_count} named individuals in the exact frozen reference "
        f"ontology (SHA-256: {reference_ontology.sha256}). It was the complete "
        "context for workflow_full_ontology. Retrieval-condition rows received "
        "only per-regest subsets, which are deliberately not shown because they "
        "would reveal conditions. Catalogue availability does not make an "
        "assertion historically required; this experiment also permitted newly "
        "minted ontology terms."
    )


def _schema_declarations(
    *, rows: list[dict[str, Any]], reference_iris: set[URIRef]
) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for row in rows:
        turtle_text = _raw_turtle_from_row(row)
        if not turtle_text:
            continue
        try:
            graph = _parse_generated_turtle(turtle_text)
        except Exception:
            continue
        for subject, _, schema_type in graph.triples((None, RDF.type, None)):
            if not isinstance(schema_type, URIRef):
                continue
            kind = SCHEMA_TYPES.get(schema_type)
            if kind is None or not isinstance(subject, URIRef):
                continue
            labels = [
                str(value) for value in graph.objects(subject, RDFS.label)
            ]
            definitions = [
                str(value) for value in graph.objects(subject, SKOS.definition)
            ]
            declarations.append(
                {
                    "regest_id": row["regest_id"],
                    "condition": row["condition"],
                    "declaration_iri": str(subject),
                    "declaration_kind": kind,
                    "declared_as": str(schema_type),
                    "label": " | ".join(labels),
                    "definition": " | ".join(definitions),
                    "reference_iri_reused": subject in reference_iris,
                    "raw_ttl_artifact_path": row.get("raw_ttl_artifact_path"),
                }
            )
    return declarations


def _raw_turtle_from_row(row: dict[str, Any]) -> str:
    """Read exact generated Turtle from the authoritative raw JSON payload.

    :param row: Raw result object enriched with artifact paths.
    :return: Captured Stage-2 output without repair, or an empty string.
    """
    direct_output = row.get("raw_ttl_output")
    if isinstance(direct_output, str) and direct_output:
        return direct_output
    return ""


def _parse_generated_turtle(turtle: str) -> Graph:
    graph = Graph()
    payload = (
        turtle if "@prefix" in turtle else f"{TURTLE_PREFIXES}\n\n{turtle}"
    )
    graph.parse(data=payload, format="turtle")
    return graph


def _attach_observation_metrics(
    *, rows: list[dict[str, Any]], declarations: list[dict[str, Any]]
) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for declaration in declarations:
        grouped[(declaration["condition"], declaration["regest_id"])].append(
            declaration
        )
    for row in rows:
        schema_rows = grouped[(row["condition"], row["regest_id"])]
        reused = sum(item["reference_iri_reused"] for item in schema_rows)
        row["schema_declaration_count"] = len(schema_rows)
        row["schema_reference_iri_reuse_count"] = reused
        row["novel_schema_declaration_count"] = len(schema_rows) - reused
        row["schema_reference_iri_reuse_share"] = (
            reused / len(schema_rows) if schema_rows else None
        )
        row["generated_classes"] = " | ".join(
            item["declaration_iri"]
            for item in schema_rows
            if item["declaration_kind"] == "class"
        )
        row["generated_properties"] = " | ".join(
            item["declaration_iri"]
            for item in schema_rows
            if item["declaration_kind"] == "property"
        )


def _paired_rows(
    *,
    rows: list[dict[str, Any]],
    left: str,
    right: str,
    pair_name: str,
) -> list[dict[str, Any]]:
    by_key = {(row["condition"], row["regest_id"]): row for row in rows}
    regest_ids = sorted({str(row["regest_id"]) for row in rows})
    pairs: list[dict[str, Any]] = []
    for regest_id in regest_ids:
        left_row = by_key.get((left, regest_id))
        right_row = by_key.get((right, regest_id))
        left_valid = _quality_valid(left_row)
        right_valid = _quality_valid(right_row)
        pairs.append(
            {
                "pair": pair_name,
                "regest_id": regest_id,
                "left_condition": left,
                "right_condition": right,
                "left_present": left_row is not None,
                "right_present": right_row is not None,
                "left_success": _bool_field(left_row, "success"),
                "right_success": _bool_field(right_row, "success"),
                "left_turtle_valid": _bool_field(
                    left_row, "turtle_syntax_valid"
                ),
                "right_turtle_valid": _bool_field(
                    right_row, "turtle_syntax_valid"
                ),
                "left_failure_code": _text_field(left_row, "failure_code"),
                "right_failure_code": _text_field(right_row, "failure_code"),
                "left_error_message": _text_field(left_row, "error_message"),
                "right_error_message": _text_field(right_row, "error_message"),
                "left_stage2_output_reduced": _bool_field(
                    left_row, "stage2_output_reduced"
                ),
                "right_stage2_output_reduced": _bool_field(
                    right_row, "stage2_output_reduced"
                ),
                "valid_pair": left_valid and right_valid,
                "left_duration_seconds": _number(left_row, "duration_seconds"),
                "right_duration_seconds": _number(
                    right_row, "duration_seconds"
                ),
                "duration_delta_seconds": _paired_delta(
                    left_row, right_row, "duration_seconds"
                ),
                "left_reuse_share": _number(
                    left_row, "schema_reference_iri_reuse_share"
                ),
                "right_reuse_share": _number(
                    right_row, "schema_reference_iri_reuse_share"
                ),
                "reuse_share_delta": _paired_delta(
                    left_row, right_row, "schema_reference_iri_reuse_share"
                ),
                "left_novel_schema_declaration_count": _number(
                    left_row, "novel_schema_declaration_count"
                ),
                "right_novel_schema_declaration_count": _number(
                    right_row, "novel_schema_declaration_count"
                ),
                "left_triples": _number(left_row, "turtle_triple_count"),
                "right_triples": _number(right_row, "turtle_triple_count"),
                "left_schema_declaration_count": _number(
                    left_row, "schema_declaration_count"
                ),
                "right_schema_declaration_count": _number(
                    right_row, "schema_declaration_count"
                ),
                "condition_order": (
                    left_row.get("condition_order") if left_row else None
                ),
            }
        )
    return pairs


def _token_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize observed prompt and completion sizes by condition.

    :param rows: Normalized authoritative condition observations.
    :return: One readable token-accounting row for each condition.
    """
    summaries: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        selected = [row for row in rows if row["condition"] == condition]
        prompt_tokens = _numbers(selected, "prompt_tokens")
        output_tokens = _numbers(selected, "output_tokens")
        summaries.append(
            {
                "condition": condition,
                "observations": len(selected),
                "prompt_token_observations": len(prompt_tokens),
                "prompt_tokens_median": _median(prompt_tokens),
                "prompt_tokens_iqr": _iqr(prompt_tokens),
                "prompt_tokens_total": sum(prompt_tokens)
                if prompt_tokens
                else 0,
                "prompt_token_measure": (
                    "Full Stage-2 input before Turtle generation; excludes "
                    "the generated Turtle output."
                ),
                "output_token_observations": len(output_tokens),
                "output_tokens_median": _median(output_tokens),
                "output_tokens_iqr": _iqr(output_tokens),
                "output_tokens_total": sum(output_tokens)
                if output_tokens
                else 0,
                "output_token_measure": (
                    "Normalized output token count; see 04_Observations for "
                    "per-stage provider usage."
                ),
            }
        )
    return summaries


def _timing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timing: list[dict[str, Any]] = []
    for row in rows:
        context = row.get("ontology_context")
        context = context if isinstance(context, dict) else {}
        retrieved_turtle = context.get("retrieved_turtle")
        base = {
            "regest_id": row["regest_id"],
            "condition": row["condition"],
            "condition_order_position": row.get("condition_order_position"),
            "prompt_tokens": row.get("prompt_tokens"),
            "prompt_tokens_source": row.get("prompt_tokens_source"),
            "prompt_tokens_complete": row.get("prompt_tokens_complete"),
            "context_window_tokens": row.get(
                "context_mode_context_window_tokens"
            ),
            "retrieved_turtle_chars": (
                len(retrieved_turtle)
                if isinstance(retrieved_turtle, str)
                else None
            ),
            "context_window_adjustment": row.get("context_window_adjustment"),
            "stage1_context_reduced": row.get("stage1_context_reduced"),
            "stage1_context_reduction": row.get("stage1_context_reduction"),
            "stage2_output_reduction": row.get("stage2_output_reduction"),
            "provider_profile": row.get("provider_profile"),
        }
        metrics = row.get("stage_metrics")
        if isinstance(metrics, dict):
            for stage, payload in metrics.items():
                if isinstance(payload, dict):
                    timing.append(
                        {
                            **base,
                            "stage": stage,
                            "duration_seconds": payload.get("duration_seconds"),
                            "timing_source": "client_wall_clock",
                            "provider_total_tokens": payload.get(
                                f"{stage}_provider_total_tokens"
                            ),
                        }
                    )
        workflow_scopes = row.get("stage_timings")
        if isinstance(workflow_scopes, dict):
            for scope, payload in workflow_scopes.items():
                if isinstance(payload, dict):
                    timing.append(
                        {
                            **base,
                            "stage": f"workflow_{scope}",
                            "duration_seconds": payload.get("duration_seconds"),
                            "timing_source": payload.get(
                                "timing_source", "opa_server_wall_clock"
                            ),
                            "timing_scope_includes": payload.get("includes"),
                            "provider_total_tokens": None,
                        }
                    )
        provider = row.get("provider_run_metadata")
        if isinstance(provider, dict):
            for stage in ("stage1", "stage2"):
                stage_data = provider.get(stage)
                if isinstance(stage_data, dict):
                    usage = stage_data.get("usage")
                    timing.append(
                        {
                            **base,
                            "stage": f"workflow_{stage}",
                            "duration_seconds": None,
                            "timing_source": "not_exposed_by_dmw",
                            "prompt_tokens": (
                                usage.get("prompt_tokens")
                                if isinstance(usage, dict)
                                else None
                            ),
                            "provider_total_tokens": (
                                usage.get("total_tokens")
                                if isinstance(usage, dict)
                                else None
                            ),
                        }
                    )
        annotation = row.get("annotation_preparation")
        if isinstance(annotation, dict):
            timing.append(
                {
                    **base,
                    "stage": "annotation_preparation",
                    "duration_seconds": annotation.get("total_elapsed_seconds"),
                    "timing_source": "dmw_annotation_preparation",
                    "provider_total_tokens": None,
                }
            )
        timing.append(
            {
                **base,
                "stage": "condition_total",
                "duration_seconds": row.get("duration_seconds"),
                "timing_source": row.get(
                    "duration_measure", "condition_wall_clock"
                ),
                "provider_total_tokens": row.get(
                    "ontology_provider_total_tokens"
                ),
            }
        )
    return timing


def _summary_rows(
    *,
    rows: list[dict[str, Any]],
    pair_dmw: list[dict[str, Any]],
    pair_system: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        selected = [row for row in rows if row["condition"] == condition]
        received_turtle = [
            row
            for row in selected
            if isinstance(row.get("turtle_syntax_valid"), bool)
        ]
        valid_outputs = [
            row for row in selected if row.get("turtle_syntax_valid") is True
        ]
        schema = [
            row
            for row in valid_outputs
            if isinstance(row.get("schema_reference_iri_reuse_share"), float)
        ]
        summaries.append(
            {
                "condition": condition,
                "observations": len(selected),
                "success_count": sum(
                    bool(row.get("success")) for row in selected
                ),
                "success_rate": _rate(
                    sum(bool(row.get("success")) for row in selected),
                    len(selected),
                ),
                "valid_completed_count": sum(
                    _quality_valid(row) for row in selected
                ),
                "valid_completed_rate": _rate(
                    sum(_quality_valid(row) for row in selected),
                    len(selected),
                ),
                "invalid_turtle_count": sum(
                    row.get("turtle_syntax_valid") is False
                    for row in received_turtle
                ),
                "received_turtle_count": len(received_turtle),
                "invalid_turtle_rate": _rate(
                    sum(
                        row.get("turtle_syntax_valid") is False
                        for row in received_turtle
                    ),
                    len(received_turtle),
                ),
                "stage2_output_reduced_count": sum(
                    row.get("stage2_output_reduced") is True for row in selected
                ),
                "stage2_output_reduction_rate": _rate(
                    sum(
                        row.get("stage2_output_reduced") is True
                        for row in selected
                    ),
                    len(selected),
                ),
                "stage1_context_reduced_count": sum(
                    row.get("stage1_context_reduced") is True
                    for row in selected
                ),
                "stage1_context_reduction_rate": _rate(
                    sum(
                        row.get("stage1_context_reduced") is True
                        for row in selected
                    ),
                    len(selected),
                ),
                "median_duration_seconds": _median(
                    _numbers(selected, "duration_seconds")
                ),
                "iqr_duration_seconds": _iqr(
                    _numbers(selected, "duration_seconds")
                ),
                "median_schema_reuse_share": _median(
                    _numbers(schema, "schema_reference_iri_reuse_share")
                ),
                "iqr_schema_reuse_share": _iqr(
                    _numbers(schema, "schema_reference_iri_reuse_share")
                ),
                "pooled_schema_reuse_numerator": sum(
                    int(row.get("schema_reference_iri_reuse_count") or 0)
                    for row in valid_outputs
                ),
                "pooled_schema_reuse_denominator": sum(
                    int(row.get("schema_declaration_count") or 0)
                    for row in valid_outputs
                ),
                "novel_schema_declaration_count": sum(
                    int(row.get("novel_schema_declaration_count") or 0)
                    for row in valid_outputs
                ),
                "dmw_full_vs_rag_valid_pairs": _pair_denominator(pair_dmw),
                "workflow_rag_vs_haiu_rag_valid_pairs": _pair_denominator(
                    pair_system
                ),
            }
        )
    return summaries


def _write_main_workbook(
    *,
    path: Path,
    manifest: dict[str, Any],
    provenance: dict[str, Any],
    partial: bool,
    summary_rows: list[dict[str, Any]],
    pair_dmw: list[dict[str, Any]],
    pair_system: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    timing_rows: list[dict[str, Any]],
    token_rows: list[dict[str, Any]],
    declarations: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> None:
    workbook = xlsxwriter.Workbook(path, {"strings_to_urls": False})
    try:
        formats = _formats(workbook)
        about: Any = workbook.add_worksheet("00_About")
        about.set_column(0, 0, 28)
        about.set_column(1, 1, 100)
        about.write(0, 0, "DMW–Haiu Qwen 3.6 27B comparison", formats["title"])
        about.write(2, 0, "Status", formats["header"])
        about.write(
            2,
            1,
            "PARTIAL DIAGNOSTIC EXPORT"
            if partial
            else "Completed analysis export",
            formats["warning"] if partial else formats["success"],
        )
        about.write(4, 0, "Primary comparison 1", formats["header"])
        about.write(4, 1, "workflow_full_ontology vs workflow_rag")
        about.write(5, 0, "Primary comparison 2", formats["header"])
        about.write(5, 1, "workflow_rag vs haiu_rag_ontologizer")
        about.write(6, 0, "Provider profile", formats["header"])
        about.write(
            6,
            1,
            json.dumps(
                manifest.get("provider_profile", {}), ensure_ascii=False
            ),
        )
        about.write(7, 0, "Conditions", formats["header"])
        about.write(
            7,
            1,
            ", ".join(str(item) for item in manifest.get("conditions", [])),
        )
        about.write(9, 0, "Provenance", formats["header"])
        about.write(
            9, 1, json.dumps(provenance.get("inputs", {}), ensure_ascii=False)
        )
        _write_table(workbook, "01_Results", summary_rows, formats, "results")
        _write_table(workbook, "02_DMW_Context_AB", pair_dmw, formats, "dmw_ab")
        _write_table(
            workbook, "03_DMW_vs_Haiu_RAG", pair_system, formats, "system_ab"
        )
        _write_table(
            workbook, "04_Observations", observations, formats, "observations"
        )
        _write_table(
            workbook, "05_Timing_Context", timing_rows, formats, "timing"
        )
        _write_table(
            workbook, "06_Schema_Declarations", declarations, formats, "schema"
        )
        _write_table(
            workbook,
            "07_Novel_Declarations",
            [row for row in declarations if not row["reference_iri_reused"]],
            formats,
            "novel",
        )
        _write_table(
            workbook,
            "08_Exploratory_Cases",
            observations,
            formats,
            "exploratory",
        )
        _write_table(
            workbook, "09_Token_Accounting", token_rows, formats, "tokens"
        )
        _write_table(
            workbook, "99_Definitions", definitions, formats, "definitions"
        )
    finally:
        workbook.close()


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
    """Parse one canonical raw-Turtle sidecar while retaining source order.

    :param run_dir: Root directory of the experiment run.
    :param row: Observation that identifies the canonical Turtle sidecar.
    :return: Parsed source-ordered graph, or None when the sidecar is absent
        or not valid Turtle.
    """
    relative = row.get("raw_ttl_artifact_path")
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


def _formats(workbook: Any) -> dict[str, Any]:
    return {
        "title": workbook.add_format(
            {"bold": True, "font_size": 14, "font_color": "#17365D"}
        ),
        "header": workbook.add_format(
            {"bold": True, "bg_color": "#D9EAF7", "border": 1}
        ),
        "success": workbook.add_format({"bg_color": "#E2F0D9", "bold": True}),
        "warning": workbook.add_format({"bg_color": "#FCE4D6", "bold": True}),
        "true": workbook.add_format({"bg_color": "#C6EFCE"}),
        "reduced": workbook.add_format({"bg_color": "#FFEB9C"}),
        "wrap": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "review_cell": workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top"}
        ),
        "merged_regest": workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top"}
        ),
        "review_not_shared": workbook.add_format({"underline": True}),
        "review_not_shared_cell": workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top", "underline": True}
        ),
        "review_unique": workbook.add_format({"bold": True, "underline": True}),
        "review_unique_cell": workbook.add_format(
            {
                "border": 1,
                "text_wrap": True,
                "valign": "top",
                "bold": True,
                "underline": True,
            }
        ),
        "relationship_subject": workbook.add_format({"font_color": "#1F4E78"}),
        "relationship_subject_not_shared": workbook.add_format(
            {"font_color": "#1F4E78", "underline": True}
        ),
        "relationship_subject_unique": workbook.add_format(
            {"font_color": "#1F4E78", "bold": True, "underline": True}
        ),
        "relationship_predicate": workbook.add_format(
            {"font_color": "#C65911"}
        ),
        "relationship_predicate_not_shared": workbook.add_format(
            {"font_color": "#C65911", "underline": True}
        ),
        "relationship_predicate_unique": workbook.add_format(
            {"font_color": "#C65911", "bold": True, "underline": True}
        ),
        "relationship_object": workbook.add_format({"font_color": "#7030A0"}),
        "relationship_object_not_shared": workbook.add_format(
            {"font_color": "#7030A0", "underline": True}
        ),
        "relationship_object_unique": workbook.add_format(
            {"font_color": "#7030A0", "bold": True, "underline": True}
        ),
        "review_input": workbook.add_format(
            {
                "border": 1,
                "bg_color": "#FFF2CC",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "numeric_input": workbook.add_format(
            {
                "border": 1,
                "bg_color": "#FFF2CC",
                "align": "center",
                "valign": "top",
            }
        ),
    }


def _write_table(
    workbook: Any,
    name: str,
    rows: list[dict[str, Any]],
    formats: dict[str, Any],
    table_name: str,
) -> None:
    sheet = workbook.add_worksheet(name)
    _write_rows(sheet, rows, formats, table_name)


def _write_rows(
    sheet: Any,
    rows: list[dict[str, Any]],
    formats: dict[str, Any],
    table_name: str,
    *,
    start_row: int = 0,
) -> None:
    headers = _fieldnames(rows)
    sheet.freeze_panes(start_row + 1, 0)
    sheet.set_default_row(18)
    if not headers:
        sheet.write(start_row, 0, "No rows", formats["warning"])
        return
    for column, header in enumerate(headers):
        sheet.write(start_row, column, header, formats["header"])
        width = min(max(len(header) + 2, 14), 38)
        sheet.set_column(column, column, width, formats["wrap"])
    for row_index, row in enumerate(rows, start=start_row + 1):
        for column, header in enumerate(headers):
            value = row.get(header)
            _write_value(sheet, row_index, column, value, formats)
    if rows:
        sheet.add_table(
            start_row,
            0,
            start_row + len(rows),
            len(headers) - 1,
            {
                "name": _safe_table_name(table_name),
                "style": "Table Style Medium 2",
                "columns": [{"header": header} for header in headers],
            },
        )
        _apply_quality_formatting(
            sheet,
            headers,
            start_row + 1,
            len(rows),
            formats,
        )


def _write_value(
    sheet: Any,
    row: int,
    column: int,
    value: Any,
    formats: dict[str, Any],
) -> None:
    if isinstance(value, bool):
        sheet.write_boolean(row, column, value)
    elif isinstance(value, int | float):
        sheet.write_number(row, column, value)
    elif value is None:
        sheet.write_blank(row, column, None)
    elif isinstance(value, (dict, list)):
        sheet.write(
            row, column, json.dumps(value, ensure_ascii=False), formats["wrap"]
        )
    else:
        sheet.write(row, column, str(value), formats["wrap"])


def _apply_quality_formatting(
    sheet: Any,
    headers: list[str],
    first_row: int,
    count: int,
    formats: dict[str, Any],
) -> None:
    for field, format_key in (
        ("success", "true"),
        ("turtle_syntax_valid", "true"),
        ("stage1_context_reduced", "reduced"),
        ("stage2_output_reduced", "reduced"),
        ("reference_iri_reused", "true"),
    ):
        if field in headers:
            column = headers.index(field)
            sheet.conditional_format(
                first_row,
                column,
                first_row + count - 1,
                column,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": True,
                    "format": formats[format_key],
                },
            )


def _metric_definitions() -> list[dict[str, Any]]:
    return [
        {
            "metric": "total_input_tokens_for_turtle_generation",
            "calculation": (
                "One full Stage-2 Turtle-generation input. Retained Stage-1 "
                "user input and plan are included; the replaced Stage-1 "
                "system prompt and generated Turtle response are excluded. "
                "Do not sum Stage-1 and Stage-2 input counts."
            ),
            "source": (
                "Provider usage: generation_budget.stage2.provider_prompt_tokens. "
                "Fallback only: local Stage-2 full-context estimate, marked "
                "prompt_tokens_source=estimated."
            ),
        },
        {
            "metric": "input_token_plot_population",
            "calculation": (
                "Successful rows with a complete numeric Stage-2 input "
                "measurement; trajectories require both conditions. Turtle "
                "syntax validity is not required for this resource metric."
            ),
            "source": "04_Observations.success, prompt_tokens_complete, and prompt_tokens",
        },
        {
            "metric": "output_tokens",
            "calculation": (
                "Stage-1 planning response plus Stage-2 Turtle response; "
                "shown separately from final-generation input."
            ),
            "source": "04_Observations.output_tokens",
        },
        {
            "metric": "invalid_turtle_rate",
            "calculation": "Raw Stage-2 Turtle parser failures / received Stage-2 outputs.",
            "source": "raw_ttl plus turtle_syntax_valid",
        },
        {
            "metric": "stage1_context_reduction_rate",
            "calculation": "Explicit OPA Stage-1 context-window adjustment / attempted observations.",
            "source": "stage1_context_reduced and stage1_context_reduction",
        },
        {
            "metric": "stage2_output_reduction_rate",
            "calculation": "Explicit OPA Stage-2 context-window adjustment / attempted observations.",
            "source": "stage2_output_reduced and stage2_output_reduction",
        },
        {
            "metric": "schema_reference_iri_reuse_share",
            "calculation": "Declared class/property URIRefs that occur in frozen full reference ontology / all declared schema URIRefs.",
            "source": "raw_ttl and provenance/reference_ontology",
        },
        {
            "metric": "novel_schema_declaration",
            "calculation": "Generated class/property URIRef absent from frozen full reference ontology; ABox individual IRIs are excluded.",
            "source": "06_Schema_Declarations",
        },
        {
            "metric": "duration_seconds",
            "calculation": "Observed client wall-clock condition attempt time; it is not provider compute time.",
            "source": "raw condition payload and stage_metrics",
        },
        {
            "metric": "median_and_iqr",
            "calculation": "Median and linear-interpolated IQR over displayed numeric observations; empty populations remain blank.",
            "source": "01_Results condition metrics",
        },
        {
            "metric": "retrieval_sidecar_completeness",
            "calculation": "Both pre-LLM retrieval Turtle and YAML sidecars must exist for every retrieval condition observation.",
            "source": "raw_ttl/haiu_retrieved/<condition>/<regest_id>.ttl|yaml",
        },
        {
            "metric": "valid_pair",
            "calculation": "Both named condition outputs succeeded and parsed as Turtle for the same regest/provider.",
            "source": "02_DMW_Context_AB and 03_DMW_vs_Haiu_RAG",
        },
    ]


def _raw_ttl_path(
    layout: _RunLayout, condition: str, regest_id: str
) -> str | None:
    path = layout.output / f"result-{condition}" / f"{regest_id}.ttl"
    return path.relative_to(layout.root).as_posix() if path.is_file() else None


def _prepare_output_dir(
    output_dir: Path,
    *,
    overwrite: bool,
    previous_output_filenames: Iterable[str] = (),
) -> None:
    """Create a compact analysis directory without deleting user files.

    :param output_dir: Derived-analysis directory.
    :param overwrite: Replace files owned by this exporter.
    :param previous_output_filenames: Additional filenames owned by an older
        compatible export layout.
    :raises ValueError: If an existing non-empty directory lacks approval.
    """
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise ValueError(
            f"Output directory is not empty: {output_dir}. Use --overwrite "
            "to replace known derived-export files."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        return
    for filename in (
        *CORE_OUTPUT_FILENAMES,
        *PREVIOUS_OUTPUT_FILENAMES,
        *previous_output_filenames,
    ):
        path = output_dir / filename
        if path.is_file():
            path.unlink()
    audit_dir = output_dir / "audit_csv"
    if audit_dir.is_dir():
        for filename in AUDIT_CSV_FILENAMES:
            path = audit_dir / filename
            if path.is_file():
                path.unlink()
        if not any(audit_dir.iterdir()):
            audit_dir.rmdir()


def _write_audit_csv(
    *,
    analysis_dir: Path,
    observations: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    declarations: list[dict[str, Any]],
    audit_csv: bool,
) -> list[Path]:
    """Write the minimal non-duplicative audit dataset when requested.

    :param analysis_dir: Reader-facing analysis directory.
    :param observations: Per-condition normalized observation rows.
    :param pairs: All paired-comparison rows.
    :param declarations: Schema declaration rows.
    :param audit_csv: Whether the caller requested audit tables.
    :return: Emitted audit CSV paths.
    """
    if not audit_csv:
        return []
    audit_dir = analysis_dir / "audit_csv"
    audit_dir.mkdir(exist_ok=True)
    paths = {
        "observations": audit_dir / "observations.csv",
        "pairs": audit_dir / "pairs.csv",
        "schema_declarations": audit_dir / "schema_declarations.csv",
    }
    _write_csv(paths["observations"], observations)
    _write_csv(
        paths["pairs"],
        [
            {
                **row,
                "comparison": row.get("comparison") or row.get("pair"),
            }
            for row in pairs
        ],
    )
    _write_csv(paths["schema_declarations"], declarations)
    return list(paths.values())


def _write_analysis_readme(
    *,
    path: Path,
    title: str,
    status: str,
    audit_csv: bool,
    review_artifacts: tuple[str, ...] = (
        "`masked_historian_quality_review.xlsx`: condition-masked resource "
        "and relationship review rows for complete valid triplets and valid "
        "planned two-condition pairs.",
        "`masked_historian_quality_review_evaluation_sidecar.xlsx`: "
        "`Review_Guide` and frozen ontology catalogue sheets for the "
        "companion review workbook.",
        "`historian_quality_review_reveal_key.json`: condition labels for "
        "the historian review; do not share it with reviewers.",
    ),
) -> None:
    """Write the reader-oriented entry point for an analysis directory.

    :param path: Markdown target path.
    :param title: Analysis title.
    :param status: Publication or diagnostic status.
    :param audit_csv: Whether the optional audit tables were emitted.
    :param review_artifacts: Descriptions of review files created by this
        export variant.
    """
    audit_status = (
        "`audit_csv/` contains observations, pairs, and schema declarations."
        if audit_csv
        else "No audit CSV files were requested; re-export with `--audit-csv` "
        "for machine-readable audit tables."
    )
    path.write_text(
        "\n".join(
            (
                f"# {title}",
                "",
                "Start with `overview.xlsx`.",
                "",
                f"**Status:** {status}",
                "",
                *(f"- {artifact}" for artifact in review_artifacts),
                "- `analysis_manifest.json`: source hashes, metrics, and output hashes.",
                f"- {audit_status}",
                "",
                "> [!WARNING]",
                "> Copy a completed review workbook outside `analysis/` "
                "before using `--overwrite`; the exporter replaces its own outputs.",
                "",
                "The experiment's raw artifacts remain authoritative.",
                "",
            )
        ),
        encoding="utf-8",
    )


def _load_json(path: Path, *, allow_missing: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if allow_missing:
            return {}
        raise ValueError(f"Missing required JSON artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _fieldnames(rows: Iterable[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def _condition_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        condition: sum(row["condition"] == condition for row in rows)
        for condition in CONDITIONS
    }


def _pair_denominator(rows: list[dict[str, Any]]) -> int:
    return sum(bool(row["valid_pair"]) for row in rows)


def _quality_valid(row: dict[str, Any] | None) -> bool:
    return bool(
        row and row.get("success") and row.get("turtle_syntax_valid") is True
    )


def _bool_field(row: dict[str, Any] | None, key: str) -> bool | None:
    value = row.get(key) if row else None
    return value if isinstance(value, bool) else None


def _text_field(row: dict[str, Any] | None, key: str) -> str | None:
    """Return a non-empty text field from an optional raw result row.

    :param row: Observation row, if present.
    :param key: Raw result field name.
    :return: Text value, or ``None`` when not exposed.
    """
    value = row.get(key) if row else None
    return value if isinstance(value, str) and value else None


def _number(row: dict[str, Any] | None, key: str) -> int | float | None:
    value = row.get(key) if row else None
    return (
        value
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _paired_delta(
    left: dict[str, Any] | None, right: dict[str, Any] | None, key: str
) -> float | None:
    left_value = _number(left, key)
    right_value = _number(right, key)
    if left_value is None or right_value is None:
        return None
    return float(right_value - left_value)


def _numbers(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [
        float(value) for row in rows if (value := _number(row, key)) is not None
    ]


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _iqr(values: list[float]) -> float | None:
    """Calculate the linear-interpolated interquartile range.

    :param values: Numeric observations from one condition.
    :return: Third quartile minus first quartile, or ``None`` without data.
    """
    if not values:
        return None
    ordered = sorted(values)
    return _quantile(ordered, 0.75) - _quantile(ordered, 0.25)


def _quantile(values: list[float], position: float) -> float:
    """Return one linear-interpolated sample quantile.

    :param values: Sorted non-empty observations.
    :param position: Quantile position between zero and one.
    :return: Interpolated quantile value.
    """
    index = (len(values) - 1) * position
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _rate(numerator: int, denominator: int) -> float | None:
    """Return a rate only when its denominator is defined.

    :param numerator: Count satisfying a condition.
    :param denominator: Population count.
    :return: Fraction, or ``None`` when no observations exist.
    """
    return numerator / denominator if denominator else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_table_name(value: str) -> str:
    return "tbl_" + "".join(char if char.isalnum() else "_" for char in value)


if __name__ == "__main__":
    raise SystemExit(main())
