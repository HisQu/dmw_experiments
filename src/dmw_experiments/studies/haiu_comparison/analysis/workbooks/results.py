#!/usr/bin/env python3
"""Export one comparison run into reproducible CSV and Excel analysis views."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import xlsxwriter
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ARTIFACT_SCHEMA_VERSION,
    ExecutionArtifactLayout,
    compatibility_prompt_key,
)
from dmw_experiments.studies.haiu_comparison.model.artifact_records import (
    load_upstream_payload,
    verify_artifact_references,
)
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
        current = self.output / "manifest.json"
        if current.is_file():
            return current
        return self.root / "environment" / f"{self.execution}-run-manifest.json"

    @property
    def provenance(self) -> Path:
        """Return the frozen input-provenance manifest for this provider."""
        current = self.output / "provenance" / "manifest.json"
        if current.is_file():
            return current
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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _write_historian_quality_review_workbook,
        _write_historian_review_guide,
    )

    layout = _RunLayout.from_output(run_dir)
    run_dir = layout.root
    manifest = _load_run_manifest(layout)
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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _write_historian_review_rows,
        _write_provider_historian_review_guide,
    )

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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _write_provider_historian_review_guide,
    )

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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _historian_review_packets,
    )

    layout = _RunLayout.from_output(run_dir)
    run_dir = layout.root
    run_manifest = _load_run_manifest(layout)
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
    artifact_layout = ExecutionArtifactLayout(raw_dir)
    result_paths: dict[tuple[str, str], Path] = {}
    for condition, result_path in artifact_layout.iter_result_records():
        result_paths[(condition, result_path.parent.name)] = result_path
    for condition, result_path in artifact_layout.iter_legacy_result_records():
        result_paths.setdefault((condition, result_path.stem), result_path)
    for (directory_condition, directory_regest_id), path in sorted(
        result_paths.items()
    ):
        record = _load_json(path)
        if record.get("schema_version") == ARTIFACT_SCHEMA_VERSION:
            verify_artifact_references(record, run_root=layout.root)
            payload = load_upstream_payload(record, run_root=layout.root)
            artifact_paths = _v3_row_artifact_paths(record)
        else:
            payload = record
            artifact_paths = _legacy_row_artifact_paths(
                layout=layout,
                condition=directory_condition,
                regest_id=directory_regest_id,
            )
        if not isinstance(payload, dict):
            raise ValueError(f"Raw result is not an object: {path}")
        condition = str(payload.get("condition") or directory_condition)
        regest_id = str(payload.get("regest_id") or directory_regest_id)
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
        row.update(artifact_paths)
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
        _attempt_checkpoint_path(
            layout=layout,
            condition=condition,
            regest_id=regest_id,
        ),
        allow_missing=True,
    )
    return attempt_state.get("status") == "retry_pending"


def _validate_raw_contract(
    *, layout: _RunLayout, rows: list[dict[str, Any]], allow_partial: bool
) -> None:
    expected_ids = {
        str(value) for value in _load_run_manifest(layout).get("regest_ids", [])
    }
    observed: set[tuple[str, str]] = set()
    failures: list[str] = []
    for row in rows:
        condition = str(row["condition"])
        regest_id = str(row["regest_id"])
        observed.add((condition, regest_id))
        if condition in RETRIEVAL_CONDITIONS:
            for label in (
                "retrieved_ttl_artifact_path",
                "retrieved_yaml_artifact_path",
            ):
                relative = row.get(label)
                if (
                    not isinstance(relative, str)
                    or not (layout.root / relative).is_file()
                ):
                    failures.append(
                        "missing retrieval evidence: "
                        f"{condition}/{regest_id}/{label}"
                    )
        if bool(row.get("success")) and (
            not isinstance(row.get("raw_ttl_artifact_path"), str)
            or not (layout.root / str(row["raw_ttl_artifact_path"])).is_file()
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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _primary_label,
    )

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
    label = reference_ontology.labels.get(resource)
    if label is not None:
        return label
    fragment = frag_uri(resource)
    return fragment if fragment is not None else str(resource)


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
    from dmw_experiments.studies.haiu_comparison.analysis.workbooks.historian import (
        _primary_label,
    )

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
    v3_path = layout.output / f"result-{condition}" / regest_id / "ontology.ttl"
    if v3_path.is_file():
        return v3_path.relative_to(layout.root).as_posix()
    legacy_path = layout.output / f"result-{condition}" / f"{regest_id}.ttl"
    return (
        legacy_path.relative_to(layout.root).as_posix()
        if legacy_path.is_file()
        else None
    )


def _attempt_checkpoint_path(
    *, layout: _RunLayout, condition: str, regest_id: str
) -> Path:
    """Resolve a v3 checkpoint or its pre-v3 predecessor.

    :param layout: Provider execution paths.
    :param condition: Stable scientific condition identifier.
    :param regest_id: Stable input-unit identifier.
    :return: Existing checkpoint when found, otherwise the v3 location.
    """
    v3_path = (
        layout.output
        / f"intermediates-{condition}"
        / regest_id
        / "checkpoint.json"
    )
    if v3_path.is_file():
        return v3_path
    legacy_path = (
        layout.output
        / f"intermediates-{condition}"
        / f"{regest_id}.attempt.json"
    )
    return legacy_path if legacy_path.is_file() else v3_path


def _legacy_row_artifact_paths(
    *, layout: _RunLayout, condition: str, regest_id: str
) -> dict[str, Any]:
    """Locate sidecars used by a pre-v3 flat terminal result.

    :param layout: Provider execution paths.
    :param condition: Stable scientific condition identifier.
    :param regest_id: Stable input-unit identifier.
    :return: Compatibility artifact fields used by validation and analysis.
    """
    intermediate = layout.output / f"intermediates-{condition}"
    retrieval_ttl = intermediate / f"{regest_id}.retrieved.ttl"
    retrieval_yaml = intermediate / f"{regest_id}.retrieved.yaml"
    stage1_candidates = sorted(intermediate.glob(f"{regest_id}.*.md"))
    prompt_prefix = f"{regest_id}_"
    prompt_paths = {
        path.stem.removeprefix(prompt_prefix): path.relative_to(
            layout.root
        ).as_posix()
        for path in sorted(intermediate.glob(f"{regest_id}_*.md"))
    }
    return {
        "raw_ttl_artifact_path": _raw_ttl_path(
            layout,
            condition,
            regest_id,
        ),
        "raw_stage1_artifact_path": (
            stage1_candidates[-1].relative_to(layout.root).as_posix()
            if stage1_candidates
            else None
        ),
        "retrieved_ttl_artifact_path": (
            retrieval_ttl.relative_to(layout.root).as_posix()
            if retrieval_ttl.is_file()
            else None
        ),
        "retrieved_yaml_artifact_path": (
            retrieval_yaml.relative_to(layout.root).as_posix()
            if retrieval_yaml.is_file()
            else None
        ),
        "retrieval_sidecars_complete": (
            retrieval_ttl.is_file() and retrieval_yaml.is_file()
        ),
        "prompt_artifact_paths": prompt_paths,
    }


def _v3_row_artifact_paths(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten schema-v3 artifact references for existing analysis code.

    :param record: Parsed nested terminal record.
    :return: Legacy-compatible artifact path fields.
    """
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    retrieval = artifacts.get("retrieval")
    retrieval = retrieval if isinstance(retrieval, dict) else {}
    prompts = artifacts.get("prompts")
    prompt_paths = {
        compatibility_prompt_key(str(label)): path
        for label, reference in (
            prompts.items() if isinstance(prompts, dict) else ()
        )
        if (path := _v3_artifact_path_from_reference(reference)) is not None
    }
    return {
        "raw_ttl_artifact_path": _v3_artifact_path(record, "stage2_response"),
        "raw_stage1_artifact_path": _v3_artifact_path(
            record, "stage1_response"
        ),
        "retrieved_ttl_artifact_path": _v3_artifact_path_from_reference(
            retrieval.get("context")
        ),
        "retrieved_yaml_artifact_path": _v3_artifact_path_from_reference(
            retrieval.get("metadata")
        ),
        "retrieval_snapshot_fidelity": retrieval.get("snapshot_fidelity"),
        "retrieval_sidecars_complete": bool(
            _v3_artifact_path_from_reference(retrieval.get("context"))
            and _v3_artifact_path_from_reference(retrieval.get("metadata"))
        ),
        "prompt_artifact_paths": prompt_paths,
    }


def _v3_artifact_path(record: dict[str, Any], role: str) -> str | None:
    """Read one run-relative path from a schema-v3 artifact role.

    :param record: Parsed nested terminal record.
    :param role: Semantic artifact key.
    :return: Portable path or ``None``.
    """
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    return _v3_artifact_path_from_reference(artifacts.get(role))


def _v3_artifact_path_from_reference(reference: Any) -> str | None:
    """Read one path from an optional schema-v3 artifact reference.

    :param reference: Candidate artifact dictionary.
    :return: Portable path or ``None``.
    """
    if not isinstance(reference, dict):
        return None
    path = reference.get("path")
    return path if isinstance(path, str) and path else None


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


def _load_run_manifest(layout: _RunLayout) -> dict[str, Any]:
    """Load the scientific contract from either manifest format.

    :param layout: Provider execution paths.
    :return: Immutable scientific run identity.
    :raises ValueError: If a schema-v3 wrapper lacks its run object.
    """
    record = _load_json(layout.manifest)
    if record.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        return record
    run_manifest = record.get("run")
    if not isinstance(run_manifest, dict):
        raise ValueError("Schema-v3 execution manifest has no run object.")
    return run_manifest


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
