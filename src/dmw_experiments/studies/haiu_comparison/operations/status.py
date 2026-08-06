"""Durable progress summaries for supervised study runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionStatus:
    """Summarize one provider execution's durable and service state."""

    execution: str
    expected_cells: int
    terminal_cells: int
    successful_cells: int
    failed_cells: int
    retry_pending_cells: int
    strict_analysis_ready: bool
    services: dict[str, str]


@dataclass(frozen=True, slots=True)
class RunStatus:
    """Aggregate enabled provider execution progress for one run."""

    run_id: str
    expected_cells: int
    terminal_cells: int
    successful_cells: int
    failed_cells: int
    retry_pending_cells: int
    strict_analysis_ready: bool
    executions: dict[str, ExecutionStatus]
