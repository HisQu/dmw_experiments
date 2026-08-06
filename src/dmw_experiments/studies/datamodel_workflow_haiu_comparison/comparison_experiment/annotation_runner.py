"""Prepare and verify immutable annotation inputs for ontology comparisons."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, cast

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.datamodel_api import (
    DatamodelClient,
    WorkflowRequestConfig,
)


class FrozenAnnotationError(RuntimeError):
    """Raised when a shared annotation cannot be prepared or verified."""


@dataclass(frozen=True, slots=True)
class FrozenAnnotation:
    """Exact annotation input shared by both workflow conditions.

    :param regest_id: Datamodel regest identifier.
    :param branch: DMW branch containing the annotation.
    :param version: Annotation guideline version.
    :param content_sha256: Canonical digest of the entity content.
    :param header_entities: Accepted header annotations.
    :param subentry_entities: Accepted subentry annotations.
    :param source: Whether the run generated or adopted the annotation.
    :param created_at: DMW creation timestamp when available.
    :param frozen_at: Timestamp of the experiment snapshot.
    :param annotation_model: Configured annotation model.
    :param generation_dependency: Exact NER and GTA source revisions stored
        with the accepted annotation when DMW exposes them.
    :param preparation: Retry and timing provenance outside ontology timing.
    """

    regest_id: str
    branch: str
    version: str
    content_sha256: str
    header_entities: list[dict[str, Any]]
    subentry_entities: list[dict[str, Any]]
    source: str
    created_at: str | None
    frozen_at: str
    annotation_model: str
    generation_dependency: dict[str, str] | None
    preparation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return the raw, portable annotation artifact.

        :return: JSON-safe annotation content and preparation provenance.
        """
        return {
            "schema_version": 1,
            "regest_id": self.regest_id,
            "branch": self.branch,
            "version": self.version,
            "content_sha256": self.content_sha256,
            "content": {
                "header_entities": self.header_entities,
                "subentry_entities": self.subentry_entities,
            },
            "source": self.source,
            "created_at": self.created_at,
            "frozen_at": self.frozen_at,
            "annotation_model": self.annotation_model,
            "generation_dependency": self.generation_dependency,
            "preparation": self.preparation,
            "provider_usage": None,
            "provider_usage_complete": False,
            "provider_usage_observation": (
                "DMW/NER does not expose provider usage. Annotation "
                "preparation is outside both ontology-condition measurements."
            ),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FrozenAnnotation:
        """Restore and validate one durable annotation snapshot.

        :param payload: Parsed raw-annotation artifact.
        :return: Verified frozen annotation.
        :raises FrozenAnnotationError: If required fields or the digest differ.
        """
        content = payload.get("content")
        if not isinstance(content, dict):
            raise FrozenAnnotationError(
                "Frozen annotation artifact has no content object."
            )
        header_entities = _entity_list(
            content.get("header_entities"),
            field_name="header_entities",
        )
        subentry_entities = _entity_list(
            content.get("subentry_entities"),
            field_name="subentry_entities",
        )
        expected_sha256 = str(payload.get("content_sha256") or "")
        observed_sha256 = annotation_content_sha256(
            header_entities=header_entities,
            subentry_entities=subentry_entities,
        )
        if not expected_sha256 or expected_sha256 != observed_sha256:
            raise FrozenAnnotationError(
                "Frozen annotation artifact digest does not match its content."
            )
        preparation = payload.get("preparation")
        if not isinstance(preparation, dict):
            raise FrozenAnnotationError(
                "Frozen annotation artifact has no preparation provenance."
            )
        generation_dependency = _generation_dependency(
            payload.get("generation_dependency"),
            field_name="frozen annotation generation_dependency",
        )
        created_at = payload.get("created_at")
        return cls(
            regest_id=str(payload.get("regest_id") or ""),
            branch=str(payload.get("branch") or ""),
            version=str(payload.get("version") or ""),
            content_sha256=expected_sha256,
            header_entities=header_entities,
            subentry_entities=subentry_entities,
            source=str(payload.get("source") or ""),
            created_at=str(created_at) if created_at is not None else None,
            frozen_at=str(payload.get("frozen_at") or ""),
            annotation_model=str(payload.get("annotation_model") or ""),
            generation_dependency=generation_dependency,
            preparation=dict(preparation),
        )


@dataclass(frozen=True, slots=True)
class AnnotationPreparationConfig:
    """Controls annotation-only generation before ontology timing.

    :param max_attempts: Preparation attempts in the current runner process.
    :param retry_delay_seconds: Delay between failed preparation attempts.
    :param poll_interval_seconds: DMW progress polling interval.
    :param timeout_seconds: Maximum duration of one generation attempt.
    """

    max_attempts: int
    retry_delay_seconds: float
    poll_interval_seconds: float
    timeout_seconds: float


def annotation_content_sha256(
    *,
    header_entities: list[dict[str, Any]],
    subentry_entities: list[dict[str, Any]],
) -> str:
    """Hash annotation content with deterministic JSON serialization.

    :param header_entities: Header annotations in accepted order.
    :param subentry_entities: Subentry annotations in accepted order.
    :return: SHA-256 hexadecimal digest.
    """
    canonical = json.dumps(
        {
            "header_entities": header_entities,
            "subentry_entities": subentry_entities,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_frozen_annotation(
    *,
    client: DatamodelClient,
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
    preparation_config: AnnotationPreparationConfig,
    existing_snapshot: dict[str, Any] | None = None,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> FrozenAnnotation:
    """Create or adopt one annotation, accept it, and freeze its exact content.

    A durable snapshot is verified against DMW instead of regenerated on
    resume. Without a snapshot, an existing completed annotation is accepted
    unchanged; otherwise the annotation-only API generates it before either
    ontology condition begins.

    :param client: Authenticated DMW client.
    :param regest_id: Datamodel regest identifier.
    :param workflow_config: Branch, model, and annotation settings.
    :param preparation_config: Retry, poll, and timeout controls.
    :param existing_snapshot: Durable raw annotation recovered on resume.
    :param checkpoint: Optional callback for each preparation attempt.
    :return: Exact annotation shared by the ontology conditions.
    :raises FrozenAnnotationError: If preparation or verification fails.
    """
    if existing_snapshot is not None:
        frozen = FrozenAnnotation.from_dict(existing_snapshot)
        _validate_snapshot_identity(
            frozen=frozen,
            regest_id=regest_id,
            workflow_config=workflow_config,
        )
        observed_dependency = verify_frozen_annotation(
            client=client,
            frozen=frozen,
        )
        if (
            frozen.generation_dependency is None
            and observed_dependency is not None
        ):
            frozen = replace(
                frozen,
                generation_dependency=observed_dependency,
            )
        return frozen

    attempts = max(1, preparation_config.max_attempts)
    attempt_history: list[dict[str, Any]] = []
    total_retry_delay_seconds = 0.0
    all_attempts_started = time.perf_counter()

    for attempt in range(1, attempts + 1):
        attempt_started = time.perf_counter()
        try:
            review_data, source = _prepare_annotation_once(
                client=client,
                regest_id=regest_id,
                workflow_config=workflow_config,
                preparation_config=preparation_config,
            )
            duration_seconds = round(time.perf_counter() - attempt_started, 3)
            attempt_history.append(
                {
                    "attempt": attempt,
                    "success": True,
                    "duration_seconds": duration_seconds,
                    "error_message": None,
                }
            )
            frozen = _frozen_from_review(
                review_data=review_data,
                regest_id=regest_id,
                workflow_config=workflow_config,
                source=source,
                preparation={
                    "attempt_history": attempt_history,
                    "total_attempt_duration_seconds": round(
                        sum(
                            float(item["duration_seconds"])
                            for item in attempt_history
                        ),
                        3,
                    ),
                    "total_retry_delay_seconds": round(
                        total_retry_delay_seconds,
                        3,
                    ),
                    "total_elapsed_seconds": round(
                        time.perf_counter() - all_attempts_started,
                        3,
                    ),
                    "timing_scope": (
                        "annotation generation, review, and acceptance; "
                        "excluded from ontology conditions"
                    ),
                },
            )
            verify_frozen_annotation(client=client, frozen=frozen)
            if checkpoint is not None:
                checkpoint(
                    {
                        "status": "completed",
                        "regest_id": regest_id,
                        "attempt": attempt,
                        "content_sha256": frozen.content_sha256,
                        "attempt_history": attempt_history,
                    }
                )
            return frozen
        except FrozenAnnotationError as exc:
            duration_seconds = round(time.perf_counter() - attempt_started, 3)
            attempt_history.append(
                {
                    "attempt": attempt,
                    "success": False,
                    "duration_seconds": duration_seconds,
                    "error_message": str(exc),
                }
            )
            _delete_incomplete_annotation(
                client=client,
                regest_id=regest_id,
                workflow_config=workflow_config,
            )
            if checkpoint is not None:
                checkpoint(
                    {
                        "status": (
                            "retry_pending" if attempt < attempts else "failed"
                        ),
                        "regest_id": regest_id,
                        "attempt": attempt,
                        "attempt_history": attempt_history,
                    }
                )
            if attempt == attempts:
                raise FrozenAnnotationError(
                    f"Annotation preparation failed for {regest_id} after "
                    f"{attempts} attempt(s): {exc}"
                ) from exc
            delay = max(0.0, preparation_config.retry_delay_seconds)
            time.sleep(delay)
            total_retry_delay_seconds += delay

    raise FrozenAnnotationError(
        f"Annotation preparation produced no result for {regest_id}."
    )


def verify_frozen_annotation(
    *,
    client: DatamodelClient,
    frozen: FrozenAnnotation,
) -> dict[str, str] | None:
    """Verify that DMW still stores the exact frozen entity content.

    :param client: Authenticated DMW client.
    :param frozen: Durable annotation snapshot.
    :return: Exact stored NER and GTA revisions when DMW exposes them.
    :raises FrozenAnnotationError: If the annotation is absent, incomplete,
        changed, or has different recorded generation revisions.
    """
    review_data = _get_review_data(
        client=client,
        regest_id=frozen.regest_id,
        version=frozen.version,
        branch=frozen.branch,
        allow_missing=False,
    )
    assert review_data is not None
    if bool(review_data.get("generation_placeholder")):
        raise FrozenAnnotationError(
            f"Frozen annotation for {frozen.regest_id} became incomplete."
        )
    header_entities, subentry_entities = _content_from_review(review_data)
    observed_sha256 = annotation_content_sha256(
        header_entities=header_entities,
        subentry_entities=subentry_entities,
    )
    if observed_sha256 != frozen.content_sha256:
        raise FrozenAnnotationError(
            f"Frozen annotation changed for {frozen.regest_id}: expected "
            f"{frozen.content_sha256}, observed {observed_sha256}."
        )
    observed_dependency = _generation_dependency(
        review_data.get("generation_dependency"),
        field_name="DMW annotation generation_dependency",
    )
    if (
        frozen.generation_dependency is not None
        and observed_dependency != frozen.generation_dependency
    ):
        raise FrozenAnnotationError(
            "Frozen annotation generation dependency changed for "
            f"{frozen.regest_id}: expected {frozen.generation_dependency}, "
            f"observed {observed_dependency}."
        )
    return observed_dependency


def _prepare_annotation_once(
    *,
    client: DatamodelClient,
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
    preparation_config: AnnotationPreparationConfig,
) -> tuple[dict[str, Any], str]:
    review_data = _get_review_data(
        client=client,
        regest_id=regest_id,
        version=workflow_config.annotation_guideline_version,
        branch=workflow_config.branch,
        allow_missing=True,
    )
    generated = False
    if review_data is not None and bool(
        review_data.get("generation_placeholder")
    ):
        _reject_annotation(
            client=client,
            regest_id=regest_id,
            workflow_config=workflow_config,
        )
        review_data = None

    if review_data is None:
        status_code, payload = client.start_annotation_generation(
            regest_id=regest_id,
            config=workflow_config,
        )
        if status_code != 200 or not bool(payload.get("success")):
            raise FrozenAnnotationError(
                "Could not start annotation generation: "
                f"{_response_message(payload)}"
            )
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            raise FrozenAnnotationError(
                "Annotation generation returned no progress session."
            )
        _wait_for_annotation(
            client=client,
            session_id=session_id,
            preparation_config=preparation_config,
        )
        review_data = _get_review_data(
            client=client,
            regest_id=regest_id,
            version=workflow_config.annotation_guideline_version,
            branch=workflow_config.branch,
            allow_missing=False,
        )
        generated = True

    assert review_data is not None
    if bool(review_data.get("generation_placeholder")):
        raise FrozenAnnotationError(
            "Annotation generation finished with an incomplete placeholder."
        )
    header_entities, subentry_entities = _content_from_review(review_data)
    status_code, accept_payload = client.accept_annotation(
        regest_id=regest_id,
        version=workflow_config.annotation_guideline_version,
        branch=workflow_config.branch,
        header_entities=header_entities,
        subentry_entities=subentry_entities,
    )
    if status_code != 200 or not bool(accept_payload.get("success")):
        raise FrozenAnnotationError(
            f"Annotation acceptance failed: {_response_message(accept_payload)}"
        )
    accepted_review = _get_review_data(
        client=client,
        regest_id=regest_id,
        version=workflow_config.annotation_guideline_version,
        branch=workflow_config.branch,
        allow_missing=False,
    )
    assert accepted_review is not None
    accepted_header, accepted_subentries = _content_from_review(accepted_review)
    if (
        accepted_header != header_entities
        or accepted_subentries != subentry_entities
    ):
        raise FrozenAnnotationError(
            "Annotation content changed during acceptance."
        )
    return (
        accepted_review,
        "generated_and_accepted"
        if generated
        else "preexisting_reviewed_and_accepted",
    )


def _wait_for_annotation(
    *,
    client: DatamodelClient,
    session_id: str,
    preparation_config: AnnotationPreparationConfig,
) -> None:
    started = time.perf_counter()
    while True:
        status_code, payload = client.get_annotation_progress(
            session_id=session_id
        )
        if status_code != 200:
            raise FrozenAnnotationError(
                "Annotation progress request failed: "
                f"{_response_message(payload)}"
            )
        result = payload.get("result")
        if isinstance(result, dict):
            if bool(result.get("success")):
                return
            raise FrozenAnnotationError(
                f"Annotation generation failed: {_response_message(result)}"
            )
        if not bool(payload.get("success")):
            raise FrozenAnnotationError(
                f"Annotation progress was lost: {_response_message(payload)}"
            )
        elapsed = time.perf_counter() - started
        if elapsed >= preparation_config.timeout_seconds:
            raise FrozenAnnotationError(
                "Annotation generation exceeded its progress timeout of "
                f"{preparation_config.timeout_seconds:g} seconds."
            )
        time.sleep(max(0.05, preparation_config.poll_interval_seconds))


def _get_review_data(
    *,
    client: DatamodelClient,
    regest_id: str,
    version: str,
    branch: str,
    allow_missing: bool,
) -> dict[str, Any] | None:
    status_code, payload = client.get_annotation_review(
        regest_id=regest_id,
        version=version,
        branch=branch,
    )
    if allow_missing and status_code == 404:
        return None
    if status_code != 200 or not bool(payload.get("success")):
        raise FrozenAnnotationError(
            f"Annotation review failed: {_response_message(payload)}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise FrozenAnnotationError(
            "Annotation review response has no data object."
        )
    return cast(dict[str, Any], data)


def _content_from_review(
    review_data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        _entity_list(
            review_data.get("header_entities"),
            field_name="header_entities",
        ),
        _entity_list(
            review_data.get("subentry_entities"),
            field_name="subentry_entities",
        ),
    )


def _entity_list(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise FrozenAnnotationError(
            f"Annotation {field_name} must be a list of objects."
        )
    return [cast(dict[str, Any], dict(item)) for item in value]


def _frozen_from_review(
    *,
    review_data: dict[str, Any],
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
    source: str,
    preparation: dict[str, Any],
) -> FrozenAnnotation:
    header_entities, subentry_entities = _content_from_review(review_data)
    created_at = review_data.get("created_at")
    return FrozenAnnotation(
        regest_id=regest_id,
        branch=workflow_config.branch,
        version=workflow_config.annotation_guideline_version,
        content_sha256=annotation_content_sha256(
            header_entities=header_entities,
            subentry_entities=subentry_entities,
        ),
        header_entities=header_entities,
        subentry_entities=subentry_entities,
        source=source,
        created_at=str(created_at) if created_at is not None else None,
        frozen_at=datetime.now(timezone.utc).isoformat(),
        annotation_model=workflow_config.annotation_model,
        generation_dependency=_generation_dependency(
            review_data.get("generation_dependency"),
            field_name="DMW annotation generation_dependency",
        ),
        preparation=preparation,
    )


def _generation_dependency(
    value: Any,
    *,
    field_name: str,
) -> dict[str, str] | None:
    """Validate one portable generation-revision mapping.

    :param value: Raw mapping returned by DMW or restored from a snapshot.
    :param field_name: Diagnostic label for malformed data.
    :return: Copied revision mapping, or ``None`` when unavailable.
    :raises FrozenAnnotationError: If the mapping has non-string content.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise FrozenAnnotationError(f"{field_name} must be an object.")
    dependency: dict[str, str] = {}
    for raw_name, raw_commit in value.items():
        if not isinstance(raw_name, str) or not isinstance(raw_commit, str):
            raise FrozenAnnotationError(
                f"{field_name} must map strings to strings."
            )
        name = raw_name.strip()
        commit = raw_commit.strip()
        if not name or not commit:
            raise FrozenAnnotationError(
                f"{field_name} must not contain blank names or revisions."
            )
        dependency[name] = commit
    return dependency


def _validate_snapshot_identity(
    *,
    frozen: FrozenAnnotation,
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
) -> None:
    expected = (
        regest_id,
        workflow_config.branch,
        workflow_config.annotation_guideline_version,
        workflow_config.annotation_model,
    )
    observed = (
        frozen.regest_id,
        frozen.branch,
        frozen.version,
        frozen.annotation_model,
    )
    if observed != expected:
        raise FrozenAnnotationError(
            "Frozen annotation identity differs from the requested run."
        )


def _delete_incomplete_annotation(
    *,
    client: DatamodelClient,
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
) -> None:
    try:
        review_data = _get_review_data(
            client=client,
            regest_id=regest_id,
            version=workflow_config.annotation_guideline_version,
            branch=workflow_config.branch,
            allow_missing=True,
        )
        if review_data is not None and bool(
            review_data.get("generation_placeholder")
        ):
            _reject_annotation(
                client=client,
                regest_id=regest_id,
                workflow_config=workflow_config,
            )
    except FrozenAnnotationError:
        return


def _reject_annotation(
    *,
    client: DatamodelClient,
    regest_id: str,
    workflow_config: WorkflowRequestConfig,
) -> None:
    status_code, payload = client.reject_annotation(
        regest_id=regest_id,
        version=workflow_config.annotation_guideline_version,
        branch=workflow_config.branch,
    )
    if status_code != 200 or not bool(payload.get("success")):
        raise FrozenAnnotationError(
            f"Could not remove incomplete annotation: "
            f"{_response_message(payload)}"
        )


def _response_message(payload: dict[str, Any]) -> str:
    for key in ("message", "error", "detail", "raw"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
        if isinstance(value, dict):
            nested = value.get("message")
            if isinstance(nested, str) and nested.strip():
                return " ".join(nested.split())
    return "DMW returned no diagnostic message."
