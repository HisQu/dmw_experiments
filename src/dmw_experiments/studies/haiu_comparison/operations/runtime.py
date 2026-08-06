"""Published-stack runtime selection for the Haiu comparison."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from dmw_experiments.shared.config import AppRuntimeConfig, UNSET_PATH
from dmw_experiments.studies.haiu_comparison.operations.repository_paths import (
    REPOSITORY_ROOT,
)


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolve only the interpreter outside a portable run contract.

    :param publication_python: Interpreter containing the released DMW stack.
    """

    publication_python: Path

    @classmethod
    def from_config(cls, config: AppRuntimeConfig) -> RuntimePaths:
        """Use the active interpreter unless an explicit override exists.

        :param config: Experiment-owned AppRC settings.
        :return: Runtime interpreter without resolving a virtualenv symlink.
        """
        configured = config.publication_python.expanduser()
        if configured == UNSET_PATH:
            configured = Path(sys.executable)
        elif not configured.is_absolute():
            configured = REPOSITORY_ROOT / configured
        return cls(publication_python=configured.absolute())

    def validate(self) -> None:
        """Reject a missing publication interpreter before mutation.

        :return: ``None`` when the interpreter is a file.
        :raises ValueError: If the configured interpreter does not exist.
        """
        if not self.publication_python.is_file():
            raise ValueError("Published-stack interpreter does not exist.")
