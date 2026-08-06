"""Architecture constraints for the Haiu comparison study package."""

from __future__ import annotations

import ast
from pathlib import Path

from dmw_experiments.studies import haiu_comparison


PACKAGE_ROOT = Path(haiu_comparison.__file__).resolve().parent


def _imports_below(directory: Path) -> set[str]:
    imports: set[str] = set()
    for path in directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_model_does_not_import_lifecycle_implementations() -> None:
    """Domain contracts stay independent from infrastructure and analysis."""
    imports = _imports_below(PACKAGE_ROOT / "model")

    forbidden = (
        ".analysis",
        ".data_collection",
        ".entrypoints",
        ".operations",
        ".preparation",
    )
    offenders = sorted(
        name for name in imports if any(marker in name for marker in forbidden)
    )

    assert offenders == []


def test_collection_does_not_import_analysis() -> None:
    """Raw data collection cannot depend on derived reporting code."""
    imports = _imports_below(PACKAGE_ROOT / "data_collection")

    assert not any(".analysis" in name for name in imports)


def test_analysis_does_not_import_collection_or_operations() -> None:
    """Derived reporting depends on preserved evidence and domain models."""
    imports = _imports_below(PACKAGE_ROOT / "analysis")

    forbidden = (".data_collection", ".entrypoints", ".operations")
    offenders = sorted(
        name for name in imports if any(marker in name for marker in forbidden)
    )

    assert offenders == []
