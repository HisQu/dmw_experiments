"""Tests for the operational experiment progress watchdog."""

from __future__ import annotations

from types import ModuleType

import pytest

from dmw_experiments.shared.supervision import watch_runner_progress


@pytest.fixture
def watchdog_module():
    """Return the packaged progress watchdog.

    :return: Imported watchdog module.
    """
    return watch_runner_progress


@pytest.mark.parametrize(
    ("newest_checkpoint_at", "current_time", "expected"),
    [
        pytest.param(None, 103.0, False, id="no-checkpoint-during-startup"),
        pytest.param(10.0, 103.0, False, id="historical-checkpoint-on-resume"),
        pytest.param(102.0, 150.0, False, id="recent-checkpoint"),
        pytest.param(10.0, 201.0, True, id="no-progress-after-startup-grace"),
    ],
)
def test_progress_stall_uses_watchdog_start_as_resume_baseline(
    watchdog_module: ModuleType,
    newest_checkpoint_at: float | None,
    current_time: float,
    expected: bool,
) -> None:
    """A resumed run receives one complete checkpoint allowance to start."""
    assert (
        watchdog_module._is_progress_stalled(
            newest_checkpoint_at=newest_checkpoint_at,
            watchdog_started_at=100.0,
            current_time=current_time,
            stall_seconds=100.0,
        )
        is expected
    )
