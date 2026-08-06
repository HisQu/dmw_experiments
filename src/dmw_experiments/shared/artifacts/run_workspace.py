"""Own machine-readable and human-readable state inside one copied run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    """Expose predictable operational paths for one provider execution.

    :param root: Complete copied run directory.
    :param execution: Provider execution owning service and BABYSIT records.
    """

    root: Path
    execution: str

    @property
    def logs(self) -> Path:
        """Return the shared run-local log directory.

        :return: Directory containing provider logs and journals.
        """
        return self.root / "logs"

    @property
    def environment(self) -> Path:
        """Return the portable runtime-evidence directory.

        :return: Directory containing locks, events, and service identities.
        """
        return self.root / "environment"

    @property
    def run_spec(self) -> Path:
        """Return the authoritative run contract.

        :return: Run-local TOML path.
        """
        return self.root / "run.toml"

    @property
    def run_spec_digest(self) -> Path:
        """Return the immutable contract digest used by resume.

        :return: SHA-256 sidecar path.
        """
        return self.environment / "run.toml.sha256"

    @property
    def services_file(self) -> Path:
        """Return this execution's service registry.

        :return: JSON registry path.
        """
        return self.environment / f"{self.execution}-services.json"

    @property
    def events_file(self) -> Path:
        """Return the shared structured lifecycle event stream.

        :return: JSON Lines path.
        """
        return self.environment / "events.jsonl"

    @property
    def babysit_log(self) -> Path:
        """Return the stable readable journal for this execution.

        The first launch date remains part of the filename across resumptions.

        :return: Existing journal or today's deterministic destination.
        """
        pattern = (
            f"BABYSIT-{self.root.name.upper()}-{self.execution.upper()}-*.md"
        )
        existing = sorted(self.logs.glob(pattern))
        if len(existing) > 1:
            raise ValueError(
                f"Multiple BABYSIT journals exist for {self.execution}."
            )
        if existing:
            return existing[0]
        date = datetime.now().astimezone().strftime("%Y-%m-%d")
        return self.logs / (
            f"BABYSIT-{self.root.name.upper()}-"
            f"{self.execution.upper()}-{date}.md"
        )

    @classmethod
    def open(cls, root: Path, execution: str) -> RunWorkspace:
        """Open a complete copied run and ensure operational directories.

        :param root: Existing run directory.
        :param execution: Provider execution selected by the lifecycle.
        :return: Ready workspace facade.
        :raises ValueError: If the run contract is absent.
        """
        resolved = root.expanduser().resolve()
        workspace = cls(root=resolved, execution=execution)
        if not workspace.run_spec.is_file():
            raise ValueError("Run directory has no run.toml.")
        workspace.logs.mkdir(parents=True, exist_ok=True)
        workspace.environment.mkdir(parents=True, exist_ok=True)
        return workspace

    def freeze_contract(self) -> None:
        """Create or verify the run-contract digest before external mutation.

        :return: ``None`` when the current TOML matches frozen evidence.
        :raises ValueError: If the run changed after its first launch.
        """
        digest = hashlib.sha256(self.run_spec.read_bytes()).hexdigest()
        if self.run_spec_digest.is_file():
            recorded = self.run_spec_digest.read_text(encoding="utf-8").strip()
            if recorded != digest:
                raise ValueError(
                    "run.toml differs from the contract frozen at first launch."
                )
            return
        _write_text_atomic(self.run_spec_digest, digest + "\n")
        self.append_event(
            event="run_contract_frozen",
            detail="Frozen run.toml before storage preparation or service launch.",
        )

    def require_frozen_contract(self) -> None:
        """Verify that resume uses the exact first-launch contract.

        :return: ``None`` when the digest matches.
        :raises ValueError: If no digest exists or the contract changed.
        """
        if not self.run_spec_digest.is_file():
            raise ValueError(
                "Cannot resume without environment/run.toml.sha256."
            )
        self.freeze_contract()

    def append_event(self, *, event: str, detail: str, **fields: Any) -> None:
        """Append one non-secret machine-readable lifecycle event.

        :param event: Stable event category.
        :param detail: Concise factual explanation.
        :param fields: Additional JSON-compatible non-secret values.
        :return: ``None``.
        """
        payload = {
            "schema_version": 1,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "execution": self.execution,
            "event": event,
            "detail": detail,
            **fields,
        }
        self.environment.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str))
            stream.write("\n")

    def append_babysit(
        self,
        *,
        heading: str,
        bullets: tuple[str, ...],
    ) -> None:
        """Append one timestamped provider checkpoint.

        :param heading: Short factual checkpoint title.
        :param bullets: Details that contain no secrets or absolute paths.
        :return: ``None``.
        """
        path = self.babysit_log
        prefix = ""
        if not path.exists():
            prefix = f"# Babysitting log: {self.root.name} / {self.execution}\n"
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        lines = [prefix, f"\n## {timestamp} — {heading}\n"]
        lines.extend(f"\n- {bullet}" for bullet in bullets)
        lines.append("\n")
        with path.open("a", encoding="utf-8") as stream:
            stream.write("".join(lines))

    def write_services(self, services: Any) -> None:
        """Replace this execution's service registry atomically.

        :param services: Dataclass or JSON-compatible mapping.
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
        """Load this execution's current service registry.

        :return: Registry mapping or an empty mapping before launch.
        """
        if not self.services_file.is_file():
            return {}
        payload = json.loads(self.services_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Run service registry is not a JSON object.")
        return payload


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace a UTF-8 file without exposing partial content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
