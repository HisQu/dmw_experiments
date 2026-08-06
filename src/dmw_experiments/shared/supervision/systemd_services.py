"""Manage long-lived experiment processes through the user service manager."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class ServiceUnits:
    """Name every process belonging to one provider run.

    :param backend: DMW API service unit.
    :param runner: Resumable experiment-runner unit.
    :param watchdog: Fail-closed progress-watchdog unit.
    """

    backend: str
    runner: str
    watchdog: str

    @classmethod
    def for_run(cls, run_id: str, execution: str) -> ServiceUnits:
        """Derive stable service names from run and execution identities.

        :param run_id: Portable lowercase run identifier.
        :param execution: Provider execution slug.
        :return: Complete service-name set.
        """
        prefix = f"dmw-experiment-{run_id}-{execution}"
        return cls(
            backend=f"{prefix}-backend.service",
            runner=f"{prefix}-runner.service",
            watchdog=f"{prefix}-watchdog.service",
        )


class UserServiceManager:
    """Small argv-based facade around user-systemd experiment services."""

    def __init__(self, runner: CommandRunner = subprocess.run) -> None:
        self._runner = runner

    def start(
        self,
        *,
        unit: str,
        command: Sequence[str],
        working_directory: Path,
        log_file: Path,
        restart: str,
        restart_seconds: int | None = None,
    ) -> None:
        """Start one detached transient service with file-backed logs.

        :param unit: Validated service name including ``.service``.
        :param command: Executable and arguments without shell interpolation.
        :param working_directory: Directory used by the child process.
        :param log_file: Append-only stdout and stderr destination.
        :param restart: systemd restart policy.
        :param restart_seconds: Optional delay before automatic runner restart.
        :return: ``None`` after systemd accepts the unit.
        :raises RuntimeError: If the service cannot be started.
        """
        log_file.parent.mkdir(parents=True, exist_ok=True)
        arguments = [
            "systemd-run",
            "--user",
            f"--unit={unit.removesuffix('.service')}",
            "--collect",
            "--property=KillMode=control-group",
            f"--property=Restart={restart}",
            f"--property=StandardOutput=append:{log_file}",
            f"--property=StandardError=append:{log_file}",
            f"--working-directory={working_directory}",
            "--setenv=PYTHONUNBUFFERED=1",
        ]
        if restart_seconds is not None:
            arguments.append(f"--property=RestartSec={restart_seconds}")
        completed = self._runner(
            [*arguments, *command],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Cannot start {unit}: {detail}")

    def active_state(self, unit: str) -> str:
        """Return the user manager's current state for one unit.

        :param unit: Service unit to inspect.
        :return: systemd active-state value, or ``not-found``.
        """
        completed = self._runner(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "--property=LoadState,ActiveState",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            return "not-found"
        values = completed.stdout.splitlines()
        if len(values) >= 2 and values[0].strip() == "not-found":
            return "not-found"
        return values[-1].strip() if values else "not-found"

    def is_active(self, unit: str) -> bool:
        """Return whether one unit is currently executing.

        :param unit: Service unit to inspect.
        :return: Whether its active state can own a live process.
        """
        return self.active_state(unit) in {
            "active",
            "activating",
            "reloading",
        }

    def stop(self, unit: str) -> None:
        """Stop one service and its complete process control group.

        :param unit: Service unit to stop.
        :return: ``None`` when absent or stopped.
        :raises RuntimeError: If systemd rejects a stop for an existing unit.
        """
        if self.active_state(unit) == "not-found":
            return
        completed = self._runner(
            ["systemctl", "--user", "stop", unit],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Cannot stop {unit}: {detail}")

    def interrupt(self, unit: str) -> None:
        """Send SIGINT to the current main process without hiding failures.

        :param unit: Runner service whose main process should checkpoint.
        :return: ``None`` when absent or after systemd accepts the signal.
        :raises RuntimeError: If systemd rejects the signal.
        """
        if not self.is_active(unit):
            return
        completed = self._runner(
            [
                "systemctl",
                "--user",
                "kill",
                "--signal=SIGINT",
                "--kill-whom=main",
                unit,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Cannot interrupt {unit}: {detail}")

    def active_experiment_units(self) -> tuple[str, ...]:
        """List active units owned by this repository's naming contract.

        :return: Sorted active ``dmw-experiment-*`` service names.
        """
        completed = self._runner(
            [
                "systemctl",
                "--user",
                "list-units",
                "--type=service",
                "--state=active,activating,reloading",
                "--plain",
                "--no-legend",
                "dmw-experiment-*.service",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"Cannot inspect active experiment services: {detail}"
            )
        return tuple(
            sorted(
                line.split(maxsplit=1)[0]
                for line in completed.stdout.splitlines()
                if line.strip()
            )
        )

    def active_academiccloud_units(self) -> tuple[str, ...]:
        """List active AcademicCloud units, including legacy experiment names.

        :return: Sorted service names whose unit identity contains the provider.
        """
        completed = self._runner(
            [
                "systemctl",
                "--user",
                "list-units",
                "--type=service",
                "--state=active,activating,reloading",
                "--plain",
                "--no-legend",
                "*academiccloud*.service",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"Cannot inspect active AcademicCloud services: {detail}"
            )
        return tuple(
            sorted(
                line.split(maxsplit=1)[0]
                for line in completed.stdout.splitlines()
                if line.strip()
            )
        )
