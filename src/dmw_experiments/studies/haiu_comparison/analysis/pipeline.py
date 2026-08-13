#!/usr/bin/env python3
"""Regenerate every derived Haiu comparison artifact from one run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dmw_experiments.studies.haiu_comparison.analysis.workbooks.ner_review import (
    HistorianNerReviewPaths,
    export_historian_ner_review_workbook,
)
from dmw_experiments.studies.haiu_comparison.analysis.plots.results import (
    plot_workbooks,
)
from dmw_experiments.studies.haiu_comparison.analysis.workbooks.results import (
    ExportPaths,
    HistorianProviderComparisonPaths,
    export_provider_historian_review_workbook,
    export_run,
)
from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    load_run_contract,
)


_PROVIDER_SNAPSHOT_PATTERNS = (
    re.compile(r"^overview-(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)\.xlsx$"),
    re.compile(
        r"^masked_historian_quality_review-"
        r"(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)\.xlsx$"
    ),
    re.compile(
        r"^masked_historian_quality_review-"
        r"(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)"
        r"_evaluation_sidecar\.xlsx$"
    ),
    re.compile(
        r"^historian_quality_review_reveal_key-"
        r"(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)\.json$"
    ),
)
_NER_REVIEW_SNAPSHOT_PATTERNS = (
    re.compile(
        r"^historian_ner_review_[a-z0-9_]+_"
        r"(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)\.xlsx$"
    ),
    re.compile(
        r"^historian_ner_review_[a-z0-9_]+_"
        r"(?P<stamp>\d{8}T\d{6}[A-Za-z0-9+-]+)_manifest\.json$"
    ),
)


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    """Collect every derived artifact emitted by one invocation.

    :param providers: Provider-specific workbook exports keyed by execution.
    :param provider_review: Fresh ungraded cross-provider review export when
        both provider executions are enabled.
    :param ner_review: Provider-visible shared NER span review workbook.
    :param plots: Timestamped figure and grade-analysis directory.
    """

    providers: dict[str, ExportPaths]
    provider_review: HistorianProviderComparisonPaths | None
    ner_review: HistorianNerReviewPaths
    plots: Path


def run_analysis(
    *,
    run_dir: Path,
    allow_partial: bool = False,
    audit_csv: bool = False,
    overwrite: bool = False,
    timestamp: str | None = None,
    quality_review_workbook: Path | None = None,
    quality_reveal_key: Path | None = None,
) -> AnalysisArtifacts:
    """Export workbooks, a review packet, and figures inside one run.

    :param run_dir: Complete copied run containing enabled provider executions.
    :param allow_partial: Permit labelled diagnostics before all cells finish.
    :param audit_csv: Emit machine-readable raw-derived audit tables.
    :param overwrite: Replace exporter-owned workbook files.
    :param timestamp: Stable workbook and plot timestamp for repeatable exports.
    :param quality_review_workbook: Optional separately evaluated review input.
    :param quality_reveal_key: Matching reveal key for the evaluated workbook.
    :return: Paths to provider workbooks, review files, and plots.
    :raises ValueError: If enabled provider data or paired grade inputs are
        missing.
    """
    if (quality_review_workbook is None) != (quality_reveal_key is None):
        raise ValueError(
            "Historian grade analysis requires both quality_review_workbook "
            "and quality_reveal_key."
        )
    root = run_dir.expanduser().resolve()
    spec = load_run_contract(root)
    enabled = tuple(execution.name for execution in spec.enabled_executions)
    missing = [name for name in enabled if not (root / f"raw-{name}").is_dir()]
    if missing:
        raise ValueError(
            "Analysis requires enabled provider directories: "
            + ", ".join(missing)
        )

    stamp = timestamp or datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%Z")
    providers = {
        name: export_run(
            root / f"raw-{name}",
            allow_partial=allow_partial,
            audit_csv=audit_csv,
            overwrite=overwrite,
            timestamp=stamp,
        )
        for name in enabled
    }
    ner_review = export_historian_ner_review_workbook(
        {name: root / f"raw-{name}" for name in enabled},
        workbook_path=(
            root
            / "analysis"
            / "workbooks"
            / f"historian_ner_review_{'_'.join(enabled)}_{stamp}.xlsx"
        ),
        allow_partial=allow_partial,
        overwrite=overwrite,
    )
    _register_ner_review_artifacts(
        root=root,
        providers=providers,
        ner_review=ner_review,
    )
    provider_review: HistorianProviderComparisonPaths | None = None
    if set(enabled) == {"academiccloud", "lmstudio"}:
        review_path = (
            root
            / "analysis"
            / "workbooks"
            / f"historian_quality_review_academiccloud_lmstudio_{stamp}.xlsx"
        )
        if quality_review_workbook is not None and (
            quality_review_workbook.expanduser().resolve()
            == review_path.resolve()
        ):
            raise ValueError(
                "The fresh ungraded review cannot replace the evaluated input."
            )
        provider_review = export_provider_historian_review_workbook(
            academiccloud_run_dir=root / "raw-academiccloud",
            lmstudio_run_dir=root / "raw-lmstudio",
            workbook_path=review_path,
            allow_partial=allow_partial,
            overwrite=overwrite,
        )
    plots = plot_workbooks(
        [providers[name].workbook for name in enabled],
        output_root=root / "plots",
        timestamp=stamp,
        quality_review_workbook=quality_review_workbook,
        quality_reveal_key=quality_reveal_key,
    )
    _archive_superseded_provider_workbook_snapshots(
        root=root,
        execution_names=enabled,
        current_timestamp=stamp,
        protected_paths=tuple(
            path.expanduser().resolve()
            for path in (quality_review_workbook, quality_reveal_key)
            if path is not None
        ),
    )
    return AnalysisArtifacts(
        providers=providers,
        provider_review=provider_review,
        ner_review=ner_review,
        plots=plots,
    )


def _register_ner_review_artifacts(
    *,
    root: Path,
    providers: dict[str, ExportPaths],
    ner_review: HistorianNerReviewPaths,
) -> None:
    """Add the shared review output to provider manifests and reader guides.

    Provider exports are written before the adaptive review workbook because
    they also feed plotting. This final registration keeps each generated
    analysis entry point honest without coupling the NER workbook writer to
    the ontology-results exporter.

    :param root: Complete copied run used for portable paths.
    :param providers: Provider workbook exports created in this invocation.
    :param ner_review: Shared NER workbook and adjacent audit manifest.
    :return: ``None``.
    """
    workbook_relative = ner_review.workbook.relative_to(root).as_posix()
    manifest_relative = ner_review.manifest.relative_to(root).as_posix()
    for provider in providers.values():
        readme_text = provider.readme.read_text(encoding="utf-8")
        entry = (
            f"- `../{ner_review.workbook.name}`: provider-visible shared NER "
            "span review with inline markers and structured corrections."
        )
        if entry not in readme_text:
            anchor = "- `analysis_manifest.json`:"
            readme_text = readme_text.replace(anchor, f"{entry}\n{anchor}")
            provider.readme.write_text(readme_text, encoding="utf-8")

        payload = json.loads(provider.manifest.read_text(encoding="utf-8"))
        outputs = payload.get("outputs")
        if not isinstance(outputs, dict):
            raise ValueError(
                f"Analysis manifest has no output mapping: {provider.manifest}"
            )
        outputs[workbook_relative] = _sha256_file(ner_review.workbook)
        outputs[manifest_relative] = _sha256_file(ner_review.manifest)
        outputs[provider.readme.relative_to(root).as_posix()] = _sha256_file(
            provider.readme
        )
        payload["historian_ner_review"] = {
            "workbook": workbook_relative,
            "workbook_sha256": outputs[workbook_relative],
            "manifest": manifest_relative,
            "manifest_sha256": outputs[manifest_relative],
        }
        provider.manifest.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _archive_superseded_provider_workbook_snapshots(
    *,
    root: Path,
    execution_names: tuple[str, ...],
    current_timestamp: str,
    protected_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Move older generated workbook sets out of the active reader surface.

    This housekeeping runs only after plots finish successfully. A failed
    analysis therefore cannot hide the last complete workbook snapshot.
    Human-named evaluated workbooks never match the exporter-owned patterns.

    :param root: Copied run directory containing ``analysis``.
    :param execution_names: Provider execution slugs exported in this run.
    :param current_timestamp: Successful snapshot that must remain active.
    :param protected_paths: Evaluated inputs that must remain at the exact path
        recorded by the completed plot manifest.
    :return: Archived paths for operational logging or tests.
    :raises FileExistsError: If an archive would overwrite an existing file.
    """
    archived: list[Path] = []
    protected = {path.expanduser().resolve() for path in protected_paths}
    archive_root = (
        root
        / "analysis"
        / "diagnostics"
        / "workbook-archives"
        / f"superseded-by-{current_timestamp}"
    )
    for execution_name in execution_names:
        workbook_dir = root / "analysis" / "workbooks" / execution_name
        if not workbook_dir.is_dir():
            continue
        for source in sorted(workbook_dir.iterdir()):
            if source.resolve() in protected:
                continue
            source_stamp = _provider_snapshot_timestamp(source.name)
            if source_stamp is None or source_stamp == current_timestamp:
                continue
            destination = (
                archive_root / execution_name / source_stamp / source.name
            )
            if destination.exists():
                raise FileExistsError(
                    f"Superseded workbook archive already exists: {destination}"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            archived.append(destination)
    shared_root = root / "analysis" / "workbooks"
    if shared_root.is_dir():
        for source in sorted(shared_root.iterdir()):
            source_stamp = _ner_review_snapshot_timestamp(source.name)
            if source_stamp is None or source_stamp == current_timestamp:
                continue
            destination = archive_root / "shared" / source_stamp / source.name
            if destination.exists():
                raise FileExistsError(
                    f"Superseded workbook archive already exists: {destination}"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            archived.append(destination)
    return tuple(archived)


def _provider_snapshot_timestamp(filename: str) -> str | None:
    """Read an exporter-owned timestamp without matching historian inputs.

    :param filename: Basename found in one provider workbook directory.
    :return: Timestamp embedded by the exporter, or ``None`` for other files.
    """
    for pattern in _PROVIDER_SNAPSHOT_PATTERNS:
        if match := pattern.fullmatch(filename):
            return match.group("stamp")
    return None


def _ner_review_snapshot_timestamp(filename: str) -> str | None:
    """Read a timestamp from an exporter-owned shared NER review artifact.

    :param filename: Basename found in the shared workbook directory.
    :return: Timestamp embedded by the exporter, or ``None`` for other files.
    """
    for pattern in _NER_REVIEW_SNAPSHOT_PATTERNS:
        if match := pattern.fullmatch(filename):
            return match.group("stamp")
    return None


def _sha256_file(path: Path) -> str:
    """Hash one generated artifact after its final write.

    :param path: File whose exact bytes enter a manifest.
    :return: Lowercase SHA-256 digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    """Build the single-run analysis interface.

    :return: Configured command-line parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--audit-csv", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timestamp")
    parser.add_argument("--quality-review-workbook", type=Path)
    parser.add_argument("--quality-reveal-key", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the complete raw-data analysis pipeline.

    :param argv: Optional command-line arguments.
    :return: Process exit status.
    """
    args = _parser().parse_args(argv)
    artifacts = run_analysis(
        run_dir=args.run_dir,
        allow_partial=args.allow_partial,
        audit_csv=args.audit_csv,
        overwrite=args.overwrite,
        timestamp=args.timestamp,
        quality_review_workbook=args.quality_review_workbook,
        quality_reveal_key=args.quality_reveal_key,
    )
    for name, provider in artifacts.providers.items():
        print(f"{name} workbook: {provider.workbook}")
    if artifacts.provider_review is not None:
        print(f"Fresh provider review: {artifacts.provider_review.workbook}")
    print(f"Historian NER review: {artifacts.ner_review.workbook}")
    print(f"Plots and grade analysis: {artifacts.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
