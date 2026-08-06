from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dmw_experiments.studies.haiu_comparison.materialize_header_sublemma_catalog import (
    materialize_catalogue,
    write_catalogue,
)


def test_materialize_catalogue_preserves_ordered_header_sublemma_pairs(
    tmp_path: Path,
) -> None:
    source_run_dir = _write_source_run(
        tmp_path,
        {
            "100": {"header": "First header", "subentries": ["A", "B"]},
            "200": {"header": "Header only", "subentries": []},
        },
    )

    catalogue = materialize_catalogue(source_run_dir)

    assert catalogue["unit_kind"] == "header_sublemma_pair"
    assert catalogue["selection"] == {
        "source_regest_count": 2,
        "input_unit_count": 2,
        "excluded_header_only_regest_count": 1,
        "excluded_header_only_regest_ids": ["200"],
    }
    records = catalogue["records"]
    assert [record["input_unit_id"] for record in records] == [
        "hsp-100-s01",
        "hsp-100-s02",
    ]
    assert records[0]["header"] == "First header"
    assert records[0]["sublemma"] == "A"
    assert records[1]["source_subentry_index"] == 1
    assert records[1]["source_sublemma_number"] == 2


def test_materialize_catalogue_rejects_changed_source_record(
    tmp_path: Path,
) -> None:
    source_run_dir = _write_source_run(
        tmp_path,
        {"100": {"header": "First header", "subentries": ["A"]}},
    )
    record_path = source_run_dir / "provenance/raw_regests/100.json"
    record_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its manifest"):
        materialize_catalogue(source_run_dir)


def test_write_catalogue_requires_explicit_replacement(tmp_path: Path) -> None:
    output_path = tmp_path / "catalogue.json"
    catalogue = {"schema_version": 1}
    write_catalogue(
        catalogue=catalogue,
        output_path=output_path,
        overwrite=False,
    )

    with pytest.raises(FileExistsError, match="Pass --overwrite"):
        write_catalogue(
            catalogue=catalogue,
            output_path=output_path,
            overwrite=False,
        )


def _write_source_run(
    tmp_path: Path, records: dict[str, dict[str, object]]
) -> Path:
    source_run_dir = tmp_path / "source-run"
    raw_dir = source_run_dir / "provenance/raw_regests"
    raw_dir.mkdir(parents=True)
    manifest_records: dict[str, dict[str, str]] = {}
    for regest_id, source in records.items():
        header = source["header"]
        subentries = source["subentries"]
        assert isinstance(header, str)
        assert isinstance(subentries, list)
        content = {
            "regest_id": regest_id,
            "header": header,
            "subentries": subentries,
        }
        payload = {
            "schema_version": 1,
            "source": "preflight_frozen_raw_regest_snapshot",
            **content,
            "content_sha256": _sha256_json(content),
        }
        path = raw_dir / f"{regest_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_records[regest_id] = {
            "path": f"provenance/raw_regests/{regest_id}.json",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest_path = source_run_dir / "provenance/raw_regests_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "preflight_frozen_raw_regest_snapshot",
                "records": manifest_records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return source_run_dir


def _sha256_json(payload: dict[str, object]) -> str:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
