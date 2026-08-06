#!/usr/bin/env python3
"""Export the historical Haiu 1.7.3 pilot as clearly limited analysis views.

The normal workbook exporter intentionally rejects this pilot because its
workflow records do not preserve the exact Stage-2 response or a frozen
provenance manifest. This adapter reads the historical sidecars without
modifying them and makes every missing modern contract field visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import xlsxwriter
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from dmw_experiments.studies.haiu_comparison import (
    export_results_workbook as strict_export,
)
from dmw_experiments.studies.haiu_comparison.data_collection.measurements import (
    _TURTLE_PREFIXES,
)


LEGACY_CONDITIONS = (
    "workflow_full_ontology",
    "workflow_rag",
    "direct_llm_raw_regest",
)
WORKFLOW_CONDITIONS = frozenset({"workflow_full_ontology", "workflow_rag"})
SCHEMA_TYPES = {
    OWL.Class: "class",
    RDFS.Class: "class",
    OWL.ObjectProperty: "property",
    OWL.DatatypeProperty: "property",
    RDF.Property: "property",
}
REFERENCE_BLOCK = re.compile(
    r"## Referenzontologie \(Ausschnitt, Turtle\).*?```ttl\n(.*?)\n```",
    flags=re.DOTALL,
)
LEGACY_PREVIOUS_OUTPUT_FILENAMES = (
    "legacy_preliminary_overview.xlsx",
    "legacy_preliminary_masked_case_review.xlsx",
    "legacy_preliminary_reveal_key.json",
    "legacy_preliminary_analysis_manifest.json",
    "condition_summary.csv",
    "dmw_context_ab.csv",
    "legacy_direct_context.csv",
    "observations.csv",
    "timing_context.csv",
    "schema_declarations.csv",
    "novel_declarations.csv",
    "historian_cases.csv",
    "metric_definitions.csv",
)


@dataclass(frozen=True, slots=True)
class LegacyExportPaths:
    """Paths created by one legacy pilot export.

    :param workbook: Main overview workbook with condition labels.
    :param review_workbook: Condition-masked case-review workbook.
    :param reveal_key: Mapping from masked review identifiers to artifacts.
    :param manifest: Source-hash and calculation manifest.
    :param readme: Reader-orientation file in the analysis directory.
    """

    workbook: Path
    review_workbook: Path
    reveal_key: Path
    manifest: Path
    readme: Path


@dataclass(frozen=True, slots=True)
class ReferenceContext:
    """Prompt-derived reference ontology evidence for the legacy diagnostic.

    :param turtle: Exact Turtle text found in the historical planner prompt.
    :param sha256: Digest of the embedded Turtle text.
    :param uri_refs: URIRefs occurring anywhere in the reference graph.
    :param source_rows: Raw observations that attested the same reference hash.
    """

    turtle: str
    sha256: str
    uri_refs: frozenset[URIRef]
    source_rows: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    """Run the legacy pilot workbook exporter.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    paths = export_legacy_run(
        Path(args.run_dir),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        audit_csv=args.audit_csv,
        overwrite=args.overwrite,
    )
    print(f"Wrote legacy preliminary workbook: {paths.workbook}")
    return 0


def export_legacy_run(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
    audit_csv: bool = False,
    overwrite: bool = False,
) -> LegacyExportPaths:
    """Create a non-publication workbook from historical pilot artifacts.

    The function never writes below the input artifact directories. It rejects
    a changed prompt-derived reference ontology rather than guessing which
    reference graph the old run saw.

    :param run_dir: Historical run directory containing raw artifacts.
    :param output_dir: Derived-analysis directory, defaulting to
        ``<run_dir>/analysis_preliminary``.
    :param audit_csv: Write compact machine-readable audit tables.
    :param overwrite: Permit replacement of known derived-analysis files.
    :return: Paths to the generated analysis artifacts.
    :raises ValueError: If the historical source does not support a bounded
        preliminary diagnostic.
    """
    run_dir = run_dir.resolve()
    manifest = _load_json(run_dir / "summaries" / "run_manifest.json")
    _validate_legacy_manifest(manifest)
    raw_rows = _load_legacy_raw_rows(run_dir)
    reference = _reference_context(raw_rows)
    observations = _build_observations(run_dir, raw_rows)
    declarations = _schema_declarations(
        run_dir=run_dir,
        observations=observations,
        reference_iris=reference.uri_refs,
    )
    condition_summary = _condition_summary(
        observations=observations,
        declarations=declarations,
        planned_regest_count=len(manifest.get("regest_ids", [])),
    )
    pairs = _dmw_context_pairs(observations)
    direct_context = _direct_context_rows(observations)
    timing_rows = _timing_rows(observations)
    historian_cases = _historian_cases(observations)
    definitions = _metric_definitions()
    source_hashes = _source_hashes(run_dir)

    output_dir = (
        output_dir.resolve()
        if output_dir is not None
        else run_dir / "analysis_preliminary"
    )
    strict_export._prepare_output_dir(
        output_dir,
        overwrite=overwrite,
        previous_output_filenames=LEGACY_PREVIOUS_OUTPUT_FILENAMES,
    )
    paths = _output_paths(output_dir)

    _write_main_workbook(
        path=paths.workbook,
        manifest=manifest,
        reference=reference,
        condition_summary=condition_summary,
        pairs=pairs,
        direct_context=direct_context,
        observations=observations,
        timing_rows=timing_rows,
        declarations=declarations,
        historian_cases=historian_cases,
        definitions=definitions,
    )
    reveal_key = _write_masked_case_review(
        path=paths.review_workbook,
        observations=observations,
        manifest=manifest,
        run_dir=run_dir,
    )
    strict_export._write_json(paths.reveal_key, reveal_key)
    strict_export._write_analysis_readme(
        path=paths.readme,
        title="Preliminary legacy pilot analysis",
        status="PRELIMINARY LEGACY PILOT — NOT PUBLICATION EVIDENCE",
        audit_csv=audit_csv,
        review_artifacts=(
            "`masked_case_review.xlsx`: condition-masked qualitative review.",
            "`reveal_key.json`: condition labels for the masked review.",
        ),
    )
    audit_paths = strict_export._write_audit_csv(
        analysis_dir=output_dir,
        pairs=pairs,
        observations=observations,
        declarations=declarations,
        audit_csv=audit_csv,
    )
    analysis_manifest = _analysis_manifest(
        run_dir=run_dir,
        manifest=manifest,
        reference=reference,
        source_hashes=source_hashes,
        condition_summary=condition_summary,
        pairs=pairs,
        output_dir=output_dir,
        audit_csv=audit_csv,
        audit_paths=audit_paths,
    )
    strict_export._write_json(paths.manifest, analysis_manifest)
    return paths


def _parser() -> argparse.ArgumentParser:
    """Build the legacy-export command-line interface.

    :return: Argument parser for the standalone adapter.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Create a clearly labelled preliminary workbook from the historical "
            "Haiu 1.7.3 pilot."
        )
    )
    parser.add_argument("run_dir", help="Legacy comparison run directory.")
    parser.add_argument(
        "--output-dir",
        help="Derived-analysis directory; default is RUN_DIR/analysis_preliminary.",
    )
    parser.add_argument(
        "--audit-csv",
        action="store_true",
        help="Write observations, pairs, and schema declarations under audit_csv/.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace only previously generated legacy-analysis files.",
    )
    return parser


def _validate_legacy_manifest(manifest: dict[str, Any]) -> None:
    """Reject runs that are not the documented three-condition legacy layout.

    :param manifest: Legacy ``run_manifest.json`` payload.
    :raises ValueError: If the historical condition layout is not recognised.
    """
    conditions = manifest.get("conditions")
    if not isinstance(conditions, list) or set(conditions) != set(
        LEGACY_CONDITIONS
    ):
        raise ValueError(
            "Legacy adapter requires conditions "
            f"{', '.join(LEGACY_CONDITIONS)}."
        )


def _load_legacy_raw_rows(run_dir: Path) -> list[dict[str, Any]]:
    """Load raw legacy observations without normalising their original fields.

    :param run_dir: Historical run directory.
    :return: Raw rows enriched with condition, ID, and artifact paths.
    :raises ValueError: If a required legacy raw directory is missing.
    """
    rows: list[dict[str, Any]] = []
    for condition in LEGACY_CONDITIONS:
        raw_dir = run_dir / "raw" / condition
        if not raw_dir.is_dir():
            raise ValueError(f"Missing legacy raw directory: {raw_dir}")
        for path in sorted(raw_dir.glob("*.json")):
            payload = _load_json(path)
            row = dict(payload)
            regest_id = str(row.get("regest_id") or path.stem)
            row["condition"] = str(row.get("condition") or condition)
            row["regest_id"] = regest_id
            row["raw_artifact_path"] = path.relative_to(run_dir).as_posix()
            row["raw_yaml_artifact_path"] = _relative_if_file(
                run_dir, run_dir / "raw_yaml" / condition / f"{regest_id}.yaml"
            )
            row["raw_ttl_artifact_path"] = _relative_if_file(
                run_dir, run_dir / "raw_ttl" / condition / f"{regest_id}.ttl"
            )
            if condition == "workflow_rag":
                retrieval_base = (
                    run_dir / "raw_ttl" / "haiu_retrieved" / regest_id
                )
                row["legacy_retrieval_ttl_artifact_path"] = _relative_if_file(
                    run_dir, retrieval_base.with_suffix(".ttl")
                )
                row["legacy_retrieval_yaml_artifact_path"] = _relative_if_file(
                    run_dir, retrieval_base.with_suffix(".yaml")
                )
            rows.append(row)
    if not rows:
        raise ValueError(f"No legacy raw JSON found under {run_dir / 'raw'}.")
    return rows


def _reference_context(rows: list[dict[str, Any]]) -> ReferenceContext:
    """Recover and verify the prompt-embedded full reference ontology.

    :param rows: Loaded legacy raw observations.
    :return: Hash-attested prompt-derived reference context.
    :raises ValueError: If the old prompt or reference hash is inconsistent.
    """
    candidates: list[tuple[str, str, str]] = []
    for row in rows:
        if (
            row["condition"] != "workflow_full_ontology"
            or row.get("success") is not True
        ):
            continue
        expected_hash = _recorded_reference_hash(row)
        prompt = _full_context_prompt(row)
        match = REFERENCE_BLOCK.search(prompt or "")
        if expected_hash is None or match is None:
            raise ValueError(
                "Successful full-context observation lacks an attested "
                "reference ontology prompt block."
            )
        turtle = match.group(1)
        actual_hash = _sha256_text(turtle)
        if actual_hash != expected_hash:
            raise ValueError(
                "Prompt-derived reference Turtle hash does not match recorded "
                f"ontology hash for {row['regest_id']}."
            )
        candidates.append((str(row["regest_id"]), turtle, actual_hash))
    if not candidates:
        raise ValueError(
            "No successful full-context observations are available."
        )
    hashes = {item[2] for item in candidates}
    turtle_texts = {item[1] for item in candidates}
    if len(hashes) != 1 or len(turtle_texts) != 1:
        raise ValueError(
            "Legacy full-context observations do not attest one common "
            "reference ontology."
        )
    turtle = candidates[0][1]
    graph = Graph()
    try:
        graph.parse(data=turtle, format="turtle")
    except Exception as error:
        raise ValueError(
            "Prompt-derived reference Turtle is not parseable."
        ) from error
    return ReferenceContext(
        turtle=turtle,
        sha256=candidates[0][2],
        uri_refs=frozenset(
            term
            for subject, predicate, obj in graph
            for term in (subject, predicate, obj)
            if isinstance(term, URIRef)
        ),
        source_rows=tuple(item[0] for item in candidates),
    )


def _recorded_reference_hash(row: dict[str, Any]) -> str | None:
    """Read the historical reference hash from either preserved response shape.

    :param row: Legacy full-context raw observation.
    :return: Recorded SHA-256 text, when present.
    """
    candidates = (
        row.get("ontology_ref"),
        _nested_mapping(row, "raw_response", "debug_output", "ontology_ref"),
        _nested_mapping(
            row,
            "raw_response",
            "ontology_review",
            "data",
            "ontology_ref",
        ),
    )
    for value in candidates:
        if isinstance(value, dict):
            digest = value.get("ttl_sha256")
            if isinstance(digest, str) and digest:
                return digest
    return None


def _full_context_prompt(row: dict[str, Any]) -> str | None:
    """Find the planner prompt that contains the full legacy ontology.

    :param row: Legacy full-context raw observation.
    :return: Planner user prompt, when the old response retained it.
    """
    candidates = (
        _nested_mapping(row, "raw_response", "debug_output", "prompts", "user"),
        _nested_mapping(
            row,
            "raw_response",
            "ontology_review",
            "data",
            "prompts",
            "user",
        ),
        _nested_mapping(row, "prompts", "workflow", "user"),
    )
    for value in candidates:
        if isinstance(value, str) and value:
            return value
    return None


def _build_observations(
    run_dir: Path, raw_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Create explicit diagnostic rows without promoting missing evidence.

    :param run_dir: Historical run directory.
    :param raw_rows: Legacy raw observations.
    :return: Rows suitable for workbook tables and CSV views.
    """
    observations: list[dict[str, Any]] = []
    for raw in raw_rows:
        sidecar_path = _artifact_path(run_dir, raw.get("raw_ttl_artifact_path"))
        syntax_valid, syntax_error, triple_count = _sidecar_syntax(sidecar_path)
        recorded_syntax = raw.get("turtle_syntax_valid")
        recorded_syntax = (
            recorded_syntax if isinstance(recorded_syntax, bool) else None
        )
        mismatch = (
            recorded_syntax is not None
            and syntax_valid is not None
            and recorded_syntax != syntax_valid
        )
        exclusion_reasons = _observation_exclusion_reasons(
            raw=raw,
            sidecar_exists=sidecar_path is not None,
            syntax_valid=syntax_valid,
            syntax_mismatch=mismatch,
        )
        annotation_digest = _annotation_digest(raw)
        stage2_adjustment = _stage2_adjustment(raw)
        context_reduction = _number_from_mapping(
            stage2_adjustment, "reduction_tokens"
        )
        stage2_reduced = bool(
            context_reduction is not None and context_reduction > 0
        )
        retrieval_ttl = raw.get("legacy_retrieval_ttl_artifact_path")
        retrieval_yaml = raw.get("legacy_retrieval_yaml_artifact_path")
        observations.append(
            {
                "condition": raw["condition"],
                "regest_id": raw["regest_id"],
                "success": raw.get("success") is True,
                "error_message": _text(raw.get("error_message")),
                "failure_stage": _text(raw.get("failure_stage")),
                "non_retryable": _bool(raw.get("non_retryable")),
                "model": _text(raw.get("model")),
                "annotation_model": _text(raw.get("annotation_model")),
                "context_mode_requested": _text(
                    raw.get("context_mode_requested")
                ),
                "context_mode_effective": _text(
                    raw.get("context_mode_effective")
                ),
                "duration_seconds": _number(raw.get("duration_seconds")),
                "total_attempt_duration_seconds": _number(
                    raw.get("total_attempt_duration_seconds")
                ),
                "total_elapsed_seconds": _number(
                    raw.get("total_elapsed_seconds")
                ),
                "prompt_tokens": _number(raw.get("prompt_tokens")),
                "prompt_tokens_complete": _bool(
                    raw.get("prompt_tokens_complete")
                ),
                "prompt_tokens_source": _text(raw.get("prompt_tokens_source")),
                "output_tokens": _number(raw.get("output_tokens")),
                "output_tokens_source": _text(raw.get("output_tokens_source")),
                "context_mode_estimated_ontology_tokens": _number(
                    raw.get("context_mode_estimated_ontology_tokens")
                ),
                "stage2_output_reduced": stage2_reduced,
                "stage2_reduction_tokens": context_reduction,
                "stage2_effective_max_tokens": _number_from_mapping(
                    stage2_adjustment, "effective_max_tokens"
                ),
                "stage2_requested_max_tokens": _number_from_mapping(
                    stage2_adjustment, "requested_max_tokens"
                ),
                "legacy_recorded_turtle_syntax_valid": recorded_syntax,
                "turtle_syntax_valid": syntax_valid,
                "turtle_triple_count": triple_count,
                "turtle_syntax_error": syntax_error,
                "legacy_syntax_status_disagrees": mismatch,
                "raw_ttl_capture_attested": _bool(
                    raw.get("raw_ttl_capture_complete")
                )
                is True,
                "raw_ttl_source": "legacy_sidecar_not_exact_stage2_attested",
                "annotation_content_sha256_reconstructed": annotation_digest,
                "legacy_retrieval_ttl_present": isinstance(retrieval_ttl, str),
                "legacy_retrieval_yaml_present": isinstance(
                    retrieval_yaml, str
                ),
                "raw_artifact_path": raw["raw_artifact_path"],
                "raw_yaml_artifact_path": raw.get("raw_yaml_artifact_path"),
                "raw_ttl_artifact_path": raw.get("raw_ttl_artifact_path"),
                "legacy_retrieval_ttl_artifact_path": retrieval_ttl,
                "legacy_retrieval_yaml_artifact_path": retrieval_yaml,
                "legacy_diagnostic_eligible": not exclusion_reasons,
                "exclusion_reasons": " | ".join(exclusion_reasons),
            }
        )
    return observations


def _sidecar_syntax(
    path: Path | None,
) -> tuple[bool | None, str | None, int | None]:
    """Parse a sidecar using the historic prefix fallback in memory only.

    :param path: Raw legacy Turtle sidecar, if present.
    :return: Parse validity, parser error, and triple count.
    """
    if path is None:
        return None, None, None
    try:
        graph = _parse_turtle(path.read_text(encoding="utf-8"))
    except Exception as error:
        return False, str(error).splitlines()[0], None
    return True, None, len(graph)


def _parse_turtle(turtle: str) -> Graph:
    """Parse historical Turtle with the old in-memory prefix fallback.

    :param turtle: Unmodified text read from a legacy sidecar.
    :return: Parsed RDF graph.
    """
    graph = Graph()
    payload = (
        turtle if "@prefix" in turtle else f"{_TURTLE_PREFIXES}\n\n{turtle}"
    )
    graph.parse(data=payload, format="turtle")
    return graph


def _observation_exclusion_reasons(
    *,
    raw: dict[str, Any],
    sidecar_exists: bool,
    syntax_valid: bool | None,
    syntax_mismatch: bool,
) -> list[str]:
    """Describe every reason an observation cannot enter a legacy diagnostic.

    :param raw: Original legacy raw observation.
    :param sidecar_exists: Whether an analysis Turtle sidecar exists.
    :param syntax_valid: Independent parser result for that sidecar.
    :param syntax_mismatch: Whether old and independent syntax results differ.
    :return: Stable machine-readable exclusion codes.
    """
    reasons: list[str] = []
    if raw.get("success") is not True:
        failure_stage = raw.get("failure_stage")
        if failure_stage == "shared_annotation_precondition":
            reasons.append("paired_condition_not_submitted")
        elif raw.get("error_message"):
            reasons.append("legacy_condition_failure")
        else:
            reasons.append("legacy_unspecified_failure")
        return reasons
    if not sidecar_exists:
        reasons.append("missing_legacy_turtle_sidecar")
    elif syntax_valid is False:
        reasons.append("legacy_turtle_sidecar_unparseable")
    if syntax_mismatch:
        reasons.append("legacy_recorded_syntax_disagrees")
    if raw.get("condition") == "workflow_rag" and not (
        raw.get("legacy_retrieval_ttl_artifact_path")
        and raw.get("legacy_retrieval_yaml_artifact_path")
    ):
        reasons.append("missing_legacy_flat_retrieval_sidecar")
    return reasons


def _annotation_digest(raw: dict[str, Any]) -> str | None:
    """Create a stable digest of the retained normalized annotation payload.

    :param raw: Legacy workflow raw observation.
    :return: SHA-256 digest, or ``None`` where no annotation payload exists.
    """
    if raw.get("condition") not in WORKFLOW_CONDITIONS:
        return None
    data = _nested_mapping(raw, "raw_response", "annotation_review", "data")
    if not isinstance(data, dict):
        return None
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stage2_adjustment(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Read the historical provider context-cap adjustment record.

    :param raw: Legacy raw observation.
    :return: Stage-2 adjustment mapping when the provider retained one.
    """
    metadata = raw.get("provider_run_metadata")
    if not isinstance(metadata, dict):
        return None
    stage2 = metadata.get("stage2")
    if not isinstance(stage2, dict):
        return None
    adjustment = stage2.get("context_window_adjustment")
    return adjustment if isinstance(adjustment, dict) else None


def _schema_declarations(
    *,
    run_dir: Path,
    observations: list[dict[str, Any]],
    reference_iris: frozenset[URIRef],
) -> list[dict[str, Any]]:
    """Classify schema declarations from eligible legacy Turtle sidecars.

    :param run_dir: Historical run directory.
    :param observations: Normalized preliminary observation rows.
    :param reference_iris: URIRefs from the hash-attested prompt reference.
    :return: One row per explicit class or property declaration.
    """
    declarations: list[dict[str, Any]] = []
    for observation in observations:
        if not observation["legacy_diagnostic_eligible"]:
            _attach_schema_metrics(observation, [])
            continue
        turtle_relative = observation.get("raw_ttl_artifact_path")
        if not isinstance(turtle_relative, str):
            _attach_schema_metrics(observation, [])
            continue
        graph = _parse_turtle(
            (run_dir / turtle_relative).read_text(encoding="utf-8")
        )
        observation_declarations: list[dict[str, Any]] = []
        for subject, _, schema_type in graph.triples((None, RDF.type, None)):
            if not isinstance(subject, URIRef) or not isinstance(
                schema_type, URIRef
            ):
                continue
            declaration_kind = SCHEMA_TYPES.get(schema_type)
            if declaration_kind is None:
                continue
            declaration = {
                "regest_id": observation["regest_id"],
                "condition": observation["condition"],
                "declaration_iri": str(subject),
                "declaration_kind": declaration_kind,
                "declared_as": str(schema_type),
                "label": " | ".join(
                    str(value) for value in graph.objects(subject, RDFS.label)
                ),
                "definition": " | ".join(
                    str(value)
                    for value in graph.objects(subject, SKOS.definition)
                ),
                "reference_iri_reused": subject in reference_iris,
                "reference_evidence": (
                    "legacy_prompt_derived_reference_sha256_attested"
                ),
                "raw_ttl_artifact_path": observation["raw_ttl_artifact_path"],
            }
            declarations.append(declaration)
            observation_declarations.append(declaration)
        _attach_schema_metrics(observation, observation_declarations)
    return declarations


def _attach_schema_metrics(
    observation: dict[str, Any], declarations: list[dict[str, Any]]
) -> None:
    """Attach per-observation schema counts derived from declaration rows.

    :param observation: Mutable preliminary observation row.
    :param declarations: Class/property declaration rows for the observation.
    """
    reuse_count = sum(item["reference_iri_reused"] for item in declarations)
    declaration_count = len(declarations)
    observation["schema_declaration_count"] = declaration_count
    observation["schema_reference_iri_reuse_count"] = reuse_count
    observation["novel_schema_declaration_count"] = (
        declaration_count - reuse_count
    )
    observation["schema_reference_iri_reuse_share"] = (
        reuse_count / declaration_count if declaration_count else None
    )
    observation["generated_classes"] = _iri_list(
        item["declaration_iri"]
        for item in declarations
        if item["declaration_kind"] == "class"
    )
    observation["generated_properties"] = _iri_list(
        item["declaration_iri"]
        for item in declarations
        if item["declaration_kind"] == "property"
    )


def _iri_list(iris: Iterable[str]) -> str:
    """Render multiple IRIs as text instead of an accidental Excel hyperlink.

    :param iris: Schema declaration IRIs.
    :return: Human-readable text that does not begin with a URL.
    """
    values = list(iris)
    return "IRI list: " + " | ".join(values) if values else ""


def _dmw_context_pairs(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the only admissible legacy paired comparison table.

    :param observations: Preliminary observation rows.
    :return: Full-context/RAG paired rows with explicit exclusions.
    """
    by_condition = {
        condition: {
            str(row["regest_id"]): row
            for row in observations
            if row["condition"] == condition
        }
        for condition in WORKFLOW_CONDITIONS
    }
    full_rows = by_condition["workflow_full_ontology"]
    rag_rows = by_condition["workflow_rag"]
    pairs: list[dict[str, Any]] = []
    for regest_id in sorted(full_rows.keys() & rag_rows.keys()):
        full = full_rows[regest_id]
        rag = rag_rows[regest_id]
        annotation_match = (
            isinstance(full["annotation_content_sha256_reconstructed"], str)
            and full["annotation_content_sha256_reconstructed"]
            == rag["annotation_content_sha256_reconstructed"]
        )
        valid_pair = bool(
            full["legacy_diagnostic_eligible"]
            and rag["legacy_diagnostic_eligible"]
            and annotation_match
        )
        pair_reasons = []
        if not full["legacy_diagnostic_eligible"]:
            pair_reasons.append(
                "full=" + str(full["exclusion_reasons"] or "ineligible")
            )
        if not rag["legacy_diagnostic_eligible"]:
            pair_reasons.append(
                "rag=" + str(rag["exclusion_reasons"] or "ineligible")
            )
        if not annotation_match:
            pair_reasons.append("reconstructed_annotation_digest_mismatch")
        pairs.append(
            {
                "regest_id": regest_id,
                "comparison": "workflow_full_ontology vs workflow_rag",
                "legacy_diagnostic_pair_eligible": valid_pair,
                "annotation_digest_match": annotation_match,
                "annotation_evidence": (
                    "reconstructed_normalized_annotation_payload"
                ),
                "full_success": full["success"],
                "rag_success": rag["success"],
                "full_turtle_syntax_valid": full["turtle_syntax_valid"],
                "rag_turtle_syntax_valid": rag["turtle_syntax_valid"],
                "full_stage2_output_reduced": full["stage2_output_reduced"],
                "rag_stage2_output_reduced": rag["stage2_output_reduced"],
                "full_prompt_tokens": full["prompt_tokens"],
                "rag_prompt_tokens": rag["prompt_tokens"],
                "rag_minus_full_prompt_tokens": _difference(
                    rag["prompt_tokens"], full["prompt_tokens"]
                ),
                "full_duration_seconds": full["duration_seconds"],
                "rag_duration_seconds": rag["duration_seconds"],
                "rag_minus_full_duration_seconds": _difference(
                    rag["duration_seconds"], full["duration_seconds"]
                ),
                "full_schema_reference_iri_reuse_share": full[
                    "schema_reference_iri_reuse_share"
                ],
                "rag_schema_reference_iri_reuse_share": rag[
                    "schema_reference_iri_reuse_share"
                ],
                "rag_minus_full_schema_reference_iri_reuse_share": _difference(
                    rag["schema_reference_iri_reuse_share"],
                    full["schema_reference_iri_reuse_share"],
                ),
                "full_raw_ttl_artifact_path": full["raw_ttl_artifact_path"],
                "rag_raw_ttl_artifact_path": rag["raw_ttl_artifact_path"],
                "pair_exclusion_reasons": " | ".join(pair_reasons),
            }
        )
    return pairs


def _direct_context_rows(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project the old direct condition without implying an A/B comparison.

    :param observations: Preliminary observation rows.
    :return: Explicitly exploratory direct-condition rows.
    """
    return [
        {
            "regest_id": row["regest_id"],
            "condition": row["condition"],
            "interpretation": (
                "Legacy exploratory direct baseline; not Haiu-RAG and not "
                "a matched DMW-versus-Haiu comparison."
            ),
            "success": row["success"],
            "turtle_syntax_valid": row["turtle_syntax_valid"],
            "schema_declaration_count": row["schema_declaration_count"],
            "schema_reference_iri_reuse_share": row[
                "schema_reference_iri_reuse_share"
            ],
            "novel_schema_declaration_count": row[
                "novel_schema_declaration_count"
            ],
            "raw_ttl_artifact_path": row["raw_ttl_artifact_path"],
            "exclusion_reasons": row["exclusion_reasons"],
        }
        for row in observations
        if row["condition"] == "direct_llm_raw_regest"
    ]


def _timing_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select legacy timing and prompt evidence with its measurement limits.

    :param observations: Preliminary observation rows.
    :return: Timing/context table rows.
    """
    fields = (
        "condition",
        "regest_id",
        "success",
        "duration_seconds",
        "total_attempt_duration_seconds",
        "total_elapsed_seconds",
        "prompt_tokens",
        "prompt_tokens_complete",
        "prompt_tokens_source",
        "output_tokens",
        "output_tokens_source",
        "context_mode_estimated_ontology_tokens",
        "stage2_output_reduced",
        "stage2_reduction_tokens",
        "stage2_effective_max_tokens",
        "stage2_requested_max_tokens",
    )
    return [
        {
            **{field: row[field] for field in fields},
            "measurement_limit": (
                "Observed legacy end-to-end wall-clock latency; not AI compute "
                "time. Workflow prompt tokens are partial Stage-1 estimates."
            ),
        }
        for row in observations
    ]


def _historian_cases(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Index readable raw artifacts for historian-led qualitative assessment.

    :param observations: Preliminary observation rows.
    :return: Case-index rows for independently parseable outputs.
    """
    return [
        {
            "regest_id": row["regest_id"],
            "condition": row["condition"],
            "case_status": (
                "Condition-labelled preliminary case; not blinded publication "
                "evidence."
            ),
            "schema_reference_iri_reuse_share": row[
                "schema_reference_iri_reuse_share"
            ],
            "novel_schema_declaration_count": row[
                "novel_schema_declaration_count"
            ],
            "raw_ttl_artifact_path": row["raw_ttl_artifact_path"],
            "raw_artifact_path": row["raw_artifact_path"],
            "historian_notes": "",
        }
        for row in observations
        if row["legacy_diagnostic_eligible"]
    ]


def _condition_summary(
    *,
    observations: list[dict[str, Any]],
    declarations: list[dict[str, Any]],
    planned_regest_count: int,
) -> list[dict[str, Any]]:
    """Aggregate condition-level descriptive measures with explicit samples.

    :param observations: Preliminary observation rows.
    :param declarations: Classified schema declaration rows.
    :param planned_regest_count: Number of IDs in the old run manifest.
    :return: Summary rows ordered by the legacy condition layout.
    """
    del declarations
    summary: list[dict[str, Any]] = []
    for condition in LEGACY_CONDITIONS:
        rows = [row for row in observations if row["condition"] == condition]
        successful = [row for row in rows if row["success"]]
        parseable = [
            row for row in successful if row["turtle_syntax_valid"] is True
        ]
        eligible = [row for row in rows if row["legacy_diagnostic_eligible"]]
        reuse_shares = _numbers(eligible, "schema_reference_iri_reuse_share")
        declaration_count = sum(
            int(row["schema_declaration_count"] or 0) for row in eligible
        )
        reuse_count = sum(
            int(row["schema_reference_iri_reuse_count"] or 0)
            for row in eligible
        )
        stage2_reductions = sum(
            row["stage2_output_reduced"] for row in successful
        )
        prompt_sources = sorted(
            {
                str(row["prompt_tokens_source"])
                for row in successful
                if row["prompt_tokens_source"]
            }
        )
        summary.append(
            {
                "condition": condition,
                "condition_role": _condition_role(condition),
                "planned_regest_count": planned_regest_count,
                "observed_rows": len(rows),
                "completed_rows": len(successful),
                "failed_or_not_submitted_rows": len(rows) - len(successful),
                "independently_parseable_turtle_count": len(parseable),
                "independently_parseable_turtle_rate": _rate(
                    len(parseable), len(successful)
                ),
                "legacy_diagnostic_eligible_count": len(eligible),
                "legacy_syntax_disagreement_count": sum(
                    row["legacy_syntax_status_disagrees"] for row in rows
                ),
                "stage2_output_reduction_count": stage2_reductions,
                "stage2_output_reduction_rate": _rate(
                    stage2_reductions, len(successful)
                ),
                "median_prompt_tokens": _median(
                    _numbers(successful, "prompt_tokens")
                ),
                "prompt_token_measurement": " | ".join(prompt_sources),
                "median_observed_duration_seconds": _median(
                    _numbers(successful, "duration_seconds")
                ),
                "schema_reuse_diagnostic_n": len(eligible),
                "median_schema_reference_iri_reuse_share": _median(
                    reuse_shares
                ),
                "minimum_schema_reference_iri_reuse_share": (
                    min(reuse_shares) if reuse_shares else None
                ),
                "aggregate_schema_reference_iri_reuse_share": _rate(
                    reuse_count, declaration_count
                ),
                "schema_declaration_count": declaration_count,
                "reference_alignment_status": (
                    "LEGACY PROMPT-DERIVED DIAGNOSTIC — NOT PUBLICATION "
                    "EVIDENCE"
                ),
            }
        )
    return summary


def _condition_role(condition: str) -> str:
    """Describe a condition without inventing the later study design.

    :param condition: Legacy condition identifier.
    :return: Plain-language condition purpose.
    """
    return {
        "workflow_full_ontology": "DMW with full reference ontology",
        "workflow_rag": "DMW with Haiu retrieval context",
        "direct_llm_raw_regest": (
            "Legacy exploratory direct baseline; not standalone Haiu-RAG"
        ),
    }[condition]


def _metric_definitions() -> list[dict[str, str]]:
    """Return the calculation and evidence definition table.

    :return: Workbook-ready metric definitions and limitations.
    """
    return [
        {
            "metric": "legacy_diagnostic_status",
            "calculation": "All figures are preliminary legacy diagnostics.",
            "source": "Missing frozen provenance and exact Stage-2 capture prevent publication use.",
        },
        {
            "metric": "independently_parseable_turtle",
            "calculation": "The unmodified legacy Turtle sidecar parses after the historical in-memory prefix fallback.",
            "source": "raw_ttl/<condition>/<id>.ttl",
        },
        {
            "metric": "schema_reference_iri_reuse_share",
            "calculation": "Declared class/property URIRefs occurring in the prompt-derived full reference ontology / all declared class/property URIRefs.",
            "source": "Legacy Turtle sidecar and hash-attested planner prompt reference block.",
        },
        {
            "metric": "novel_schema_declaration",
            "calculation": "Generated class/property URIRef absent from the prompt-derived reference URIRef set. ABox individuals are excluded.",
            "source": "06_Schema_Declarations",
        },
        {
            "metric": "legacy_diagnostic_pair_eligible",
            "calculation": "Both workflow outputs succeeded, independently parse, have no syntax-status disagreement, and retain equal reconstructed annotation digests.",
            "source": "02_DMW_Context_AB",
        },
        {
            "metric": "stage2_output_reduction_rate",
            "calculation": "Provider metadata with positive Stage-2 context-window reduction tokens / completed observations.",
            "source": "provider_run_metadata.stage2.context_window_adjustment",
        },
        {
            "metric": "prompt_tokens",
            "calculation": "Use the historical source classification verbatim. Workflow values are partial Stage-1 estimates, not complete prompt sizes.",
            "source": "prompt_tokens and prompt_tokens_source",
        },
        {
            "metric": "duration_seconds",
            "calculation": "Legacy observed end-to-end wall-clock latency. It can include queueing, network, retries, and runtime effects; it is not AI compute time.",
            "source": "duration_seconds",
        },
        {
            "metric": "direct_llm_raw_regest",
            "calculation": "Shown only as contextual exploratory output; it is neither the later haiu_rag_ontologizer condition nor a primary A/B comparison.",
            "source": "03_Legacy_Direct_Context",
        },
    ]


def _write_main_workbook(
    *,
    path: Path,
    manifest: dict[str, Any],
    reference: ReferenceContext,
    condition_summary: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    direct_context: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    timing_rows: list[dict[str, Any]],
    declarations: list[dict[str, Any]],
    historian_cases: list[dict[str, Any]],
    definitions: list[dict[str, str]],
) -> None:
    """Write the styled main workbook and all condition-labelled sheets.

    :param path: Target XLSX path.
    :param manifest: Historical run manifest.
    :param reference: Verified prompt-derived reference context.
    :param condition_summary: Aggregate condition rows.
    :param pairs: DMW context A/B rows.
    :param direct_context: Exploratory direct-condition rows.
    :param observations: Observation ledger rows.
    :param timing_rows: Timing/context rows.
    :param declarations: Schema declaration rows.
    :param historian_cases: Qualitative case index rows.
    :param definitions: Metric definition rows.
    """
    workbook = xlsxwriter.Workbook(path)
    try:
        formats = strict_export._formats(workbook)
        critical = workbook.add_format(
            {"bold": True, "bg_color": "#C00000", "font_color": "#FFFFFF"}
        )
        about = workbook.add_worksheet("00_Legacy_About")
        about.set_column(0, 0, 32)
        about.set_column(1, 1, 108, formats["wrap"])
        about.write(
            0,
            0,
            "Legacy DMW–Haiu pilot overview",
            formats["title"],
        )
        about.write(
            2,
            0,
            "Status",
            formats["header"],
        )
        about.write(
            2,
            1,
            "PRELIMINARY LEGACY PILOT — NOT PUBLICATION EVIDENCE",
            critical,
        )
        about_rows = [
            ("Run ID", manifest.get("run_id")),
            (
                "Primary comparison",
                "workflow_full_ontology vs workflow_rag only",
            ),
            (
                "Direct condition",
                "direct_llm_raw_regest is contextual only; it is not Haiu-RAG.",
            ),
            (
                "Reference evidence",
                "Prompt-derived Turtle matched the recorded full-reference "
                f"SHA-256: {reference.sha256}",
            ),
            (
                "Reference source rows",
                ", ".join(reference.source_rows),
            ),
            (
                "Raw-Turtle limitation",
                "Workflow raw JSON did not attest to exact unmodified Stage-2 "
                "output; this export uses legacy sidecars only for a diagnostic.",
            ),
            (
                "Timing limitation",
                "Observed legacy end-to-end wall-clock latency, not AI compute "
                "time; named stage scopes are unavailable.",
            ),
        ]
        for row_index, (label, value) in enumerate(about_rows, start=4):
            about.write(row_index, 0, label, formats["header"])
            strict_export._write_value(about, row_index, 1, value, formats)
        strict_export._write_table(
            workbook,
            "01_Condition_Summary",
            condition_summary,
            formats,
            "legacy_condition_summary",
        )
        strict_export._write_table(
            workbook,
            "02_DMW_Context_AB",
            pairs,
            formats,
            "legacy_dmw_context_ab",
        )
        strict_export._write_table(
            workbook,
            "03_Legacy_Direct_Context",
            direct_context,
            formats,
            "legacy_direct_context",
        )
        strict_export._write_table(
            workbook,
            "04_Observations",
            observations,
            formats,
            "legacy_observations",
        )
        strict_export._write_table(
            workbook,
            "05_Context_Timing",
            timing_rows,
            formats,
            "legacy_timing_context",
        )
        strict_export._write_table(
            workbook,
            "06_Schema_Declarations",
            declarations,
            formats,
            "legacy_schema_declarations",
        )
        strict_export._write_table(
            workbook,
            "07_Novel_Declarations",
            [row for row in declarations if not row["reference_iri_reused"]],
            formats,
            "legacy_novel_declarations",
        )
        strict_export._write_table(
            workbook,
            "08_Historian_Cases",
            historian_cases,
            formats,
            "legacy_historian_cases",
        )
        strict_export._write_table(
            workbook,
            "99_Definitions_Limits",
            definitions,
            formats,
            "legacy_metric_definitions",
        )
    finally:
        workbook.close()


def _write_masked_case_review(
    *,
    path: Path,
    observations: list[dict[str, Any]],
    manifest: dict[str, Any],
    run_dir: Path,
) -> dict[str, dict[str, str]]:
    """Write a deterministic condition-masked qualitative review workbook.

    :param path: Target XLSX path.
    :param observations: Preliminary observation rows.
    :param manifest: Historical run manifest used for the stable shuffle seed.
    :param run_dir: Historical run directory.
    :return: Reveal-key mapping retained beside the workbook.
    """
    seed = int(
        hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        16,
    )
    cases = [row for row in observations if row["legacy_diagnostic_eligible"]]
    random.Random(seed).shuffle(cases)
    reveal_key: dict[str, dict[str, str]] = {}
    review_rows: list[dict[str, Any]] = []
    for index, row in enumerate(cases, start=1):
        review_id = f"R{index:04d}"
        turtle_path = run_dir / str(row["raw_ttl_artifact_path"])
        reveal_key[review_id] = {
            "regest_id": str(row["regest_id"]),
            "condition": str(row["condition"]),
            "raw_ttl_artifact_path": str(row["raw_ttl_artifact_path"]),
        }
        review_rows.append(
            {
                "review_id": review_id,
                "regest_id": row["regest_id"],
                "generated_turtle": turtle_path.read_text(encoding="utf-8"),
                "reference_ontology_adherence": "",
                "modelling_adequacy": "",
                "factual_grounding": "",
                "historian_usability": "",
                "review_notes": "",
            }
        )
    workbook = xlsxwriter.Workbook(path)
    try:
        formats = strict_export._formats(workbook)
        sheet = workbook.add_worksheet("Masked_Review")
        sheet.write(
            0,
            0,
            "Legacy pilot: condition labels are intentionally masked. "
            "Ratings are preliminary and not publication evidence.",
            formats["title"],
        )
        strict_export._write_rows(
            sheet,
            review_rows,
            formats,
            "legacy_masked_review",
            start_row=2,
        )
    finally:
        workbook.close()
    return reveal_key


def _analysis_manifest(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    reference: ReferenceContext,
    source_hashes: dict[str, str],
    condition_summary: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    output_dir: Path,
    audit_csv: bool,
    audit_paths: list[Path],
) -> dict[str, Any]:
    """Build the reproducibility record for a derived preliminary analysis.

    :param run_dir: Historical run directory.
    :param manifest: Original legacy run manifest.
    :param reference: Hash-attested prompt-derived reference context.
    :param source_hashes: Hashes for every read legacy source artifact.
    :param condition_summary: Aggregate result rows.
    :param pairs: DMW context A/B rows.
    :param output_dir: Derived-analysis directory.
    :param audit_csv: Whether compact audit CSVs were emitted.
    :param audit_paths: Emitted audit CSV paths.
    :return: JSON-serializable analysis manifest.
    """
    outputs = {
        path.relative_to(output_dir).as_posix(): _sha256_file(path)
        for path in sorted(
            [
                output_dir / "overview.xlsx",
                output_dir / "masked_case_review.xlsx",
                output_dir / "reveal_key.json",
                output_dir / "README.md",
                *audit_paths,
            ]
        )
    }
    return {
        "schema_version": 1,
        "analysis_kind": "legacy_preliminary_pilot_diagnostic",
        "publication_eligible": False,
        "warning": "LEGACY PROMPT-DERIVED DIAGNOSTIC — NOT PUBLICATION EVIDENCE",
        "run_directory": run_dir.name,
        "run_id": manifest.get("run_id"),
        "legacy_conditions": list(LEGACY_CONDITIONS),
        "primary_comparison": "workflow_full_ontology vs workflow_rag",
        "excluded_comparison": (
            "direct_llm_raw_regest is not haiu_rag_ontologizer and is not "
            "a DMW-versus-Haiu-RAG comparison."
        ),
        "reference": {
            "source": "fenced full-ontology planner prompt block",
            "sha256": reference.sha256,
            "source_regest_ids": list(reference.source_rows),
            "uri_ref_count": len(reference.uri_refs),
        },
        "source_hashes": source_hashes,
        "condition_summary": condition_summary,
        "pair_denominator": sum(
            row["legacy_diagnostic_pair_eligible"] for row in pairs
        ),
        "audit_csv_enabled": audit_csv,
        "metric_definitions": _metric_definitions(),
        "output_hashes": outputs,
        "exporter_sha256": _sha256_file(Path(__file__)),
    }


def _source_hashes(run_dir: Path) -> dict[str, str]:
    """Hash every historical file consumed by the preliminary adapter.

    :param run_dir: Historical run directory.
    :return: Relative path to SHA-256 mapping.
    """
    files = [run_dir / "summaries" / "run_manifest.json"]
    for directory in ("raw", "raw_yaml", "raw_ttl", "prompts"):
        root = run_dir / directory
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return {
        path.relative_to(run_dir).as_posix(): _sha256_file(path)
        for path in sorted(set(files))
        if path.is_file()
    }


def _output_paths(output_dir: Path) -> LegacyExportPaths:
    """Return the fixed derived-analysis artifact paths.

    :param output_dir: Analysis output directory.
    :return: Output artifact path container.
    """
    return LegacyExportPaths(
        workbook=output_dir / "overview.xlsx",
        review_workbook=output_dir / "masked_case_review.xlsx",
        reveal_key=output_dir / "reveal_key.json",
        manifest=output_dir / "analysis_manifest.json",
        readme=output_dir / "README.md",
    )


def _load_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from one historical artifact.

    :param path: JSON artifact path.
    :return: Parsed object.
    :raises ValueError: If the file is absent or has the wrong JSON shape.
    """
    if not path.is_file():
        raise ValueError(f"Missing required JSON artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _nested_mapping(
    value: dict[str, Any], *keys: str
) -> dict[str, Any] | str | None:
    """Follow a dynamic historical payload path without changing its value.

    :param value: Historical JSON object at a dynamic compatibility boundary.
    :param keys: Nested mapping keys.
    :return: Final mapping/string value, or ``None`` if the old shape differs.
    """
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, (dict, str)) else None


def _artifact_path(run_dir: Path, relative: Any) -> Path | None:
    """Resolve a retained relative artifact path only when it still exists.

    :param run_dir: Historical run directory.
    :param relative: Relative artifact path from a legacy payload.
    :return: Existing artifact path, or ``None``.
    """
    if not isinstance(relative, str):
        return None
    path = run_dir / relative
    return path if path.is_file() else None


def _relative_if_file(run_dir: Path, path: Path) -> str | None:
    """Return a relative path only for an existing legacy artifact.

    :param run_dir: Historical run directory.
    :param path: Candidate artifact path.
    :return: Run-relative POSIX path, or ``None``.
    """
    return path.relative_to(run_dir).as_posix() if path.is_file() else None


def _bool(value: Any) -> bool | None:
    """Return one strict boolean from a dynamic historical JSON field.

    :param value: Historical payload value.
    :return: Boolean value, or ``None`` when unavailable.
    """
    return value if isinstance(value, bool) else None


def _number(value: Any) -> int | float | None:
    """Return one strict numeric value from a dynamic historical JSON field.

    :param value: Historical payload value.
    :return: Number, or ``None`` when unavailable.
    """
    return (
        value
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _number_from_mapping(
    mapping: dict[str, Any] | None, key: str
) -> int | float | None:
    """Read one number from an optional historical metadata mapping.

    :param mapping: Dynamic metadata mapping, when present.
    :param key: Numeric field name.
    :return: Number, or ``None`` when unavailable.
    """
    return _number(mapping.get(key)) if mapping is not None else None


def _text(value: Any) -> str | None:
    """Return non-empty text from a dynamic historical JSON field.

    :param value: Historical payload value.
    :return: Text, or ``None`` when unavailable.
    """
    return value if isinstance(value, str) and value else None


def _difference(
    later: int | float | None, earlier: int | float | None
) -> float | None:
    """Calculate a displayed RAG-minus-full numeric difference.

    :param later: Right-side comparison value.
    :param earlier: Left-side comparison value.
    :return: Difference, or ``None`` when a value is unavailable.
    """
    if later is None or earlier is None:
        return None
    return float(later - earlier)


def _numbers(rows: Iterable[dict[str, Any]], key: str) -> list[float]:
    """Collect present numeric values from workbook rows.

    :param rows: Workbook-row mappings.
    :param key: Numeric field name.
    :return: Float values in input order.
    """
    return [
        float(value)
        for row in rows
        if (value := _number(row.get(key))) is not None
    ]


def _median(values: list[float]) -> float | None:
    """Return a median only for an observed population.

    :param values: Numeric observations.
    :return: Median, or ``None`` for no observations.
    """
    return median(values) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    """Return a rate only when its denominator is defined.

    :param numerator: Count satisfying a condition.
    :param denominator: Population count.
    :return: Fraction, or ``None`` for an empty population.
    """
    return numerator / denominator if denominator else None


def _sha256_text(value: str) -> str:
    """Hash one UTF-8 text payload.

    :param value: Text to hash.
    :return: SHA-256 digest.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash one file without interpreting its contents.

    :param path: Existing file path.
    :return: SHA-256 digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
