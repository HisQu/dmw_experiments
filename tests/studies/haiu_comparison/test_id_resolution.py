from pathlib import Path
from typing import Any

import pytest

from dmw_experiments.studies.haiu_comparison.comparison_experiment.datamodel_api import (
    RegestNotFoundError,
)
from dmw_experiments.studies.haiu_comparison.comparison_experiment.id_resolution import (
    MissingRegestIdsError,
    resolve_available_regest_ids,
)
from dmw_experiments.studies.haiu_comparison.model.identifiers import (
    ParsedRegestId,
)


class FakeRegestClient:
    def __init__(
        self,
        *,
        missing_ids: tuple[str, ...] = (),
        error_ids: tuple[str, ...] = (),
    ) -> None:
        self.missing_ids = set(missing_ids)
        self.error_ids = set(error_ids)
        self.calls: list[str] = []

    def get_regest_payload(self, regest_id: str) -> dict[str, Any]:
        self.calls.append(regest_id)
        if regest_id in self.error_ids:
            raise RuntimeError(f"boom: {regest_id}")
        if regest_id in self.missing_ids:
            raise RegestNotFoundError(regest_id, 404, "missing")
        return {"success": True}


def test_skip_policy_selects_next_available_ids_until_limit() -> None:
    candidates = [
        _candidate("11010116", raw_id="11010116-1"),
        _candidate("11000127"),
        _candidate("11010624", raw_id="11010624-1"),
        _candidate("11000166"),
        _candidate("11002025"),
    ]
    client = FakeRegestClient(missing_ids=("11010116", "11010624"))

    selection = resolve_available_regest_ids(
        client=client,
        candidates=candidates,
        limit=2,
        missing_id_policy="skip",
    )

    assert selection.selected_ids == ["11000127", "11000166"]
    assert [item.candidate.regest_id for item in selection.skipped] == [
        "11010116",
        "11010624",
    ]
    assert client.calls == [candidate.regest_id for candidate in candidates]
    assert selection.as_dict(source_file=Path("ids.txt"))["selected_count"] == 2
    assert (
        selection.as_dict(source_file=Path.cwd() / "ids.txt")["source_file"]
        == "ids.txt"
    )


def test_limit_zero_selects_all_available_ids() -> None:
    candidates = [
        _candidate("11010116", raw_id="11010116-1"),
        _candidate("11000127"),
        _candidate("11000166"),
    ]
    client = FakeRegestClient(missing_ids=("11010116",))

    selection = resolve_available_regest_ids(
        client=client,
        candidates=candidates,
        limit=0,
        missing_id_policy="skip",
    )

    assert selection.selected_ids == ["11000127", "11000166"]
    assert len(selection.available) == 2


def test_fail_policy_reports_missing_ids_before_experiment_work() -> None:
    candidates = [
        _candidate("11010116", raw_id="11010116-1"),
        _candidate("11000127"),
    ]
    client = FakeRegestClient(missing_ids=("11010116",))

    with pytest.raises(MissingRegestIdsError) as exc_info:
        resolve_available_regest_ids(
            client=client,
            candidates=candidates,
            limit=1,
            missing_id_policy="fail",
        )

    assert "11010116-1->11010116" in str(exc_info.value)
    assert exc_info.value.selection.selected_ids == ["11000127"]


def test_non_not_found_datamodel_errors_abort_preflight() -> None:
    candidates = [_candidate("11000127"), _candidate("11000166")]
    client = FakeRegestClient(error_ids=("11000166",))

    with pytest.raises(RuntimeError, match="boom: 11000166"):
        resolve_available_regest_ids(
            client=client,
            candidates=candidates,
            limit=1,
            missing_id_policy="skip",
        )


def _candidate(
    regest_id: str, *, raw_id: str | None = None, line_no: int = 1
) -> ParsedRegestId:
    return ParsedRegestId(
        line_no=line_no,
        raw_id=raw_id or regest_id,
        regest_id=regest_id,
    )
