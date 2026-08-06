"""Tests for secret-free user-systemd command construction."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dmw_experiments.supervision.systemd_services import (
    ServiceUnits,
    UserServiceManager,
)


class RecordingRunner:
    """Record subprocess argument vectors and return configured output."""

    def __init__(self, *, stdout: str = "") -> None:
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        **_: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Store one command and report success.

        :param command: Argument vector under test.
        :param _: Ignored subprocess keyword arguments.
        :return: Successful completed-process record.
        """
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 0, self.stdout, "")


def test_service_names_are_stable_for_resume() -> None:
    """One run identity always maps to the same three unit names."""
    units = ServiceUnits.for_run("header-sublemma-smoke")

    assert units.runner == (
        "dmw-experiment-header-sublemma-smoke-runner.service"
    )
    assert units.backend.endswith("-backend.service")
    assert units.watchdog.endswith("-watchdog.service")


def test_start_uses_argv_and_file_backed_logs(tmp_path: Path) -> None:
    """Service launch retains no shell expression or credential value."""
    runner = RecordingRunner()
    manager = UserServiceManager(runner=runner)

    manager.start(
        unit="dmw-experiment-smoke-runner.service",
        command=["python", "-m", "example", "--env-file", "private.env"],
        working_directory=tmp_path,
        log_file=tmp_path / "logs" / "runner.log",
        restart="on-failure",
        restart_seconds=30,
    )

    command = runner.calls[0]
    assert command[0] == "systemd-run"
    assert "--property=Restart=on-failure" in command
    assert "--property=RestartSec=30" in command
    assert "python" in command
    assert not any("password" in argument.lower() for argument in command)


def test_active_state_reads_systemd_property_order() -> None:
    """A loaded unit reports the active-state line, not its load state."""
    manager = UserServiceManager(
        runner=RecordingRunner(stdout="loaded\nactive\n")
    )

    assert manager.active_state("example.service") == "active"
