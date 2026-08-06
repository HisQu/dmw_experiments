from pathlib import Path

import dmw_experiments.shared


def test_shared_modules_do_not_import_studies() -> None:
    root = Path(dmw_experiments.shared.__file__).resolve().parent
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "dmw_experiments.studies" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_shared_modules_do_not_define_haiu_comparison_conditions() -> None:
    root = Path(dmw_experiments.shared.__file__).resolve().parent
    condition_names = (
        "workflow_full_ontology",
        "workflow_rag",
        "haiu_rag_ontologizer",
    )
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if any(
            condition in path.read_text(encoding="utf-8")
            for condition in condition_names
        )
    ]

    assert offenders == []
