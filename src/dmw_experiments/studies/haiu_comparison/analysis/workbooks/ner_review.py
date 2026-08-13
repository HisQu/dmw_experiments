"""Export provider-visible NER annotations for historian span review."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from dmw_experiments.shared.analysis import (
    EntityMention,
    EntitySpanResolver,
    ResolvedEntityMention,
)
from dmw_experiments.studies.haiu_comparison.model.artifact_layout import (
    ExecutionArtifactLayout,
    portable_name,
)
from dmw_experiments.studies.haiu_comparison.model.inputs import (
    HeaderSublemmaCatalog,
    HeaderSublemmaInput,
    load_header_sublemma_catalog,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)

NER_REVIEW_LOCATION_VERDICTS = (
    "Correct",
    "Wrong occurrence",
    "Boundary correction",
    "Not present",
    "Unclear",
)
NER_REVIEW_TYPE_VERDICTS = (
    "Correct",
    "Incorrect",
    "Unclear",
    "Not applicable",
)
NER_REVIEW_COMPLETION_STATES = ("Not started", "In progress", "Complete")
NER_REVIEW_COLORS = (
    "#1F4E78",
    "#9C0006",
    "#548235",
    "#7030A0",
    "#C65911",
    "#006666",
    "#7F6000",
    "#404040",
)
NER_REVIEW_MATCHER_RULES = {
    "normalization": "Unicode NFKC, collapsed whitespace, then case-folding",
    "fuzzy_candidate_scope": "token-boundary windows",
    "fuzzy_minimum_length": EntitySpanResolver.FUZZY_MINIMUM_LENGTH,
    "fuzzy_short_maximum_length": (
        EntitySpanResolver.FUZZY_SHORT_MAXIMUM_LENGTH
    ),
    "fuzzy_short_minimum_score": (EntitySpanResolver.FUZZY_SHORT_MINIMUM_SCORE),
    "fuzzy_long_minimum_score": EntitySpanResolver.FUZZY_LONG_MINIMUM_SCORE,
    "fuzzy_runner_up_margin": EntitySpanResolver.FUZZY_RUNNER_UP_MARGIN,
    "retained_candidate_count": EntitySpanResolver.MAX_CANDIDATES,
}
_PROVIDER_LABELS = {
    "academiccloud": "AcademicCloud",
    "lmstudio": "LM Studio",
}


@dataclass(frozen=True, slots=True)
class HistorianNerReviewPaths:
    """Paths emitted by one adaptive historian NER review export.

    :param workbook: Editable provider-visible review workbook.
    :param manifest: Source, matcher, and output hashes for the workbook.
    """

    workbook: Path
    manifest: Path


@dataclass(frozen=True, slots=True)
class _NerReviewSegment:
    """Hold one provider's source segment and its resolved annotations.

    :param provider: Execution slug used in machine-readable fields.
    :param provider_label: Human-facing provider name.
    :param input_unit_id: Frozen header--sublemma unit identifier.
    :param source_regest_id: Complete source-regest identifier.
    :param source_sublemma_number: One-based source position.
    :param segment: ``Header`` or ``Sublemma``.
    :param source_text: Original unmodified segment text.
    :param source_sha256: Digest of ``source_text``.
    :param annotation_available: Whether frozen annotation evidence exists.
    :param annotation_path: Run-relative evidence path when available.
    :param annotation_sha256: Digest of the evidence file when available.
    :param annotation_model: Model recorded by annotation evidence.
    :param annotation_version: Guideline or ontology version recorded there.
    :param results: Ordered conservative location results.
    """

    provider: str
    provider_label: str
    input_unit_id: str
    source_regest_id: str
    source_sublemma_number: int
    segment: str
    source_text: str
    source_sha256: str
    annotation_available: bool
    annotation_path: str
    annotation_sha256: str
    annotation_model: str
    annotation_version: str
    results: tuple[ResolvedEntityMention, ...]


@dataclass(frozen=True, slots=True)
class _NerProviderReview:
    """Hold one validated provider's segments and frozen identities.

    :param execution: Provider execution slug.
    :param label: Human-facing provider name.
    :param run_dir: Provider raw-evidence directory.
    :param run_manifest_sha256: Exact execution-manifest digest.
    :param input_catalog_sha256: Frozen catalogue file digest.
    :param annotation_guideline_path: Run-relative frozen guideline path.
    :param annotation_guideline_sha256: Frozen guideline digest.
    :param scheduled_unit_count: Source units represented for this provider.
    :param annotated_unit_count: Units with available annotation evidence.
    :param segments: Header and sublemma review rows.
    """

    execution: str
    label: str
    run_dir: Path
    run_manifest_sha256: str
    input_catalog_sha256: str
    annotation_guideline_path: str
    annotation_guideline_sha256: str
    scheduled_unit_count: int
    annotated_unit_count: int
    segments: tuple[_NerReviewSegment, ...]


@dataclass(frozen=True, slots=True)
class _DisplayMarker:
    """Group all semantic labels rendered at one exact source span.

    :param number: Segment-local authoritative marker number.
    :param color_index: Index into the repeating dark-color palette.
    :param start_offset: Inclusive source boundary.
    :param end_offset: Exclusive source boundary.
    :param results: Resolved annotations sharing this exact span.
    """

    number: int
    color_index: int
    start_offset: int
    end_offset: int
    results: tuple[ResolvedEntityMention, ...]

    @property
    def is_fuzzy(self) -> bool:
        """Check whether any grouped annotation used approximate matching.

        :return: Whether the marker needs the ``≈`` prefix.
        """
        return any(
            result.selected is not None and result.selected.method == "fuzzy"
            for result in self.results
        )

    @property
    def label(self) -> str:
        """Build the source marker shown beside the highlighted span.

        :return: Bracketed local number with an optional ``≈`` prefix.
        """
        prefix = "≈" if self.is_fuzzy else ""
        return f"{prefix}[{self.number}]"


def export_historian_ner_review_workbook(
    provider_run_dirs: dict[str, Path],
    *,
    workbook_path: Path,
    allow_partial: bool = False,
    overwrite: bool = False,
) -> HistorianNerReviewPaths:
    """Write one adaptive workbook for shared NER annotation review.

    The workbook has one provider sheet for each supplied execution. Source
    population does not depend on successful ontology generation. A normal
    export requires frozen annotation evidence for every scheduled input;
    partial exports keep missing annotations visible as unavailable rows.

    :param provider_run_dirs: Enabled execution slugs mapped to their
        ``raw-<execution>`` directories.
    :param workbook_path: Destination for the editable XLSX file.
    :param allow_partial: Permit missing manifests, snapshots, or annotations
        while labelling their absence.
    :param overwrite: Replace this export's workbook and adjacent manifest.
    :return: Workbook and manifest paths.
    :raises ValueError: If evidence is malformed, providers disagree, or an
        owned output exists without replacement permission.
    """
    if not provider_run_dirs:
        raise ValueError("NER review requires at least one provider execution.")
    unsupported = sorted(set(provider_run_dirs) - set(_PROVIDER_LABELS))
    if unsupported:
        raise ValueError(
            "Unsupported NER review provider execution: "
            + ", ".join(unsupported)
        )
    resolved_dirs = {
        execution: path.expanduser().resolve()
        for execution, path in provider_run_dirs.items()
    }
    roots = {path.parent for path in resolved_dirs.values()}
    if len(roots) != 1:
        raise ValueError("NER review providers must belong to the same run.")
    run_root = next(iter(roots))
    contract = load_run_contract(run_root)
    catalog = load_header_sublemma_catalog(run_root / contract.input_catalog)
    resolver = EntitySpanResolver()
    providers = tuple(
        _load_provider_review(
            execution=execution,
            run_dir=resolved_dirs[execution],
            catalog=catalog,
            resolver=resolver,
            allow_partial=allow_partial,
        )
        for execution in _ordered_executions(
            (spec.name for spec in contract.executions), resolved_dirs
        )
    )
    if allow_partial and len(providers) > 1:
        scheduled_union = _provider_scheduled_union(
            providers=providers, catalog=catalog
        )
        if any(
            _provider_unit_ids(provider) != set(scheduled_union)
            for provider in providers
        ):
            providers = tuple(
                _load_provider_review(
                    execution=execution,
                    run_dir=resolved_dirs[execution],
                    catalog=catalog,
                    resolver=resolver,
                    allow_partial=True,
                    scheduled_ids=scheduled_union,
                )
                for execution in _ordered_executions(
                    (spec.name for spec in contract.executions), resolved_dirs
                )
            )
    _validate_provider_agreement(providers, allow_partial=allow_partial)

    workbook_path = workbook_path.expanduser().resolve()
    if not workbook_path.is_relative_to(run_root):
        raise ValueError("NER review workbook must be written inside its run.")
    manifest_path = workbook_path.with_name(
        f"{workbook_path.stem}_manifest.json"
    )
    _prepare_outputs(paths=(workbook_path, manifest_path), overwrite=overwrite)
    _write_ner_review_workbook(
        path=workbook_path,
        providers=providers,
        partial=allow_partial,
    )
    manifest = _ner_review_manifest(
        workbook_path=workbook_path,
        providers=providers,
        allow_partial=allow_partial,
        run_root=run_root,
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return HistorianNerReviewPaths(
        workbook=workbook_path,
        manifest=manifest_path,
    )


def _ordered_executions(
    declared: Iterable[str], provider_run_dirs: dict[str, Path]
) -> tuple[str, ...]:
    """Keep contract order while rejecting undeclared execution slugs.

    :param declared: Execution slugs in run-contract order.
    :param provider_run_dirs: Requested execution directories.
    :return: Requested execution slugs in contract order.
    """
    ordered = tuple(name for name in declared if name in provider_run_dirs)
    if set(ordered) != set(provider_run_dirs):
        undeclared = sorted(set(provider_run_dirs) - set(ordered))
        raise ValueError(
            "NER review provider is not declared by run.toml: "
            + ", ".join(undeclared)
        )
    return ordered


def _load_provider_review(
    *,
    execution: str,
    run_dir: Path,
    catalog: HeaderSublemmaCatalog,
    resolver: EntitySpanResolver,
    allow_partial: bool,
    scheduled_ids: tuple[str, ...] | None = None,
) -> _NerProviderReview:
    """Load source-independent NER evidence for one provider execution.

    :param execution: Provider execution slug.
    :param run_dir: Matching ``raw-<execution>`` directory.
    :param catalog: Verified source-text population.
    :param resolver: Shared source-alignment service.
    :param allow_partial: Permit missing evidence with explicit labels.
    :param scheduled_ids: Optional cross-provider union population.
    :return: Validated provider review data.
    """
    layout = ExecutionArtifactLayout(run_dir)
    if layout.execution != execution:
        raise ValueError(
            f"Provider mapping {execution!r} points to {layout.execution!r}."
        )
    manifest, manifest_sha256 = _load_execution_manifest(
        layout.manifest, allow_partial=allow_partial
    )
    if scheduled_ids is None:
        scheduled_ids = _scheduled_unit_ids(
            manifest=manifest,
            catalog=catalog,
            annotation_root=layout.shared_annotations,
            allow_partial=allow_partial,
        )
    guideline_path, guideline_sha256 = _annotation_guideline_identity(
        layout=layout, allow_partial=allow_partial
    )
    segments: list[_NerReviewSegment] = []
    annotated_unit_count = 0
    for input_unit_id in scheduled_ids:
        unit = catalog.by_id[input_unit_id]
        _validate_source_snapshot(
            layout=layout,
            unit=unit,
            allow_partial=allow_partial,
        )
        annotation_path = (
            layout.annotation_unit(input_unit_id) / "annotation.json"
        )
        annotation = _load_annotation(
            annotation_path,
            input_unit_id=input_unit_id,
            allow_partial=allow_partial,
        )
        if annotation is not None:
            annotated_unit_count += 1
        segments.extend(
            _segments_for_unit(
                execution=execution,
                provider_label=_PROVIDER_LABELS[execution],
                layout=layout,
                unit=unit,
                annotation_path=annotation_path,
                annotation=annotation,
                resolver=resolver,
            )
        )
    return _NerProviderReview(
        execution=execution,
        label=_PROVIDER_LABELS[execution],
        run_dir=run_dir,
        run_manifest_sha256=manifest_sha256,
        input_catalog_sha256=catalog.file_sha256,
        annotation_guideline_path=guideline_path,
        annotation_guideline_sha256=guideline_sha256,
        scheduled_unit_count=len(scheduled_ids),
        annotated_unit_count=annotated_unit_count,
        segments=tuple(segments),
    )


def _provider_unit_ids(provider: _NerProviderReview) -> set[str]:
    """Read each scheduled unit once from its two segment rows.

    :param provider: Validated provider review data.
    :return: Unique input-unit identifiers.
    """
    return {segment.input_unit_id for segment in provider.segments}


def _provider_scheduled_union(
    *,
    providers: tuple[_NerProviderReview, ...],
    catalog: HeaderSublemmaCatalog,
) -> tuple[str, ...]:
    """Order the partial cross-provider population by the frozen catalogue.

    :param providers: Initially loaded provider populations.
    :param catalog: Frozen ordering authority.
    :return: Union of scheduled units in catalogue order.
    """
    selected = set().union(
        *(_provider_unit_ids(provider) for provider in providers)
    )
    return tuple(
        record.input_unit_id
        for record in catalog.records
        if record.input_unit_id in selected
    )


def _load_execution_manifest(
    path: Path, *, allow_partial: bool
) -> tuple[dict[str, Any], str]:
    """Read an execution manifest while permitting an empty partial run.

    :param path: Provider execution-manifest path.
    :param allow_partial: Whether absence becomes an empty diagnostic record.
    :return: Decoded manifest and exact file digest.
    """
    if not path.is_file():
        if allow_partial:
            return {}, ""
        raise ValueError(f"Missing NER execution manifest: {path}")
    return _load_json(path), _sha256_file(path)


def _scheduled_unit_ids(
    *,
    manifest: dict[str, Any],
    catalog: HeaderSublemmaCatalog,
    annotation_root: Path,
    allow_partial: bool,
) -> tuple[str, ...]:
    """Select scheduled and already-annotated units in catalogue order.

    :param manifest: Provider execution manifest.
    :param catalog: Frozen population and ordering authority.
    :param annotation_root: Provider shared-annotation directory.
    :param allow_partial: Whether a missing schedule uses the full catalogue.
    :return: Selected unit identifiers in frozen order.
    """
    run_manifest = manifest.get("run", manifest)
    raw_ids = run_manifest.get("regest_ids") if run_manifest else None
    if not isinstance(raw_ids, list):
        if not allow_partial:
            raise ValueError(
                "NER execution manifest has no scheduled unit IDs."
            )
        raw_ids = [record.input_unit_id for record in catalog.records]
    if not all(isinstance(value, str) for value in raw_ids):
        raise ValueError("NER execution manifest has malformed unit IDs.")
    selected = set(raw_ids)
    if annotation_root.is_dir():
        selected.update(
            path.parent.name
            for path in annotation_root.glob("*/annotation.json")
        )
    unknown = sorted(selected - set(catalog.by_id))
    if unknown:
        raise ValueError(
            "NER evidence names units outside the frozen input catalogue: "
            + ", ".join(unknown)
        )
    return tuple(
        record.input_unit_id
        for record in catalog.records
        if record.input_unit_id in selected
    )


def _annotation_guideline_identity(
    *, layout: ExecutionArtifactLayout, allow_partial: bool
) -> tuple[str, str]:
    """Load and verify the provider's frozen annotation-guideline identity.

    :param layout: Provider evidence paths.
    :param allow_partial: Whether missing provenance becomes an empty identity.
    :return: Run-relative guideline path and verified digest.
    """
    provenance_path = layout.provenance / "manifest.json"
    if not provenance_path.is_file():
        if allow_partial:
            return "", ""
        raise ValueError(f"Missing NER provenance manifest: {provenance_path}")
    provenance = _load_json(provenance_path)
    inputs = provenance.get("inputs")
    entry = (
        inputs.get("annotation_guidelines")
        if isinstance(inputs, dict)
        else None
    )
    if not isinstance(entry, dict):
        if allow_partial:
            return "", ""
        raise ValueError("NER provenance has no annotation-guideline entry.")
    relative = entry.get("path")
    expected_hash = entry.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError("NER annotation-guideline provenance is malformed.")
    source = layout.run_root / relative
    if not source.is_file() or _sha256_file(source) != expected_hash:
        raise ValueError(
            "Frozen NER annotation guidelines are missing or changed."
        )
    return relative, expected_hash


def _validate_source_snapshot(
    *,
    layout: ExecutionArtifactLayout,
    unit: HeaderSublemmaInput,
    allow_partial: bool,
) -> None:
    """Require provider source snapshots to match the input catalogue.

    :param layout: Provider evidence paths.
    :param unit: Frozen catalogue record used by every condition.
    :param allow_partial: Whether an absent snapshot is allowed.
    :return: ``None``.
    """
    candidates = (
        layout.provenance
        / "raw-regests"
        / f"{portable_name(unit.input_unit_id)}.json",
        layout.intermediate_condition("haiu_rag_ontologizer")
        / "provenance"
        / "raw_regests"
        / f"{portable_name(unit.input_unit_id)}.json",
    )
    path = next(
        (candidate for candidate in candidates if candidate.is_file()), None
    )
    if path is None:
        if allow_partial:
            return
        raise ValueError(
            f"Missing frozen source snapshot for {unit.input_unit_id}."
        )
    payload = _load_json(path)
    subentries = payload.get("subentries")
    if (
        payload.get("regest_id") != unit.input_unit_id
        or payload.get("header") != unit.header
        or subentries != [unit.sublemma]
    ):
        raise ValueError(
            f"Frozen source text disagrees for {unit.input_unit_id}."
        )


def _load_annotation(
    path: Path, *, input_unit_id: str, allow_partial: bool
) -> dict[str, Any] | None:
    """Read one annotation record or label its absence in partial mode.

    :param path: Frozen annotation JSON path.
    :param input_unit_id: Unit identity expected inside the record.
    :param allow_partial: Whether absence returns ``None``.
    :return: Validated annotation object or ``None``.
    """
    if not path.is_file():
        if allow_partial:
            return None
        raise ValueError(
            f"Missing shared NER annotation for {input_unit_id}: {path}"
        )
    annotation = _load_json(path)
    if annotation.get("regest_id") != input_unit_id:
        raise ValueError(f"Shared NER annotation has the wrong unit ID: {path}")
    content = annotation.get("content")
    if not isinstance(content, dict):
        raise ValueError(f"Shared NER annotation has no content: {path}")
    return annotation


def _segments_for_unit(
    *,
    execution: str,
    provider_label: str,
    layout: ExecutionArtifactLayout,
    unit: HeaderSublemmaInput,
    annotation_path: Path,
    annotation: dict[str, Any] | None,
    resolver: EntitySpanResolver,
) -> tuple[_NerReviewSegment, _NerReviewSegment]:
    """Resolve the header and selected sublemma without crossing boundaries.

    :param execution: Provider execution slug.
    :param provider_label: Human-facing provider name.
    :param layout: Provider evidence paths.
    :param unit: Frozen source-text record.
    :param annotation_path: Expected annotation artifact path.
    :param annotation: Decoded annotation or ``None``.
    :param resolver: Shared source-alignment service.
    :return: Header and sublemma review records.
    """
    content = annotation.get("content", {}) if annotation is not None else {}
    header_entities = _entity_records(
        content.get("header_entities", []),
        field_name="header_entities",
    )
    sublemma_entities = _entity_records(
        content.get("subentry_entities", []),
        field_name="subentry_entities",
        required_subentry_index=0,
    )
    annotation_relative = (
        annotation_path.relative_to(layout.run_root).as_posix()
        if annotation_path.is_file()
        else ""
    )
    annotation_sha256 = (
        _sha256_file(annotation_path) if annotation_path.is_file() else ""
    )
    common = {
        "provider": execution,
        "provider_label": provider_label,
        "input_unit_id": unit.input_unit_id,
        "source_regest_id": unit.source_regest_id,
        "source_sublemma_number": unit.source_sublemma_number,
        "annotation_available": annotation is not None,
        "annotation_path": annotation_relative,
        "annotation_sha256": annotation_sha256,
        "annotation_model": str(
            annotation.get("annotation_model", "")
            if annotation is not None
            else ""
        ),
        "annotation_version": str(
            annotation.get("version", "") if annotation is not None else ""
        ),
    }
    return (
        _make_segment(
            segment="Header",
            source_text=unit.header,
            entities=header_entities,
            resolver=resolver,
            common=common,
        ),
        _make_segment(
            segment="Sublemma",
            source_text=unit.sublemma,
            entities=sublemma_entities,
            resolver=resolver,
            common=common,
        ),
    )


def _entity_records(
    value: Any,
    *,
    field_name: str,
    required_subentry_index: int | None = None,
) -> tuple[tuple[str, str], ...]:
    """Validate generated entity dictionaries before matching them.

    :param value: Raw annotation list.
    :param field_name: Field identity used in validation errors.
    :param required_subentry_index: Allowed subentry when applicable.
    :return: Entity type and surface-value pairs in generated order.
    """
    if not isinstance(value, list):
        raise ValueError(f"NER annotation field {field_name} is not a list.")
    records: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"NER annotation field {field_name} is malformed.")
        entity_type = item.get("type")
        surface = item.get("value")
        if (
            not isinstance(entity_type, str)
            or not entity_type.strip()
            or not isinstance(surface, str)
            or not surface.strip()
        ):
            raise ValueError(f"NER annotation field {field_name} is malformed.")
        if (
            required_subentry_index is not None
            and item.get("subentry_index") != required_subentry_index
        ):
            raise ValueError(
                "NER subentry annotation lies outside its declared sublemma."
            )
        records.append((entity_type, surface))
    return tuple(records)


def _make_segment(
    *,
    segment: str,
    source_text: str,
    entities: tuple[tuple[str, str], ...],
    resolver: EntitySpanResolver,
    common: dict[str, Any],
) -> _NerReviewSegment:
    """Attach stable mention identities and resolve one source segment.

    :param segment: ``Header`` or ``Sublemma``.
    :param source_text: Original source text for that segment.
    :param entities: Validated generated type and value pairs.
    :param resolver: Shared source-alignment service.
    :param common: Unit, provider, and annotation metadata.
    :return: Complete segment review record.
    """
    segment_slug = segment.lower()
    mentions = tuple(
        EntityMention(
            mention_id=(
                f"{common['provider']}:{common['input_unit_id']}:"
                f"{segment_slug}:M{index}"
            ),
            entity_type=entity_type,
            value=surface,
        )
        for index, (entity_type, surface) in enumerate(entities, start=1)
    )
    return _NerReviewSegment(
        **common,
        segment=segment,
        source_text=source_text,
        source_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        results=resolver.resolve(source_text, mentions),
    )


def _validate_provider_agreement(
    providers: tuple[_NerProviderReview, ...], *, allow_partial: bool
) -> None:
    """Reject source or guideline drift across provider review surfaces.

    :param providers: Validated provider review data.
    :param allow_partial: Whether an absent guideline identity is allowed.
    :return: ``None``.
    """
    if len(providers) < 2:
        return
    available_guidelines = {
        provider.annotation_guideline_sha256
        for provider in providers
        if provider.annotation_guideline_sha256
    }
    if len(available_guidelines) > 1:
        raise ValueError("Provider NER annotation-guideline hashes disagree.")
    if not allow_partial and len(available_guidelines) != 1:
        raise ValueError(
            "Provider NER annotation-guideline identity is missing."
        )
    source_by_provider = [
        {
            (
                segment.input_unit_id,
                segment.segment,
            ): (segment.source_text, segment.source_sha256)
            for segment in provider.segments
        }
        for provider in providers
    ]
    shared_keys = set.intersection(
        *(set(source) for source in source_by_provider)
    )
    for key in shared_keys:
        if len({source[key] for source in source_by_provider}) != 1:
            raise ValueError(
                f"Provider NER source text disagrees for {key[0]} {key[1]}."
            )


def _prepare_outputs(*, paths: tuple[Path, ...], overwrite: bool) -> None:
    """Create the output directory and replace only named owned artifacts.

    :param paths: Workbook and manifest paths owned by this export.
    :param overwrite: Whether existing owned outputs may be replaced.
    :return: ``None``.
    """
    if len({path.parent for path in paths}) != 1:
        raise ValueError("NER review outputs must share one directory.")
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise ValueError(
            "Historian NER review export already exists: "
            + ", ".join(path.name for path in existing)
        )
    for path in existing:
        path.unlink()


def _write_ner_review_workbook(
    *,
    path: Path,
    providers: tuple[_NerProviderReview, ...],
    partial: bool,
) -> None:
    """Render review, entity, omission, provenance, and validation sheets.

    :param path: Destination workbook path.
    :param providers: Provider data rendered into separate review sheets.
    :param partial: Whether the workbook needs a diagnostic status label.
    :return: ``None``.
    """
    workbook = xlsxwriter.Workbook(path, {"strings_to_urls": False})
    try:
        formats = _ner_formats(workbook)
        _write_guide_sheet(
            sheet=workbook.add_worksheet("NER_Guide"),
            formats=formats,
            providers=providers,
            partial=partial,
        )
        for provider in providers:
            sheet_name = f"{provider.label.replace(' ', '_')}_NER"
            _write_provider_sheet(
                sheet=workbook.add_worksheet(sheet_name),
                formats=formats,
                provider=provider,
            )
        all_segments = tuple(
            segment for provider in providers for segment in provider.segments
        )
        _write_entity_sheet(
            sheet=workbook.add_worksheet("NER_Entities"),
            formats=formats,
            segments=all_segments,
        )
        _write_missing_sheet(
            sheet=workbook.add_worksheet("NER_Missing"),
            formats=formats,
            segments=all_segments,
        )
        provenance = workbook.add_worksheet("_Provenance")
        _write_provenance_sheet(
            sheet=provenance,
            formats=formats,
            providers=providers,
            partial=partial,
        )
        provenance.hide()
        validation = workbook.add_worksheet("_Validation")
        _write_validation_sheet(validation)
        validation.hide()
    finally:
        workbook.close()


def _ner_formats(workbook: Any) -> dict[str, Any]:
    """Create the shared workbook styles and local span colors.

    :param workbook: XlsxWriter workbook that owns every format.
    :return: Named cell and rich-fragment formats.
    """
    formats = {
        "title": workbook.add_format(
            {"bold": True, "font_size": 14, "font_color": "#17365D"}
        ),
        "header": workbook.add_format(
            {
                "bold": True,
                "bg_color": "#D9EAF7",
                "border": 1,
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "cell": workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top"}
        ),
        "input": workbook.add_format(
            {
                "border": 1,
                "bg_color": "#FFF2CC",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "wrap": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "warning": workbook.add_format(
            {"bg_color": "#FCE4D6", "bold": True, "text_wrap": True}
        ),
        "ambiguous": workbook.add_format({"font_color": "#C65911"}),
        "unmatched": workbook.add_format({"font_color": "#9C0006"}),
        "ambiguous_cell": workbook.add_format(
            {
                "font_color": "#C65911",
                "border": 1,
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "unmatched_cell": workbook.add_format(
            {
                "font_color": "#9C0006",
                "border": 1,
                "text_wrap": True,
                "valign": "top",
            }
        ),
    }
    formats["span_colors"] = tuple(
        workbook.add_format(
            {"font_color": color, "bold": True, "underline": True}
        )
        for color in NER_REVIEW_COLORS
    )
    formats["span_cell_colors"] = tuple(
        workbook.add_format(
            {
                "font_color": color,
                "bold": True,
                "underline": True,
                "border": 1,
                "text_wrap": True,
                "valign": "top",
            }
        )
        for color in NER_REVIEW_COLORS
    )
    return formats


def _write_guide_sheet(
    *,
    sheet: Any,
    formats: dict[str, Any],
    providers: tuple[_NerProviderReview, ...],
    partial: bool,
) -> None:
    """Explain markers, uncertainty, verdicts, and correction ownership.

    :param sheet: Guide worksheet.
    :param formats: Workbook-owned display formats.
    :param providers: Provider counts and names shown to the reviewer.
    :param partial: Whether evidence absence is expected and labelled.
    :return: ``None``.
    """
    sheet.set_column(0, 0, 28)
    sheet.set_column(1, 1, 110)
    sheet.write(0, 0, "Historian NER review", formats["title"])
    status = (
        "PARTIAL DIAGNOSTIC EXPORT — unavailable annotations remain visible."
        if partial
        else "Complete frozen shared-annotation export."
    )
    rows = (
        ("Status", status),
        (
            "Provider sheets",
            "Review the marked source text beside its entity key. Provider "
            "identity is visible because the NER output is provider-specific.",
        ),
        (
            "Markers",
            "[n] is authoritative. Eight dark colors repeat within each "
            "segment. One marker may list several types on the exact same "
            "span. Overlapping spans share a color but keep separate markers.",
        ),
        (
            "Approximate matches",
            "≈[n] passed the conservative fuzzy rule. Check its location even "
            "when it is colored. The entity sheet records method and score.",
        ),
        (
            "Unresolved annotations",
            "Orange means several plausible locations; red means no accepted "
            "location. They are deliberately not colored in the source text.",
        ),
        (
            "Location verdict",
            ", ".join(NER_REVIEW_LOCATION_VERDICTS) + ".",
        ),
        (
            "Type verdict",
            ", ".join(NER_REVIEW_TYPE_VERDICTS) + ".",
        ),
        (
            "Missing entities",
            "Use NER_Missing to record false negatives. One blank row is "
            "pre-populated for every provider and source segment; insert or "
            "copy rows when a segment has several missing entities.",
        ),
        (
            "Evidence rule",
            "Frozen annotations and source text remain authoritative inputs. "
            "Historian corrections are editable review data, not changes to "
            "the immutable raw artifacts.",
        ),
        (
            "Providers",
            "; ".join(
                f"{provider.label}: {provider.annotated_unit_count}/"
                f"{provider.scheduled_unit_count} units annotated"
                for provider in providers
            ),
        ),
    )
    for row_index, (label, detail) in enumerate(rows, start=2):
        sheet.write(row_index, 0, label, formats["header"])
        sheet.write(row_index, 1, detail, formats["wrap"])
        sheet.set_row(row_index, 45)


def _write_provider_sheet(
    *, sheet: Any, formats: dict[str, Any], provider: _NerProviderReview
) -> None:
    """Write one row per provider, input unit, and declared text segment.

    :param sheet: Provider review worksheet.
    :param formats: Workbook-owned display formats.
    :param provider: Validated provider review data.
    :return: ``None``.
    """
    headers = (
        "input_unit_id",
        "source_regest_id",
        "source_sublemma_number",
        "segment",
        "annotation_status",
        "plain_source_text",
        "marked_source_text",
        "entity_key",
        "unresolved_annotations",
        "segment_notes",
        "review_completion",
    )
    widths = (24, 16, 12, 11, 18, 58, 58, 48, 58, 32, 18)
    sheet.freeze_panes(1, 5)
    sheet.autofilter(0, 0, len(provider.segments), len(headers) - 1)
    for column, (header, width) in enumerate(zip(headers, widths, strict=True)):
        sheet.set_column(column, column, width)
        sheet.write(0, column, header, formats["header"])
    for row_index, segment in enumerate(provider.segments, start=1):
        fixed_values = (
            segment.input_unit_id,
            segment.source_regest_id,
            segment.source_sublemma_number,
            segment.segment,
            "Available" if segment.annotation_available else "Unavailable",
            segment.source_text,
        )
        for column, value in enumerate(fixed_values):
            sheet.write(row_index, column, value, formats["cell"])
        _write_marked_source(
            sheet=sheet,
            row=row_index,
            column=6,
            segment=segment,
            formats=formats,
        )
        _write_entity_key(
            sheet=sheet,
            row=row_index,
            column=7,
            segment=segment,
            formats=formats,
        )
        _write_unresolved_annotations(
            sheet=sheet,
            row=row_index,
            column=8,
            segment=segment,
            formats=formats,
        )
        sheet.write_blank(row_index, 9, None, formats["input"])
        sheet.write(row_index, 10, "Not started", formats["input"])
        sheet.set_row(row_index, _segment_row_height(segment))
    if provider.segments:
        sheet.data_validation(
            1,
            10,
            len(provider.segments),
            10,
            {
                "validate": "list",
                "source": "='_Validation'!$C$1:$C$3",
            },
        )


def _display_markers(segment: _NerReviewSegment) -> tuple[_DisplayMarker, ...]:
    """Assign local marker numbers and colors to accepted unique spans.

    :param segment: Source text and resolved annotation results.
    :return: Offset-ordered marker groups.
    """
    grouped: dict[tuple[int, int], list[ResolvedEntityMention]] = defaultdict(
        list
    )
    for result in segment.results:
        if result.selected is not None:
            grouped[
                (result.selected.start_offset, result.selected.end_offset)
            ].append(result)
    spans = sorted(grouped)
    markers: list[_DisplayMarker] = []
    cluster_end = -1
    color_index = -1
    for number, (start, end) in enumerate(spans, start=1):
        if start >= cluster_end:
            color_index = (color_index + 1) % len(NER_REVIEW_COLORS)
            cluster_end = end
        else:
            cluster_end = max(cluster_end, end)
        markers.append(
            _DisplayMarker(
                number=number,
                color_index=color_index,
                start_offset=start,
                end_offset=end,
                results=tuple(grouped[(start, end)]),
            )
        )
    return tuple(markers)


def _write_marked_source(
    *,
    sheet: Any,
    row: int,
    column: int,
    segment: _NerReviewSegment,
    formats: dict[str, Any],
) -> None:
    """Render colored intervals and insert markers at span endpoints.

    :param sheet: Provider review worksheet.
    :param row: Zero-based target row.
    :param column: Zero-based target column.
    :param segment: Source text and resolved annotations.
    :param formats: Workbook-owned rich-text and cell formats.
    :return: ``None``.
    """
    markers = _display_markers(segment)
    if not markers:
        sheet.write(row, column, segment.source_text, formats["cell"])
        return
    boundaries = sorted(
        {
            0,
            len(segment.source_text),
            *(marker.start_offset for marker in markers),
            *(marker.end_offset for marker in markers),
        }
    )
    endings: dict[int, list[_DisplayMarker]] = defaultdict(list)
    for marker in markers:
        endings[marker.end_offset].append(marker)
    fragments: list[Any] = []
    color_formats = formats["span_colors"]
    for start, end in zip(boundaries, boundaries[1:]):
        if start < end:
            covering = next(
                (
                    marker
                    for marker in markers
                    if marker.start_offset <= start and end <= marker.end_offset
                ),
                None,
            )
            source = segment.source_text[start:end]
            if covering is None:
                fragments.append(source)
            else:
                fragments.extend((color_formats[covering.color_index], source))
        for marker in sorted(
            endings.get(end, ()), key=lambda item: item.number
        ):
            fragments.extend((color_formats[marker.color_index], marker.label))
    sheet.write_rich_string(row, column, *fragments, formats["cell"])


def _write_entity_key(
    *,
    sheet: Any,
    row: int,
    column: int,
    segment: _NerReviewSegment,
    formats: dict[str, Any],
) -> None:
    """Place same-color marker definitions beside the marked source text.

    :param sheet: Provider review worksheet.
    :param row: Zero-based target row.
    :param column: Zero-based target column.
    :param segment: Source text and resolved annotations.
    :param formats: Workbook-owned rich-text and cell formats.
    :return: ``None``.
    """
    markers = _display_markers(segment)
    if not markers:
        message = (
            "Annotation unavailable"
            if not segment.annotation_available
            else "No resolved annotations"
        )
        sheet.write(row, column, message, formats["cell"])
        return
    if len(markers) == 1:
        marker = markers[0]
        definitions = "; ".join(
            f"{result.mention.entity_type}: {result.mention.value}"
            for result in marker.results
        )
        score = ""
        if marker.is_fuzzy:
            fuzzy_scores = [
                result.selected.score
                for result in marker.results
                if result.selected is not None
                and result.selected.method == "fuzzy"
            ]
            score = f" (score {min(fuzzy_scores):.1f})"
        sheet.write(
            row,
            column,
            f"{marker.label} {definitions}{score}",
            formats["span_cell_colors"][marker.color_index],
        )
        return
    fragments: list[Any] = []
    color_formats = formats["span_colors"]
    for index, marker in enumerate(markers):
        if index:
            fragments.append("\n")
        definitions = "; ".join(
            f"{result.mention.entity_type}: {result.mention.value}"
            for result in marker.results
        )
        score = ""
        if marker.is_fuzzy:
            fuzzy_scores = [
                result.selected.score
                for result in marker.results
                if result.selected is not None
                and result.selected.method == "fuzzy"
            ]
            score = f" (score {min(fuzzy_scores):.1f})"
        fragments.extend(
            (
                color_formats[marker.color_index],
                f"{marker.label} {definitions}{score}",
            )
        )
    sheet.write_rich_string(row, column, *fragments, formats["cell"])


def _write_unresolved_annotations(
    *,
    sheet: Any,
    row: int,
    column: int,
    segment: _NerReviewSegment,
    formats: dict[str, Any],
) -> None:
    """Show ambiguous and unmatched annotations without false highlights.

    :param sheet: Provider review worksheet.
    :param row: Zero-based target row.
    :param column: Zero-based target column.
    :param segment: Source text and unresolved annotations.
    :param formats: Workbook-owned warning and cell formats.
    :return: ``None``.
    """
    unresolved = [
        result for result in segment.results if result.status != "resolved"
    ]
    if not unresolved:
        sheet.write_blank(row, column, None, formats["cell"])
        return
    if len(unresolved) == 1:
        result = unresolved[0]
        candidates = "; ".join(
            f"{candidate.candidate_id} {candidate.start_offset}:"
            f"{candidate.end_offset} {candidate.context}"
            for candidate in result.candidates
        )
        detail = (
            f"{result.status.upper()} {result.mention.mention_id} "
            f"{result.mention.entity_type}: {result.mention.value}"
        )
        if candidates:
            detail = f"{detail} | {candidates}"
        sheet.write(row, column, detail, formats[f"{result.status}_cell"])
        return
    fragments: list[Any] = []
    for index, result in enumerate(unresolved):
        if index:
            fragments.append("\n")
        candidates = "; ".join(
            f"{candidate.candidate_id} {candidate.start_offset}:"
            f"{candidate.end_offset} {candidate.context}"
            for candidate in result.candidates
        )
        detail = (
            f"{result.status.upper()} {result.mention.mention_id} "
            f"{result.mention.entity_type}: {result.mention.value}"
        )
        if candidates:
            detail = f"{detail} | {candidates}"
        fragments.extend((formats[result.status], detail))
    sheet.write_rich_string(row, column, *fragments, formats["cell"])


def _segment_row_height(segment: _NerReviewSegment) -> float:
    """Estimate enough vertical space for marked text and adjacent keys.

    :param segment: Source text and resolution results shown in one row.
    :return: Bounded Excel row height in points.
    """
    source_lines = max(1, len(segment.source_text) // 70 + 1)
    entity_lines = max(1, len(_display_markers(segment)))
    unresolved_lines = sum(
        max(1, len(result.candidates))
        for result in segment.results
        if result.status != "resolved"
    )
    return float(
        min(
            300, max(45, 15 * max(source_lines, entity_lines, unresolved_lines))
        )
    )


def _write_entity_sheet(
    *,
    sheet: Any,
    formats: dict[str, Any],
    segments: tuple[_NerReviewSegment, ...],
) -> None:
    """Write one auditable structured row per predicted annotation.

    :param sheet: Structured entity-review worksheet.
    :param formats: Workbook-owned display and input formats.
    :param segments: All provider source segments.
    :return: ``None``.
    """
    headers = (
        "provider",
        "mention_id",
        "input_unit_id",
        "source_regest_id",
        "source_sublemma_number",
        "segment",
        "predicted_value",
        "predicted_type",
        "automatic_status",
        "resolved_source_text",
        "start_offset",
        "end_offset",
        "match_method",
        "match_score",
        "inferred_candidate_id",
        "candidate_contexts",
        "annotation_model",
        "annotation_version",
        "location_verdict",
        "selected_candidate_id",
        "corrected_surface",
        "type_verdict",
        "corrected_type",
        "historian_notes",
        "review_completion",
        "annotation_sha256",
    )
    widths = {
        "provider": 16,
        "mention_id": 48,
        "input_unit_id": 24,
        "source_regest_id": 16,
        "source_sublemma_number": 12,
        "segment": 11,
        "predicted_value": 30,
        "predicted_type": 22,
        "automatic_status": 14,
        "resolved_source_text": 30,
        "candidate_contexts": 80,
        "historian_notes": 40,
        "annotation_sha256": 66,
    }
    sheet.freeze_panes(1, 8)
    for column, header in enumerate(headers):
        sheet.set_column(column, column, widths.get(header, 18))
        sheet.write(0, column, header, formats["header"])
    row_index = 1
    for segment in segments:
        for result in segment.results:
            selected = result.selected
            contexts = "\n".join(
                f"{candidate.candidate_id} | {candidate.start_offset}:"
                f"{candidate.end_offset} | {candidate.score:.1f} | "
                f"{candidate.context}"
                for candidate in result.candidates
            )
            fixed_values = (
                segment.provider_label,
                result.mention.mention_id,
                segment.input_unit_id,
                segment.source_regest_id,
                segment.source_sublemma_number,
                segment.segment,
                result.mention.value,
                result.mention.entity_type,
                result.status,
                selected.source_text if selected is not None else "",
                selected.start_offset if selected is not None else "",
                selected.end_offset if selected is not None else "",
                selected.method if selected is not None else "",
                selected.score if selected is not None else "",
                selected.candidate_id if selected is not None else "",
                contexts,
                segment.annotation_model,
                segment.annotation_version,
            )
            for column, value in enumerate(fixed_values):
                sheet.write(row_index, column, value, formats["cell"])
            for column in range(18, 24):
                sheet.write_blank(row_index, column, None, formats["input"])
            sheet.write(row_index, 24, "Not started", formats["input"])
            sheet.write(
                row_index, 25, segment.annotation_sha256, formats["cell"]
            )
            sheet.set_row(
                row_index, max(30, 15 * max(1, len(result.candidates)))
            )
            row_index += 1
    if row_index > 1:
        sheet.autofilter(0, 0, row_index - 1, len(headers) - 1)
        sheet.data_validation(
            1,
            18,
            row_index - 1,
            18,
            {"validate": "list", "source": "='_Validation'!$A$1:$A$5"},
        )
        sheet.data_validation(
            1,
            21,
            row_index - 1,
            21,
            {"validate": "list", "source": "='_Validation'!$B$1:$B$4"},
        )
        sheet.data_validation(
            1,
            24,
            row_index - 1,
            24,
            {"validate": "list", "source": "='_Validation'!$C$1:$C$3"},
        )


def _write_missing_sheet(
    *,
    sheet: Any,
    formats: dict[str, Any],
    segments: tuple[_NerReviewSegment, ...],
) -> None:
    """Pre-populate one editable false-negative row per source segment.

    :param sheet: False-negative worksheet.
    :param formats: Workbook-owned display and input formats.
    :param segments: All provider source segments.
    :return: ``None``.
    """
    headers = (
        "provider",
        "input_unit_id",
        "source_regest_id",
        "source_sublemma_number",
        "segment",
        "source_text",
        "missing_surface",
        "expected_type",
        "context_or_offsets",
        "historian_notes",
        "review_completion",
    )
    widths = (16, 24, 16, 12, 11, 70, 30, 24, 36, 40, 18)
    sheet.freeze_panes(1, 6)
    sheet.autofilter(0, 0, len(segments), len(headers) - 1)
    for column, (header, width) in enumerate(zip(headers, widths, strict=True)):
        sheet.set_column(column, column, width)
        sheet.write(0, column, header, formats["header"])
    for row_index, segment in enumerate(segments, start=1):
        fixed_values = (
            segment.provider_label,
            segment.input_unit_id,
            segment.source_regest_id,
            segment.source_sublemma_number,
            segment.segment,
            segment.source_text,
        )
        for column, value in enumerate(fixed_values):
            sheet.write(row_index, column, value, formats["cell"])
        for column in range(6, 10):
            sheet.write_blank(row_index, column, None, formats["input"])
        sheet.write(row_index, 10, "Not started", formats["input"])
        sheet.set_row(
            row_index,
            min(180, max(30, 15 * (len(segment.source_text) // 90 + 1))),
        )
    if segments:
        sheet.data_validation(
            1,
            10,
            len(segments),
            10,
            {"validate": "list", "source": "='_Validation'!$C$1:$C$3"},
        )


def _write_provenance_sheet(
    *,
    sheet: Any,
    formats: dict[str, Any],
    providers: tuple[_NerProviderReview, ...],
    partial: bool,
) -> None:
    """Record enough immutable identity to audit inference and corrections.

    :param sheet: Hidden provenance worksheet.
    :param formats: Workbook-owned display formats.
    :param providers: Provider evidence identities and counts.
    :param partial: Whether the source export permits incomplete evidence.
    :return: ``None``.
    """
    sheet.set_column(0, 0, 42)
    sheet.set_column(1, 1, 110)
    sheet.write_row(0, 0, ("field", "value"), formats["header"])
    rows: list[tuple[str, Any]] = [
        ("export_status", "partial" if partial else "complete"),
        ("matcher_version", EntitySpanResolver.VERSION),
        ("matcher_rules", json.dumps(NER_REVIEW_MATCHER_RULES, sort_keys=True)),
        (
            "ownership",
            "automatic fields are inferred; yellow fields are historian corrections",
        ),
    ]
    for provider in providers:
        prefix = provider.execution
        rows.extend(
            (
                (f"{prefix}.provider", provider.label),
                (f"{prefix}.run_manifest_sha256", provider.run_manifest_sha256),
                (
                    f"{prefix}.input_catalog_sha256",
                    provider.input_catalog_sha256,
                ),
                (
                    f"{prefix}.annotation_guideline_path",
                    provider.annotation_guideline_path,
                ),
                (
                    f"{prefix}.annotation_guideline_sha256",
                    provider.annotation_guideline_sha256,
                ),
                (f"{prefix}.scheduled_units", provider.scheduled_unit_count),
                (f"{prefix}.annotated_units", provider.annotated_unit_count),
                (
                    f"{prefix}.annotation_models",
                    ", ".join(
                        sorted(
                            {
                                segment.annotation_model
                                for segment in provider.segments
                                if segment.annotation_model
                            }
                        )
                    ),
                ),
                (
                    f"{prefix}.annotation_versions",
                    ", ".join(
                        sorted(
                            {
                                segment.annotation_version
                                for segment in provider.segments
                                if segment.annotation_version
                            }
                        )
                    ),
                ),
            )
        )
    for row_index, (field, value) in enumerate(rows, start=1):
        sheet.write(row_index, 0, field, formats["cell"])
        sheet.write(row_index, 1, value, formats["cell"])


def _write_validation_sheet(sheet: Any) -> None:
    """Store dropdown values outside editable reviewer sheets.

    :param sheet: Hidden validation-list worksheet.
    :return: ``None``.
    """
    for row, value in enumerate(NER_REVIEW_LOCATION_VERDICTS):
        sheet.write(row, 0, value)
    for row, value in enumerate(NER_REVIEW_TYPE_VERDICTS):
        sheet.write(row, 1, value)
    for row, value in enumerate(NER_REVIEW_COMPLETION_STATES):
        sheet.write(row, 2, value)


def _ner_review_manifest(
    *,
    workbook_path: Path,
    providers: tuple[_NerProviderReview, ...],
    allow_partial: bool,
    run_root: Path,
) -> dict[str, Any]:
    """Build the machine-readable audit identity for one workbook.

    :param workbook_path: Finished workbook whose digest is recorded.
    :param providers: Provider source identities and resolution results.
    :param allow_partial: Whether missing annotations were permitted.
    :param run_root: Copied run used for portable output paths.
    :return: JSON-compatible manifest payload.
    """
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "allow_partial": allow_partial,
        "matcher_version": EntitySpanResolver.VERSION,
        "matcher_rules": NER_REVIEW_MATCHER_RULES,
        "providers": {
            provider.execution: {
                "label": provider.label,
                "run_manifest_sha256": provider.run_manifest_sha256,
                "input_catalog_sha256": provider.input_catalog_sha256,
                "annotation_guideline_path": provider.annotation_guideline_path,
                "annotation_guideline_sha256": (
                    provider.annotation_guideline_sha256
                ),
                "scheduled_unit_count": provider.scheduled_unit_count,
                "annotated_unit_count": provider.annotated_unit_count,
                "annotation_models": sorted(
                    {
                        segment.annotation_model
                        for segment in provider.segments
                        if segment.annotation_model
                    }
                ),
                "annotation_versions": sorted(
                    {
                        segment.annotation_version
                        for segment in provider.segments
                        if segment.annotation_version
                    }
                ),
                "segment_count": len(provider.segments),
                "entity_count": sum(
                    len(segment.results) for segment in provider.segments
                ),
                "status_counts": _status_counts(provider.segments),
                "source_text_sha256": {
                    f"{segment.input_unit_id}:{segment.segment.lower()}": (
                        segment.source_sha256
                    )
                    for segment in provider.segments
                },
                "annotation_sha256": {
                    segment.annotation_path: segment.annotation_sha256
                    for segment in provider.segments
                    if segment.annotation_path
                },
            }
            for provider in providers
        },
        "outputs": {
            workbook_path.relative_to(run_root).as_posix(): _sha256_file(
                workbook_path
            )
        },
    }


def _status_counts(
    segments: tuple[_NerReviewSegment, ...],
) -> dict[str, int]:
    """Count automatic resolution outcomes for manifest diagnostics.

    :param segments: Provider source segments and their entity results.
    :return: Counts keyed by resolved, ambiguous, and unmatched.
    """
    counts = {"resolved": 0, "ambiguous": 0, "unmatched": 0}
    for segment in segments:
        for result in segment.results:
            counts[result.status] += 1
    return counts


def _load_json(path: Path) -> dict[str, Any]:
    """Read one required JSON object.

    :param path: Evidence artifact path.
    :return: Decoded object.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read NER JSON artifact: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"NER JSON artifact is not an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    """Hash one artifact's exact bytes.

    :param path: Existing file.
    :return: Lowercase SHA-256 digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()
