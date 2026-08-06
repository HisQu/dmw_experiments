#!/usr/bin/env python3
"""Fail closed when a runner stops writing durable experiment progress.

Run this beside one experiment runner. It watches canonical results and
condition/annotation attempt states. If none change within the supplied
threshold, it requests a clean runner stop and escalates only when necessary.
The next ``--resume`` invocation repeats the one unfinished condition while
preserving every prior checkpoint.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path


def main() -> int:
    """Watch one runner until it exits or becomes stale.

    A fixed PID is appropriate for non-restarting services. A systemd unit is
    required when ``Restart=on-failure`` preserves the same resumable run
    across OOM exits: its main PID changes after every automatic restart.

    :return: Zero when the watched runner exits normally; 75 after a stale
        fixed-PID runner is shut down.
    """
    parser = argparse.ArgumentParser()
    runner_target = parser.add_mutually_exclusive_group(required=True)
    runner_target.add_argument("--runner-pid", type=int)
    runner_target.add_argument("--runner-unit")
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    # > A runner may spend up to one hour in each of three provider attempts
    # > before it can persist the terminal failure state. Keep this outer
    # > guard longer than that bounded retry window so a live request is not
    # > mistaken for a stalled runner.
    parser.add_argument("--stall-seconds", type=float, default=14_400)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--term-grace-seconds", type=float, default=20)
    args = parser.parse_args()
    if args.stall_seconds <= 0 or args.poll_seconds <= 0:
        raise SystemExit("Stall and poll durations must be positive.")

    watched_roots = (
        args.result_dir / "raw",
        args.result_dir / "attempts",
        args.result_dir / "annotation_attempts",
    )
    watchdog_started_at = time.time()
    runner_inactive_since: float | None = None
    while True:
        runner_is_live = _runner_is_live(
            runner_pid=args.runner_pid, runner_unit=args.runner_unit
        )
        if not runner_is_live:
            if args.runner_unit is None:
                return 0
            # > systemd briefly reports a restart-on-failure unit as inactive
            # > between the OOM exit and its delayed replacement process.
            # > Do not abandon the guard during that gap, but still exit once
            # > a deliberately stopped or normally finished runner is stable.
            if runner_inactive_since is None:
                runner_inactive_since = time.monotonic()
            inactive_grace_seconds = max(args.poll_seconds * 2, 120)
            if (
                time.monotonic() - runner_inactive_since
                < inactive_grace_seconds
            ):
                time.sleep(args.poll_seconds)
                continue
            return 0
        runner_inactive_since = None
        newest = _newest_mtime(watched_roots)
        if not _is_progress_stalled(
            newest_checkpoint_at=newest,
            watchdog_started_at=watchdog_started_at,
            current_time=time.time(),
            stall_seconds=args.stall_seconds,
        ):
            time.sleep(args.poll_seconds)
            continue
        target = (
            f"unit {args.runner_unit}"
            if args.runner_unit is not None
            else f"PID {args.runner_pid}"
        )
        _write_event(
            args.event_log,
            "Progress watchdog: no canonical result or attempt-state update "
            f"for {args.stall_seconds:g} seconds; interrupting runner "
            f"{target} for safe --resume.",
        )
        if args.runner_unit is not None:
            _interrupt_runner_unit(args.runner_unit)
            # > The systemd unit restarts on a non-zero runner exit. Keep
            # > watching the replacement PID rather than abandoning its
            # > progress guard after the first restart.
            time.sleep(args.term_grace_seconds)
            continue
        _stop_runner(args.runner_pid, args.term_grace_seconds)
        return 75
    return 0


def _runner_is_live(*, runner_pid: int | None, runner_unit: str | None) -> bool:
    """Return whether the configured runner target is still running.

    :param runner_pid: Fixed process identifier for a non-restarting runner.
    :param runner_unit: User-systemd unit for an automatically restarted run.
    :return: Whether the runner can still make durable progress.
    """
    if runner_unit is not None:
        result = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                runner_unit,
                "--property=ActiveState",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() in {
            "active",
            "activating",
            "reloading",
        }
    assert runner_pid is not None
    return _process_exists(runner_pid)


def _newest_mtime(roots: tuple[Path, ...]) -> float | None:
    """Return the most recent durable checkpoint timestamp.

    :param roots: Result and attempt-state directories to inspect.
    :return: Newest timestamp, or ``None`` before the first checkpoint exists.
    """
    mtimes = [
        path.stat().st_mtime
        for root in roots
        if root.exists()
        for path in root.rglob("*.json")
        if path.is_file()
    ]
    return max(mtimes) if mtimes else None


def _is_progress_stalled(
    *,
    newest_checkpoint_at: float | None,
    watchdog_started_at: float,
    current_time: float,
    stall_seconds: float,
) -> bool:
    """Return whether the current runner exceeded its checkpoint allowance.

    A resumed run can have old canonical files before it starts its next
    request. The watchdog therefore measures its first allowance from its own
    start time rather than treating the historical checkpoint as a new stall.

    :param newest_checkpoint_at: Latest canonical result or attempt timestamp.
    :param watchdog_started_at: Timestamp when this watchdog began observing.
    :param current_time: Timestamp for the current progress check.
    :param stall_seconds: Maximum quiet interval before interruption.
    :return: Whether no relevant checkpoint has appeared in the allowance.
    """
    baseline = watchdog_started_at
    if newest_checkpoint_at is not None:
        baseline = max(baseline, newest_checkpoint_at)
    return current_time - baseline > stall_seconds


def _process_exists(pid: int) -> bool:
    """Check whether the target PID remains available.

    :param pid: Process identifier to probe.
    :return: Whether the process has not exited.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _stop_runner(pid: int, grace_seconds: float) -> None:
    """Request an orderly stop, then force termination after the grace period.

    :param pid: Runner process that failed to checkpoint.
    :param grace_seconds: Time allowed for the orderly signal to take effect.
    """
    os.kill(pid, signal.SIGINT)
    deadline = time.monotonic() + grace_seconds
    while _process_exists(pid) and time.monotonic() < deadline:
        time.sleep(1)
    if _process_exists(pid):
        os.kill(pid, signal.SIGTERM)


def _interrupt_runner_unit(unit: str) -> None:
    """Request the current systemd main process to stop cleanly.

    :param unit: User-systemd runner unit configured with restart-on-failure.
    """
    subprocess.run(
        [
            "systemctl",
            "--user",
            "kill",
            "--signal=SIGINT",
            "--kill-whom=main",
            unit,
        ],
        check=False,
    )


def _write_event(path: Path, message: str) -> None:
    """Append one readable watchdog event to the run handoff log.

    :param path: Existing or new babysit log.
    :param message: Concise recorded incident description.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n### {timestamp}\n\n- {message}\n")


if __name__ == "__main__":
    raise SystemExit(main())
