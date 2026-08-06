from pathlib import Path

from dmw_experiments.studies.datamodel_workflow_haiu_comparison import (
    haiu_ontologizer,
)


def test_haiu_ontologizer_does_not_import_experiment_package() -> None:
    root = Path(haiu_ontologizer.__file__).resolve().parent
    mirror_files = root.glob("*.py")

    offenders = [
        path.name
        for path in mirror_files
        if "comparison_experiment" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
