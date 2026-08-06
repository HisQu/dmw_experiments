"""Tests for the supported Haiu comparison Python façade."""

from __future__ import annotations

from pathlib import Path

from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.studies.haiu_comparison import HaiuComparisonStudy
from dmw_experiments.studies.haiu_comparison import study as study_module


def test_new_run_translates_public_arguments_to_one_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Callers do not need to import the internal run-factory request."""
    destination = tmp_path / "new-run"
    captured = []
    monkeypatch.setattr(
        study_module,
        "create_run",
        lambda request: captured.append(request) or destination,
    )

    result = HaiuComparisonStudy(AppRuntimeConfig()).new_run(
        run_id="new-run",
        mode="smoke",
        executions=("academiccloud",),
    )

    assert result == destination
    assert captured[0].run_id == "new-run"
    assert captured[0].mode == "smoke"
    assert captured[0].executions == ("academiccloud",)


def test_status_delegates_through_the_lifecycle(
    monkeypatch, tmp_path: Path
) -> None:
    """Provider filtering has one spelling at the public boundary."""
    study = HaiuComparisonStudy(AppRuntimeConfig())
    expected = object()
    monkeypatch.setattr(
        study._lifecycle, "status", lambda *args, **kwargs: expected
    )

    result = study.status(
        tmp_path,
        executions=("lmstudio",),
    )

    assert result is expected
