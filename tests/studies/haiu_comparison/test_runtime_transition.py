"""Tests for explicit mid-run runtime identity transitions."""

from __future__ import annotations

import json
from pathlib import Path

import dmw_experiments.studies.haiu_comparison.operations.runtime_transition as transition_module
from dmw_experiments.studies.haiu_comparison.operations.runtime_transition import (
    record_runtime_transition,
    runtime_transition_matches,
)


def test_runtime_transition_records_and_verifies_exact_identities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_root = tmp_path / "run"
    environment = run_root / "environment"
    output = run_root / "raw-academiccloud"
    environment.mkdir(parents=True)
    output.mkdir()
    original_harness = {
        "commit": "a" * 40,
        "branch": "main",
        "worktree_clean": True,
    }
    migration_harness = {
        "commit": "b" * 40,
        "branch": "main",
        "worktree_clean": True,
    }
    target_harness = {
        "commit": "c" * 40,
        "branch": "main",
        "worktree_clean": True,
    }
    source_haiu = {
        "version": "1.8.0",
        "record_sha256": "ignored",
        "source": {
            "url": "https://github.com/HisQu/haiu.git",
            "editable": False,
            "vcs": "git",
            "requested_revision": "v1.8.0",
            "commit_id": "d" * 40,
        },
    }
    target_haiu = {
        "version": "1.8.1",
        "url": "https://github.com/HisQu/haiu.git",
        "requested_revision": "v1.8.1",
        "commit_id": "e" * 40,
        "editable": False,
    }
    (environment / "academiccloud-environment-lock.json").write_text(
        json.dumps(
            {
                "experiment_harness": original_harness,
                "runtime": {"packages": {"haiu": source_haiu}},
            }
        ),
        encoding="utf-8",
    )
    (environment / "academiccloud-artifact-layout-migration.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "target_harness": migration_harness,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        transition_module,
        "clean_harness_identity",
        lambda: target_harness,
    )
    monkeypatch.setattr(
        transition_module,
        "installed_haiu_identity",
        lambda: target_haiu,
    )

    report = record_runtime_transition(
        run_root=run_root,
        execution="academiccloud",
        reason="Preserve provider payloads after terminal failures.",
    )

    assert report.source_haiu_version == "1.8.0"
    assert report.target_haiu_version == "1.8.1"
    live_distribution = {
        "version": "1.8.1",
        "direct_url": target_haiu["url"],
        "requested_revision": "v1.8.1",
        "commit_id": "e" * 40,
        "editable": False,
    }
    runner_harness = {
        "commit": target_harness["commit"],
        "worktree_clean": True,
    }
    assert runtime_transition_matches(
        output_dir=output,
        frozen_haiu_package=source_haiu,
        live_haiu_distribution=live_distribution,
        live_harness=runner_harness,
    )
    assert not runtime_transition_matches(
        output_dir=output,
        frozen_haiu_package=source_haiu,
        live_haiu_distribution={**live_distribution, "commit_id": "f" * 40},
        live_harness=runner_harness,
    )
