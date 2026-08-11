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
    versions = {
        "datamodel-workflow": ("1.1.3", "1.1.4"),
        "opa": ("2.1.2", "2.1.3"),
        "gta": ("0.2.4", "0.2.5"),
        "haiu": ("1.8.0", "1.8.1"),
    }
    source_packages = {
        name: {
            "version": source_version,
            "source": {
                "url": f"https://example.test/{name}.git",
                "editable": False,
                "vcs": "git",
                "requested_revision": f"v{source_version}",
                "commit_id": chr(100 + index) * 40,
            },
        }
        for index, (name, (source_version, _)) in enumerate(versions.items())
    }
    target_packages = {
        name: {
            "version": target_version,
            "url": f"https://example.test/{name}.git",
            "requested_revision": f"v{target_version}",
            "commit_id": chr(110 + index) * 40,
            "editable": False,
        }
        for index, (name, (_, target_version)) in enumerate(versions.items())
    }
    (environment / "academiccloud-environment-lock.json").write_text(
        json.dumps(
            {
                "experiment_harness": original_harness,
                "runtime": {"packages": source_packages},
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
    source_haiu = source_packages["haiu"]
    source_haiu_source = source_haiu["source"]
    (environment / "academiccloud-runtime-transition.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_type": "haiu_comparison_runtime_transition",
                "status": "completed",
                "completed_at": "2026-08-10T15:00:00+00:00",
                "execution": "academiccloud",
                "reason": "Earlier Haiu-only observability patch.",
                "scientific_contract_changed": False,
                "source_harness": migration_harness,
                "target_harness": {
                    "commit": "f" * 40,
                    "branch": "main",
                    "worktree_clean": True,
                },
                "source_haiu": {
                    "version": source_haiu["version"],
                    "url": source_haiu_source["url"],
                    "requested_revision": source_haiu_source[
                        "requested_revision"
                    ],
                    "commit_id": source_haiu_source["commit_id"],
                    "editable": False,
                },
                "target_haiu": target_packages["haiu"],
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
        "installed_runtime_package_identities",
        lambda: target_packages,
    )

    report = record_runtime_transition(
        run_root=run_root,
        execution="academiccloud",
        reason="Preserve provider payloads after terminal failures.",
    )

    assert report.source_haiu_version == "1.8.0"
    assert report.target_haiu_version == "1.8.1"
    transition = json.loads(
        (environment / "academiccloud-runtime-transition.json").read_text(
            encoding="utf-8"
        )
    )
    assert transition["schema_version"] == 2
    assert transition["history"][0]["reason"] == (
        "Earlier Haiu-only observability patch."
    )
    live_distributions = {
        name: {
            "version": identity["version"],
            "direct_url": identity["url"],
            "requested_revision": identity["requested_revision"],
            "commit_id": identity["commit_id"],
            "editable": False,
        }
        for name, identity in target_packages.items()
    }
    runner_harness = {
        "commit": target_harness["commit"],
        "worktree_clean": True,
    }
    assert runtime_transition_matches(
        output_dir=output,
        frozen_haiu_package=source_packages["haiu"],
        live_haiu_distribution=live_distributions["haiu"],
        live_harness=runner_harness,
        frozen_packages=source_packages,
        live_distributions=live_distributions,
    )
    assert not runtime_transition_matches(
        output_dir=output,
        frozen_haiu_package=source_packages["haiu"],
        live_haiu_distribution=live_distributions["haiu"],
        live_harness=runner_harness,
        frozen_packages=source_packages,
        live_distributions={
            **live_distributions,
            "opa": {
                **live_distributions["opa"],
                "commit_id": "f" * 40,
            },
        },
    )
