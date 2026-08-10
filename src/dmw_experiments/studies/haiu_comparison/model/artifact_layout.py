"""Canonical paths for one provider execution's preserved evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from dmw_experiments.studies.haiu_comparison.model.run_contract import (
    CONDITIONS,
)

ARTIFACT_SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class ExecutionArtifactLayout:
    """Resolve every path below one ``raw-<execution>`` directory.

    Conditions remain visible as flat siblings at the execution root. Each
    condition then owns one directory per input unit so prompts, responses,
    retries, and terminal outputs cannot become an undifferentiated file list.

    :param output: Provider execution root named ``raw-<execution>``.
    """

    output: Path

    def __post_init__(self) -> None:
        """Reject roots that cannot identify their provider execution.

        :raises ValueError: If the directory does not use the required name.
        """
        if not self.output.name.startswith("raw-"):
            raise ValueError(
                "Artifact output must be a raw-<execution> directory."
            )

    @property
    def execution(self) -> str:
        """Return the provider execution encoded by the directory name.

        :return: Text following the ``raw-`` prefix.
        """
        return self.output.name.removeprefix("raw-")

    @property
    def run_root(self) -> Path:
        """Return the copied run that owns this execution.

        :return: Parent of the provider execution directory.
        """
        return self.output.parent

    @property
    def manifest(self) -> Path:
        """Return the execution-level run manifest.

        :return: Stable, human-visible manifest path.
        """
        return self.output / "manifest.json"

    @property
    def provenance(self) -> Path:
        """Return the execution-wide frozen provenance directory.

        :return: Directory that is not owned by any scientific condition.
        """
        return self.output / "provenance"

    @property
    def shared_annotations(self) -> Path:
        """Return the condition-independent NER evidence directory.

        :return: Shared annotation intermediate root.
        """
        return self.output / "intermediates-shared_annotations"

    @property
    def amendments(self) -> Path:
        """Return the optional run-amendment directory.

        :return: Execution-local amendment evidence root.
        """
        return self.output / "amendments"

    @property
    def superseded(self) -> Path:
        """Return the optional superseded-evidence directory.

        :return: Execution-local archive root.
        """
        return self.output / "superseded"

    def intermediate_condition(self, condition: str) -> Path:
        """Return one condition's intermediate root.

        :param condition: Stable scientific condition identifier.
        :return: Flat condition directory below the execution root.
        """
        _require_condition(condition)
        return self.output / f"intermediates-{condition}"

    def result_condition(self, condition: str) -> Path:
        """Return one condition's terminal-result root.

        :param condition: Stable scientific condition identifier.
        :return: Flat condition directory below the execution root.
        """
        _require_condition(condition)
        return self.output / f"result-{condition}"

    def intermediate_unit(self, condition: str, unit_id: str) -> Path:
        """Return the complete intermediate bundle for one matrix cell.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :return: Unit directory below its condition.
        """
        return self.intermediate_condition(condition) / portable_name(unit_id)

    def result_unit(self, condition: str, unit_id: str) -> Path:
        """Return the terminal bundle for one matrix cell.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :return: Unit directory below its condition.
        """
        return self.result_condition(condition) / portable_name(unit_id)

    def checkpoint(self, condition: str, unit_id: str) -> Path:
        """Return the crash-recovery checkpoint for one matrix cell.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :return: Stable checkpoint path outside individual attempts.
        """
        return self.intermediate_unit(condition, unit_id) / "checkpoint.json"

    def attempt(
        self,
        condition: str,
        unit_id: str,
        number: int,
        *,
        failed: bool,
    ) -> Path:
        """Return one immutable attempt directory.

        Successful attempts use ``NNN``. Every unsuccessful attempt uses
        ``NNN-failed``, including a final non-retryable model failure.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :param number: One-based attempt number.
        :param failed: Whether the attempt ended unsuccessfully.
        :return: Attempt-specific evidence directory.
        :raises ValueError: If ``number`` is not positive.
        """
        if number < 1:
            raise ValueError("Attempt number must be positive.")
        suffix = "-failed" if failed else ""
        return (
            self.intermediate_unit(condition, unit_id)
            / "attempts"
            / f"{number:03d}{suffix}"
        )

    def result_record(self, condition: str, unit_id: str) -> Path:
        """Return the canonical small terminal record.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :return: Nested schema-v3 JSON path.
        """
        return self.result_unit(condition, unit_id) / "result.json"

    def ontology(self, condition: str, unit_id: str) -> Path:
        """Return the exact terminal Stage-2 text when it was captured.

        :param condition: Stable scientific condition identifier.
        :param unit_id: Input-unit identifier.
        :return: Human-visible ontology output path.
        """
        return self.result_unit(condition, unit_id) / "ontology.ttl"

    def annotation_unit(self, unit_id: str) -> Path:
        """Return shared NER evidence for one input unit.

        :param unit_id: Input-unit identifier.
        :return: Shared annotation unit directory.
        """
        return self.shared_annotations / portable_name(unit_id)

    def iter_result_records(self) -> Iterator[tuple[str, Path]]:
        """Yield canonical schema-v3 terminal records in stable order.

        :return: Condition and result path pairs.
        """
        for condition in CONDITIONS:
            result_root = self.result_condition(condition)
            for result_path in sorted(result_root.glob("*/result.json")):
                yield condition, result_path

    def iter_legacy_result_records(self) -> Iterator[tuple[str, Path]]:
        """Yield pre-v3 flat terminal records for migration and compatibility.

        :return: Condition and legacy JSON path pairs.
        """
        for condition in CONDITIONS:
            result_root = self.result_condition(condition)
            for result_path in sorted(result_root.glob("*.json")):
                yield condition, result_path

    def prepare(self) -> None:
        """Create only directories required by every execution.

        Amendment and superseded roots are deliberately lazy so an ordinary
        run does not advertise recovery protocols that never occurred.

        :return: ``None``.
        """
        for directory in (
            self.output,
            self.provenance,
            self.shared_annotations,
            *(self.intermediate_condition(value) for value in CONDITIONS),
            *(self.result_condition(value) for value in CONDITIONS),
        ):
            directory.mkdir(parents=True, exist_ok=True)


def portable_name(value: str) -> str:
    """Replace characters that are unsafe in portable artifact names.

    :param value: External identifier used as a filename component.
    :return: Identifier containing only letters, numbers, hyphens, and
        underscores.
    """
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in value
    )


def compatibility_prompt_key(label: str) -> str:
    """Translate readable prompt filenames into legacy analysis keys.

    Schema-v3 stores prompts with names such as ``stage-1-system.md``. The
    stable workbook and checkpoint columns predate that layout and use keys
    such as ``stage1_system``. Keeping the translation at the artifact-layout
    boundary prevents writers and readers from defining different aliases.

    :param label: Prompt filename stem or semantic role.
    :return: Existing analysis key without stage-name hyphens.
    """
    normalized = label.replace("stage-1", "stage1").replace("stage-2", "stage2")
    return normalized.replace("-", "_")


def _require_condition(condition: str) -> None:
    """Reject path construction for an unknown condition.

    :param condition: Candidate scientific condition identifier.
    :raises ValueError: If the condition is outside the study contract.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown experiment condition: {condition}")
