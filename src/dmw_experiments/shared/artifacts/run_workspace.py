"""Own the durable operational files around one experiment run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    """Expose the predictable directory layout for one run.

    Scientific observations and operational logs share one run root so a
    tired operator never has to reconstruct which log belongs to which data.
    The immutable run specification is copied before any external storage is
    prepared.

    :param root: Top-level directory for one run identity.
    """

    root: Path

    @property
    def logs(self) -> Path:
        """Return the directory containing service and babysitting logs.

        :return: Run-local operational-log directory.
        """
        return self.root / "logs"

    @property
    def provenance(self) -> Path:
        """Return the directory containing frozen execution evidence.

        :return: Run-local provenance directory.
        """
        return self.root / "provenance"

    @property
    def operations(self) -> Path:
        """Return the directory containing mutable lifecycle state.

        :return: Run-local service and event-state directory.
        """
        return self.root / "operations"

    @property
    def run_spec(self) -> Path:
        """Return the immutable copy of the launch specification.

        :return: Run-local specification path.
        """
        return self.root / "run_spec.json"

    @property
    def run_spec_digest(self) -> Path:
        """Return the recorded specification content identity.

        :return: Run-local SHA-256 sidecar path.
        """
        return self.operations / "run_spec.sha256"

    @property
    def services_file(self) -> Path:
        """Return the latest service-unit registry.

        :return: Run-local JSON service registry path.
        """
        return self.operations / "services.json"

    @property
    def events_file(self) -> Path:
        """Return the structured append-only operational event log.

        :return: Run-local JSON Lines event path.
        """
        return self.operations / "events.jsonl"

    @property
    def babysit_log(self) -> Path:
        """Return the readable babysitting journal for this run.

        :return: Markdown log whose name identifies the run.
        """
        return self.logs / f"BABYSIT-{self.root.name.upper()}.md"

    @classmethod
    def create(cls, root: Path, source_spec: Path) -> RunWorkspace:
        """Create a fresh workspace and freeze its requested specification.

        :param root: New run directory below the configured output root.
        :param source_spec: Validated tracked JSON run specification.
        :return: Created workspace.
        :raises FileExistsError: If the run directory already exists.
        """
        root.mkdir(parents=True, exist_ok=False)
        workspace = cls(root=root)
        workspace.logs.mkdir()
        workspace.provenance.mkdir()
        workspace.operations.mkdir()
        content = source_spec.read_bytes()
        _write_bytes_atomic(workspace.run_spec, content)
        _write_text_atomic(
            workspace.run_spec_digest,
            hashlib.sha256(content).hexdigest() + "\n",
        )
        workspace.append_event(
            event="workspace_created",
            detail="Frozen run specification before external preparation.",
        )
        workspace.append_babysit(
            heading="Run workspace created",
            bullets=(
                "The validated run specification was frozen before storage "
                "preparation or service launch.",
                "Service logs, lifecycle events, and this journal are owned "
                "by the same run directory.",
            ),
        )
        return workspace

    @classmethod
    def open(cls, root: Path, source_spec: Path) -> RunWorkspace:
        """Open an existing workspace only for an identical specification.

        :param root: Existing run directory.
        :param source_spec: Requested tracked JSON run specification.
        :return: Verified workspace.
        :raises ValueError: If the frozen specification is missing or differs.
        """
        workspace = cls(root=root)
        if not workspace.run_spec.is_file():
            raise ValueError("Existing run has no frozen run_spec.json.")
        requested = source_spec.read_bytes()
        frozen = workspace.run_spec.read_bytes()
        if requested != frozen:
            raise ValueError(
                "Requested specification differs from the existing run."
            )
        digest = hashlib.sha256(frozen).hexdigest()
        if (
            not workspace.run_spec_digest.is_file()
            or workspace.run_spec_digest.read_text(encoding="utf-8").strip()
            != digest
        ):
            raise ValueError("Existing run specification digest is invalid.")
        return workspace

    def append_event(self, *, event: str, detail: str, **fields: Any) -> None:
        """Append one non-secret machine-readable lifecycle event.

        :param event: Stable event category.
        :param detail: Concise human-readable explanation.
        :param fields: Additional non-secret JSON-compatible event fields.
        :return: ``None``.
        """
        payload = {
            "schema_version": 1,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "event": event,
            "detail": detail,
            **fields,
        }
        self.operations.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str))
            stream.write("\n")

    def append_babysit(
        self,
        *,
        heading: str,
        bullets: tuple[str, ...],
    ) -> None:
        """Append one timestamped checkpoint to the readable run journal.

        :param heading: Short checkpoint title.
        :param bullets: Factual checkpoint details without secrets.
        :return: ``None``.
        """
        self.logs.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        prefix = ""
        if not self.babysit_log.exists():
            prefix = f"# Babysitting log: {self.root.name}\n"
        lines = [prefix, f"\n## {timestamp} — {heading}\n"]
        lines.extend(f"\n- {bullet}" for bullet in bullets)
        lines.append("\n")
        with self.babysit_log.open("a", encoding="utf-8") as stream:
            stream.write("".join(lines))

    def write_services(self, services: Any) -> None:
        """Replace the current non-secret service-unit registry atomically.

        :param services: Dataclass or JSON-compatible service mapping.
        :return: ``None``.
        """
        payload = (
            asdict(services)
            if hasattr(services, "__dataclass_fields__")
            else services
        )
        _write_text_atomic(
            self.services_file,
            json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            + "\n",
        )

    def load_services(self) -> dict[str, Any]:
        """Load the latest service-unit registry.

        :return: Registry payload, or an empty mapping before launch.
        :raises ValueError: If the stored document is not an object.
        """
        if not self.services_file.is_file():
            return {}
        payload = json.loads(self.services_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Run service registry is not a JSON object.")
        return payload


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace a UTF-8 text file without exposing partial content.

    :param path: Destination path.
    :param content: Complete file content.
    :return: ``None``.
    """
    _write_bytes_atomic(path, content.encode("utf-8"))


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    """Replace a file through a sibling temporary artifact.

    :param path: Destination path.
    :param content: Complete file bytes.
    :return: ``None``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
