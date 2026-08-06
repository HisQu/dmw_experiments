"""Retry, recovery, and terminal-state policy for collected cells."""

from __future__ import annotations

import argparse
import time
from typing import Any, Iterator

from dmw_experiments.studies.haiu_comparison.data_collection.dmw.annotations import (
    FrozenAnnotationError,
)
from dmw_experiments.studies.haiu_comparison.data_collection.protocol import (
    LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR,
    LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR,
    LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS,
    LOCAL_RUNTIME_RECOVERY_MODEL_ID,
    LOCAL_RUNTIME_STALE_MODEL_ERROR,
)
from dmw_experiments.studies.haiu_comparison.model.results import (
    ExperimentResult,
)


def _is_terminal_result_payload(payload: dict[str, Any]) -> bool:
    """Return whether a result is complete or must never be retried.

    :param payload: Persisted or in-memory condition result fields.
    :return: Whether the runner must preserve the result without another call.
    """
    return (
        bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
    )


def _is_retry_budget_exhausted(
    payload: dict[str, Any],
    *,
    max_attempts: int,
) -> bool:
    """Return whether a preserved failure has used its normal retry budget.

    The result remains an observed provider outcome even when it is not marked
    ``non_retryable``. A future replay must select and archive it through an
    explicit recovery amendment rather than falling through a normal resume.

    :param payload: Persisted condition result fields.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether no ordinary retry attempt remains.
    """
    attempt = payload.get("attempt")
    return isinstance(attempt, int) and attempt >= max(1, max_attempts)


def _terminal_attempt_state_payload(
    *,
    condition: str,
    regest_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a terminal checkpoint from authoritative result metadata.

    A process can stop after preserving a final retry attempt but before its
    lightweight checkpoint is updated. On resume, this payload repairs only
    that stale checkpoint; it never changes the observed raw result.

    :param condition: Stable experiment condition.
    :param regest_id: Datamodel regest identifier.
    :param result: Persisted terminal result metadata.
    :return: Terminal checkpoint payload for the condition and regest pair.
    """
    success = bool(result.get("success"))
    return {
        "condition": condition,
        "regest_id": regest_id,
        "status": "completed" if success else "failed",
        "attempt": result.get("attempt"),
        "success": success,
    }


def _is_resume_complete_result(
    payload: dict[str, Any],
    *,
    max_attempts: int,
) -> bool:
    """Return whether a resumed runner must preserve an existing row.

    :param payload: Persisted condition result fields.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether the row is terminal or has exhausted ordinary retries.
    """
    return _is_terminal_result_payload(payload) or _is_retry_budget_exhausted(
        payload,
        max_attempts=max_attempts,
    )


def _is_annotation_preparation_retry_exhausted(
    attempt_state: dict[str, Any] | None,
    *,
    max_attempts: int,
) -> bool:
    """Return whether a shared annotation already exhausted normal retries.

    Ontology rows do not yet exist when annotation preparation fails. The
    dedicated checkpoint must therefore be honored on resume, or every process
    restart silently grants the prerequisite another full retry budget.

    :param attempt_state: Durable annotation preparation checkpoint.
    :param max_attempts: Annotation retry budget of the resumed run.
    :return: Whether the checkpoint is a terminal exhausted failure.
    """
    if not isinstance(attempt_state, dict):
        return False
    attempt = attempt_state.get("attempt")
    return (
        attempt_state.get("status") == "failed"
        and isinstance(attempt, int)
        and attempt >= max(1, max_attempts)
    )


def _annotation_preparation_exhaustion_error(
    *,
    regest_id: str,
    attempt_state: dict[str, Any],
    max_attempts: int,
) -> FrozenAnnotationError:
    """Restore a stable terminal error from a shared-annotation checkpoint.

    :param regest_id: Datamodel regest identifier.
    :param attempt_state: Exhausted durable annotation checkpoint.
    :param max_attempts: Annotation retry budget of the resumed run.
    :return: Error preserving the final observed preparation failure.
    """
    attempt_history = attempt_state.get("attempt_history")
    last_error = "Annotation preparation exhausted its retry budget."
    if isinstance(attempt_history, list):
        for item in reversed(attempt_history):
            if not isinstance(item, dict):
                continue
            error_message = item.get("error_message")
            if isinstance(error_message, str) and error_message:
                last_error = error_message
                break
    return FrozenAnnotationError(
        f"Annotation preparation failed for {regest_id} after "
        f"{max(1, max_attempts)} attempt(s): {last_error}"
    )


def _workflow_conditions_require_annotation(
    *,
    regest_id: str,
    conditions: tuple[str, ...],
    rows_by_key: dict[tuple[str, str], dict[str, Any]],
    max_attempts: int,
) -> bool:
    """Return whether an unfinished workflow condition needs its shared input.

    Completed, terminal, and retry-exhausted workflow rows retain their
    original immutable annotation evidence. A resume must not contact the
    annotation provider for those rows again, because that spends provider
    capacity without changing a pending ontology observation.

    :param regest_id: Candidate regest under consideration.
    :param conditions: Conditions selected for the current run.
    :param rows_by_key: Durable raw observations keyed by condition and ID.
    :param max_attempts: Retry budget configured for the resumed runner.
    :return: Whether at least one workflow condition still requires an
        annotation preparation attempt.
    """
    return any(
        condition.startswith("workflow_")
        and not _is_resume_complete_result(
            rows_by_key.get((condition, regest_id), {}),
            max_attempts=max_attempts,
        )
        for condition in conditions
    )


def _is_output_cap_recovery_candidate(
    payload: dict[str, Any],
    *,
    recovery_cap: int | None,
) -> bool:
    """Identify a terminal length stop caused by one fixed output cap.

    A predictive context budget can also end in a provider length stop, but
    that is an observed capacity outcome rather than a fair replay candidate.
    The recovery protocol therefore requires the failed stage to have used the
    exact configured cap without a context-derived reduction.

    :param payload: Persisted condition result fields.
    :param recovery_cap: Original configured cap selected for recovery.
    :return: Whether this exact terminal result may be replayed by amendment.
    """
    if recovery_cap is None or payload.get("output_truncated") is not True:
        return False
    budgets = payload.get("generation_budget")
    if not isinstance(budgets, dict):
        return False
    for stage in budgets.values():
        if not isinstance(stage, dict):
            continue
        if (
            stage.get("output_truncated") is True
            and stage.get("requested_max_output_tokens") == recovery_cap
            and stage.get("effective_max_output_tokens") == recovery_cap
            and stage.get("output_constrained") is False
        ):
            return True
    return False


def _attach_input_lineage(
    payload: dict[str, Any],
    lineage: dict[str, int | str] | None,
) -> None:
    """Attach pair-source metadata without changing legacy result rows.

    :param payload: Condition result before artifact serialization.
    :param lineage: Pair catalogue identity, or ``None`` for complete regesta.
    :return: ``None``.
    """
    if lineage is not None:
        payload["input_lineage"] = dict(lineage)


def _attach_recovery_metadata(
    payload: dict[str, Any],
    *,
    key: tuple[str, str],
    args: argparse.Namespace,
    output_cap_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    timeout_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    timeout_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    connection_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    connection_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    local_runtime_recovered_archives: dict[tuple[str, str], dict[str, Any]],
    local_runtime_recovery_sources: dict[tuple[str, str], dict[str, Any]],
    local_runtime_annotation_attempt_archives: dict[str, dict[str, Any]],
) -> None:
    """Attach recovery evidence before every durable result checkpoint.

    :param payload: Mutable result metadata that will be persisted.
    :param key: Condition and regest identity of this result.
    :param args: Parsed recovery controls.
    :param output_cap_recovered_archives: Archives created for fixed-cap rows.
    :param timeout_recovered_archives: Archives created for timeout replays.
    :param timeout_recovery_sources: Pre-replay rows used to preserve cap
        recovery provenance.
    :param connection_recovered_archives: Archives created for exhausted
        connection failures.
    :param connection_recovery_sources: Pre-replay connection-failure rows.
    :param local_runtime_recovered_archives: Archives created for local runtime
        configuration and availability failures.
    :param local_runtime_recovery_sources: Pre-replay local runtime failure
        rows used to classify the immutable amendment.
    :param local_runtime_annotation_attempt_archives: Failed shared annotation
        checkpoints reset only for the local-runtime amendment.
    :return: None.
    """
    output_cap_archive_record = output_cap_recovered_archives.get(key)
    if output_cap_archive_record is not None:
        payload["output_cap_recovery"] = {
            "amendment_id": args.output_cap_recovery_id,
            "original_max_output_tokens": args.rerun_output_truncated_at_cap,
            "replacement_max_output_tokens": args.max_output_tokens,
            "superseded_raw_artifact_path": output_cap_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": output_cap_archive_record[
                "canonical_raw_sha256"
            ],
        }
    timeout_archive_record = timeout_recovered_archives.get(key)
    if timeout_archive_record is not None:
        source = timeout_recovery_sources[key]
        output_cap_recovery = source.get("output_cap_recovery")
        if isinstance(output_cap_recovery, dict):
            payload["output_cap_recovery"] = output_cap_recovery
        payload["provider_timeout_recovery"] = {
            "amendment_id": args.provider_timeout_recovery_id,
            "predecessor_output_cap_recovery_id": args.output_cap_recovery_id,
            "superseded_raw_artifact_path": timeout_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": timeout_archive_record[
                "canonical_raw_sha256"
            ],
        }
    connection_archive_record = connection_recovered_archives.get(key)
    if connection_archive_record is not None:
        source = connection_recovery_sources[key]
        payload["connection_recovery"] = {
            "amendment_id": args.connection_recovery_id,
            "predecessor_output_cap_recovery_id": args.output_cap_recovery_id,
            "original_failure_code": source.get("failure_code"),
            "original_attempts": source.get("attempt"),
            "superseded_raw_artifact_path": connection_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": connection_archive_record[
                "canonical_raw_sha256"
            ],
        }
    local_runtime_archive_record = local_runtime_recovered_archives.get(key)
    if local_runtime_archive_record is not None:
        source = local_runtime_recovery_sources[key]
        local_runtime_recovery = {
            "amendment_id": args.local_runtime_recovery_id,
            "original_reasons": sorted(
                _local_runtime_recovery_reasons(
                    source,
                    required_attempts=args.max_attempts,
                )
            ),
            "original_failure_code": source.get("failure_code"),
            "original_attempts": source.get("attempt"),
            "corrected_model_id": LOCAL_RUNTIME_RECOVERY_MODEL_ID,
            "verified_context_window_tokens": (
                LOCAL_RUNTIME_RECOVERY_CONTEXT_WINDOW_TOKENS
            ),
            "superseded_raw_artifact_path": local_runtime_archive_record[
                "canonical_raw_artifact_path"
            ],
            "superseded_raw_sha256": local_runtime_archive_record[
                "canonical_raw_sha256"
            ],
        }
        annotation_archive = local_runtime_annotation_attempt_archives.get(
            key[1]
        )
        if annotation_archive is not None:
            local_runtime_recovery["superseded_annotation_attempt_state"] = (
                annotation_archive
            )
        payload["local_runtime_recovery"] = local_runtime_recovery


def _is_provider_timeout_recovery_candidate(
    payload: dict[str, Any],
    *,
    expected_output_cap_recovery_id: str,
    required_attempts: int,
) -> bool:
    """Select only unreplayed exhausted timeouts from one cap amendment.

    :param payload: Persisted condition result fields.
    :param expected_output_cap_recovery_id: Cap amendment that selected the
        original fixed-cap failure.
    :param required_attempts: Attempts the failed replay exhausted.
    :return: Whether the preserved result may receive its one timeout replay.
    """
    if (
        not expected_output_cap_recovery_id
        or bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
        or payload.get("failure_code") != "ontology_generation_failed"
        or payload.get("attempt") != required_attempts
        or isinstance(payload.get("provider_timeout_recovery"), dict)
    ):
        return False
    output_cap_recovery = payload.get("output_cap_recovery")
    if not isinstance(output_cap_recovery, dict):
        return False
    if (
        output_cap_recovery.get("amendment_id")
        != expected_output_cap_recovery_id
    ):
        return False
    attempt_history = payload.get("attempt_history")
    if (
        not isinstance(attempt_history, list)
        or len(attempt_history) < required_attempts
    ):
        return False
    return all(
        isinstance(item, dict)
        and "timed out" in str(item.get("error_message") or "").lower()
        for item in attempt_history[-required_attempts:]
    )


def _is_connection_recovery_candidate(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> bool:
    """Select only unreplayed exhausted transport failures.

    :param payload: Persisted condition result fields.
    :param required_attempts: Attempts the failed observation exhausted.
    :return: Whether the row may receive its one connection recovery replay.
    """
    if (
        bool(payload.get("success"))
        or bool(payload.get("non_retryable"))
        or payload.get("output_truncated") is True
        or payload.get("failure_code") != "ontology_generation_failed"
        or payload.get("attempt") != required_attempts
        or isinstance(payload.get("connection_recovery"), dict)
    ):
        return False
    attempt_history = payload.get("attempt_history")
    if (
        not isinstance(attempt_history, list)
        or len(attempt_history) < required_attempts
    ):
        return False
    return all(
        isinstance(item, dict)
        and "connection error" in str(item.get("error_message") or "").lower()
        for item in attempt_history[-required_attempts:]
    )


def _is_local_runtime_recovery_candidate(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> bool:
    """Select only unreplayed local runtime configuration failures.

    The selection deliberately excludes output-truncated observations. Those
    rows reached a valid context-derived generation budget and remain
    experimental capacity outcomes even when the local model is reloaded.

    :param payload: Persisted condition result fields.
    :param required_attempts: Retry budget that terminal availability failures
        must have exhausted.
    :return: Whether the row may receive the one approved local replay.
    """
    if (
        bool(payload.get("success"))
        or payload.get("output_truncated") is True
        or isinstance(payload.get("local_runtime_recovery"), dict)
    ):
        return False
    return bool(
        _local_runtime_recovery_reasons(
            payload,
            required_attempts=required_attempts,
        )
    )


def _local_runtime_recovery_reasons(
    payload: dict[str, Any],
    *,
    required_attempts: int,
) -> frozenset[str]:
    """Classify the exact local failures permitted by one amendment.

    :param payload: Persisted condition result fields.
    :param required_attempts: Retry budget for an initial-response outage.
    :return: Stable reason labels supporting the selected replay.
    """
    messages = tuple(_failure_messages(payload))
    reasons: set[str] = set()
    if any(
        LOCAL_RUNTIME_CONTEXT_ADMISSION_ERROR in message for message in messages
    ):
        reasons.add("context_admission_rejected")
    if any(LOCAL_RUNTIME_STALE_MODEL_ERROR in message for message in messages):
        reasons.add("stale_proxy_model_identifier")
    attempt_history = payload.get("attempt_history")
    if (
        payload.get("failure_code") == "ontology_generation_failed"
        and payload.get("attempt") == required_attempts
        and isinstance(attempt_history, list)
        and len(attempt_history) >= required_attempts
        and all(
            isinstance(item, dict)
            and LOCAL_RUNTIME_INITIAL_RESPONSE_ERROR
            in str(item.get("error_message") or "").lower()
            for item in attempt_history[-required_attempts:]
        )
    ):
        reasons.add("http_502_initial_response_unavailable")
    return frozenset(reasons)


def _failure_messages(payload: dict[str, Any]) -> Iterator[str]:
    """Yield nested error strings without inspecting prompt or model output.

    :param payload: JSON-like persisted result whose failure fields are read.
    :return: Lowercase failure-message strings.
    """
    for key, value in payload.items():
        normalized_key = key.lower()
        if isinstance(value, str) and (
            "error" in normalized_key or normalized_key in {"message", "reason"}
        ):
            yield value.lower()
        elif isinstance(value, dict):
            yield from _failure_messages(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _failure_messages(item)


def _validate_output_cap_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Reject ambiguous or unsafe output-cap recovery invocations.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If recovery controls do not describe a valid amendment.
    """
    has_recovery_id = bool(args.output_cap_recovery_id)
    has_recovery_cap = args.rerun_output_truncated_at_cap is not None
    if has_recovery_id != has_recovery_cap:
        raise SystemExit(
            "--output-cap-recovery-id and "
            "--rerun-output-truncated-at-cap must be used together."
        )
    if not has_recovery_id:
        return
    recovery_cap = args.rerun_output_truncated_at_cap
    assert recovery_cap is not None
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Output-cap recovery requires --resume and existing raw results."
        )
    if recovery_cap <= 0:
        raise SystemExit("--rerun-output-truncated-at-cap must be positive.")
    if args.max_output_tokens <= recovery_cap:
        raise SystemExit(
            "--max-output-tokens must exceed the recovered output cap."
        )


def _validate_provider_timeout_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require a provider-timeout replay to extend an output-cap amendment.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the replay lacks its immutable recovery chain.
    """
    if not args.provider_timeout_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Provider-timeout recovery requires --resume and existing raw "
            "results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Provider-timeout recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _validate_connection_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require an auditable replay of exhausted connection failures.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the replay lacks its immutable recovery chain.
    """
    if not args.connection_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Connection recovery requires --resume and existing raw results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Connection recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _validate_local_runtime_recovery_arguments(
    *,
    args: argparse.Namespace,
    has_existing_results: bool,
) -> None:
    """Require an auditable replay after a corrected local runtime.

    :param args: Parsed command-line arguments.
    :param has_existing_results: Whether canonical observations already exist.
    :return: None.
    :raises SystemExit: If the recovery lacks its immutable amendment chain.
    """
    if not args.local_runtime_recovery_id:
        return
    if not args.resume or not has_existing_results:
        raise SystemExit(
            "Local-runtime recovery requires --resume and existing raw results."
        )
    if not args.output_cap_recovery_id:
        raise SystemExit(
            "Local-runtime recovery requires the preceding "
            "--output-cap-recovery-id."
        )


def _update_attempt_metadata(
    *,
    result: ExperimentResult,
    attempt: int,
    attempts: int,
    attempt_history: list[dict[str, Any]],
    total_retry_delay_seconds: float,
    all_attempts_started: float,
    previous_elapsed_seconds: float,
) -> None:
    """Attach retry accounting to the current checkpoint.

    :param result: Current condition result.
    :param attempt: Current one-based attempt number.
    :param attempts: Maximum attempts for this process.
    :param attempt_history: Compact outcomes observed so far.
    :param total_retry_delay_seconds: Completed retry delay.
    :param all_attempts_started: Monotonic start time for the retry loop.
    :param previous_elapsed_seconds: Active elapsed time from earlier processes.
    """
    attempt_duration_seconds = result.payload.get("duration_seconds")
    total_attempt_duration_seconds = round(
        sum(
            float(item["duration_seconds"])
            for item in attempt_history
            if isinstance(item.get("duration_seconds"), int | float)
        ),
        3,
    )
    result.payload.update(
        {
            "attempt": attempt,
            "max_attempts": attempts,
            "attempt_history": attempt_history,
            "attempt_duration_seconds": attempt_duration_seconds,
            "duration_seconds": total_attempt_duration_seconds,
            "duration_measure": (
                "cumulative condition-attempt time excluding runner backoff"
            ),
            "total_attempt_duration_seconds": total_attempt_duration_seconds,
            "ontology_stage_total_attempt_duration_seconds": (
                total_attempt_duration_seconds
            ),
            "total_retry_delay_seconds": round(
                total_retry_delay_seconds,
                3,
            ),
            "total_elapsed_seconds": round(
                previous_elapsed_seconds
                + time.perf_counter()
                - all_attempts_started,
                3,
            ),
        }
    )
    if result.condition.startswith("workflow_") and len(attempt_history) > 1:
        result.payload["ontology_provider_usage_complete"] = False
        result.payload["ontology_provider_usage_scope"] = (
            "final attempt only; failed-attempt provider usage is unavailable"
        )


def _recovered_attempt_history(
    previous_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Copy durable attempt records from an earlier runner process.

    :param previous_result: Raw checkpoint recovered during resume.
    :return: Independent attempt records safe to extend.
    """
    if previous_result is None:
        return []

    raw_history = previous_result.get("attempt_history")
    history = (
        [dict(item) for item in raw_history if isinstance(item, dict)]
        if isinstance(raw_history, list)
        else []
    )
    previous_attempt = previous_result.get("attempt")
    known_attempts = {
        item.get("attempt")
        for item in history
        if isinstance(item.get("attempt"), int)
    }
    if (
        isinstance(previous_attempt, int)
        and previous_attempt > 0
        and previous_attempt not in known_attempts
    ):
        history.append(
            {
                "attempt": previous_attempt,
                "success": bool(previous_result.get("success")),
                "duration_seconds": previous_result.get(
                    "attempt_duration_seconds",
                    previous_result.get("duration_seconds"),
                ),
                "request_duration_seconds": previous_result.get(
                    "request_duration_seconds"
                ),
                "error_message": previous_result.get("error_message"),
            }
        )
    return history


def _numeric_metadata(
    previous_result: dict[str, Any] | None,
    key: str,
) -> float:
    """Read a non-negative numeric checkpoint field.

    :param previous_result: Raw checkpoint recovered during resume.
    :param key: Field to read.
    :return: Non-negative numeric value, or zero when absent.
    """
    value = (previous_result or {}).get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(0.0, float(value))
    return 0.0
