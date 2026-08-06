from pathlib import Path

from dmw_experiments.studies.datamodel_workflow_haiu_comparison.comparison_experiment.ids import (
    limited_ids,
    normalize_regest_id,
    parse_regest_id_entries,
    parse_regest_ids,
)


def test_parse_regest_ids_skips_header_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "ids.txt"
    path.write_text(
        "\n".join(
            [
                "id_RG_all",
                "11010116-1",
                "11010116-1",
                "11010624-3",
                "",
                "# note",
                "11000127",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_regest_ids(path) == ["11010116", "11010624", "11000127"]


def test_parse_regest_id_entries_preserves_source_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ids.txt"
    path.write_text(
        "id_RG_all\n# note\n11010116-1\n\n11000127\n", encoding="utf-8"
    )

    entries = parse_regest_id_entries(path)

    assert [entry.as_dict() for entry in entries] == [
        {"line_no": 3, "raw_id": "11010116-1", "regest_id": "11010116"},
        {"line_no": 5, "raw_id": "11000127", "regest_id": "11000127"},
    ]


def test_parse_regest_ids_can_keep_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "ids.txt"
    path.write_text("id_RG_all\n11010116-1\n11010116-1\n", encoding="utf-8")

    assert parse_regest_ids(path, keep_duplicates=True) == [
        "11010116",
        "11010116",
    ]


def test_normalize_regest_id_rejects_unknown_format() -> None:
    try:
        normalize_regest_id("x-2", line_no=12)
    except ValueError as exc:
        assert "line 12" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-numeric regest id")


def test_limited_ids_zero_means_all() -> None:
    assert limited_ids(["a", "b"], 0) == ["a", "b"]
    assert limited_ids(["a", "b"], 1) == ["a"]
