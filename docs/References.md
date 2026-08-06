# Reference

## Table of contents

1. [Project paths](#project-paths)
2. [Commands](#commands)
3. [Environment variables](#environment-variables)
4. [Dependency surfaces](#dependency-surfaces)
5. [Public interfaces](#public-interfaces)
6. [Study files](#study-files)
7. [Generated run files](#generated-run-files)
8. [Service units](#service-units)
9. [Figure visual tokens](#figure-visual-tokens)

## Project paths

| Path | Owner |
| --- | --- |
| `src/dmw_experiments/shared/` | Reusable execution, supervision, artifact, configuration, and analysis code. |
| `src/dmw_experiments/studies/` | Study-specific scientific code. |
| `studies/` | Tracked scientific inputs, run specs, and release contracts. |
| `output/runs/` | Generated raw runs, logs, and provenance. |
| `output/analyses/` | Generated cross-run workbooks and figures. |
| `tests/` | Offline regression and lifecycle verification. |
| `docs/` | User and maintainer documentation. |
| `docs/studies/` | Scientific study summaries synchronized with tracked study READMEs. |

## Commands

| Command | Effect |
| --- | --- |
| `dmw_experiments validate --spec PATH` | Validate without storage or service mutation. |
| `dmw_experiments smoke` | Prepare and start the canonical one-unit smoke. |
| `dmw_experiments run` | Prepare and start the canonical 480-unit full run. |
| `dmw_experiments status --spec PATH` | Count terminal, successful, failed, and retry-pending cells. |
| `dmw_experiments pause --spec PATH` | Stop watchdog, runner, and backend safely. |
| `dmw_experiments resume --spec PATH` | Resume only the identical frozen run. |
| `dmw_experiments analyze ...` | Rebuild workbooks, review packets, and plots. |
| `dmw_experiments config doctor` | Diagnose AppRC runtime configuration. |

`analyze` overwrites known exporter-owned per-run files by default. It never
overwrites a supplied historian-grade workbook or an existing timestamped plot
directory. Use `--no-overwrite` for a fail-if-present export and `--audit-csv`
for raw-derived CSV tables.

## Environment variables

| Variable | Meaning |
| --- | --- |
| `DMW_EXPERIMENTS_STORAGE` | Root containing `runs/`, `analyses/`, and ignored runtime support. |
| `DMW_EXPERIMENTS_PUBLICATION_PYTHON` | Optional Python interpreter containing the locked stack; defaults to `.venv/bin/python`. |
| `DMW_EXPERIMENTS_ACADEMICCLOUD_ENV_FILE` | Ignored dotenv file containing DMW, MongoDB, Haiu, provider, and API-login values. |
| `DMW_EXPERIMENTS_LMSTUDIO_ENV_FILE` | Reserved ignored dotenv file for local-provider workflows. |
| `DMW_EXPERIMENTS_WATCHDOG_STALL_SECONDS` | Maximum quiet checkpoint interval; defaults to `14400`. |
| `DATAMODEL_LOGIN` | DMW API login read from the ignored runtime file. |
| `DATAMODEL_PASSWORD` | DMW API password read from the ignored runtime file. |
| `FAISS_INDEX_PATH` | Absolute existing NER few-shot example-index file. |

## Dependency surfaces

| Surface | Purpose |
| --- | --- |
| `[project].dependencies` | Core DMW execution and analysis packages. |
| `[tool.uv].override-dependencies` | Published-metadata corrections for MongoDBAPI 1.0.2 and GTA 0.2.4. |
| `[dependency-groups].dev` | Tests, linting, type checking, and profiling. |
| `uv.lock` | Exact uv environment, including resolved Git commits. |
| `pylock.toml` | PEP 751 export of the complete maintainer environment. |
| `requirements-runtime.lock` | Plain-pip export of the core release environment. |

## Public interfaces

The supported user interface is the `dmw_experiments` command tree documented
under [Commands](#commands). Python modules below
`dmw_experiments.studies` are experiment implementation details unless a study
document names them explicitly.

Reusable Python modules live below `dmw_experiments.shared`. The root
`dmw_experiments.cli` package is the application boundary, not a utility
owner.

## Study files

| Path | Meaning |
| --- | --- |
| `studies/haiu_comparison/inputs/header_sublemma_input_catalog.json` | Frozen 480-unit population. |
| `studies/haiu_comparison/inputs/reference_ontology.ttl` | Frozen reference ontology used by the measured conditions. |
| `studies/haiu_comparison/inputs/retrieval_workspace.json` | Portable retrieval-workspace identity. |
| `studies/haiu_comparison/inputs/annotation_guidelines.md` | Immutable annotation instructions. |
| `studies/haiu_comparison/specs/academiccloud-header-sublemma-smoke.json` | Canonical `limit=1` smoke contract. |
| `studies/haiu_comparison/specs/academiccloud-header-sublemma-full.json` | Canonical `limit=0` full contract. |
| `studies/haiu_comparison/locks/published-dmw-stack-1.1.3.json` | Published stack contract. |
| `studies/haiu_comparison/README.md` | Operational study overview beside the tracked contract. |
| `docs/studies/haiu_comparison.md` | Narrative scientific and repository overview. |

## Generated run files

| Relative path | Meaning |
| --- | --- |
| `run_spec.json` | Byte-for-byte frozen launch spec. |
| `operations/run_spec.sha256` | Resume guard for the frozen spec. |
| `operations/services.json` | Stable service-unit identities. |
| `operations/events.jsonl` | Structured lifecycle events. |
| `logs/BABYSIT-*.md` | Human-readable handoff log. |
| `provenance/dmw_input_manifest.json` | Isolated DMW branch and collection evidence. |
| `provenance/environment_lock.json` | Schema-v2 source, package, provider, and input evidence. |
| `raw/<condition>/<unit>.json` | Authoritative terminal observation. |
| `attempts/<condition>/<unit>.json` | Condition progress and retry state. |
| `annotation_attempts/<unit>.json` | Shared annotation-preparation state. |
| `summaries/run_manifest.json` | Immutable scientific runner configuration, schema version 6 for pair runs. |

## Service units

For run ID `<run-id>`, the lifecycle owns:

```text
dmw-experiment-<run-id>-backend.service
dmw-experiment-<run-id>-runner.service
dmw-experiment-<run-id>-watchdog.service
```

The backend and watchdog use `Restart=no`. The runner uses
`Restart=on-failure` with a 30-second delay. A completed matrix with measured
model failures exits normally and therefore does not restart.

## Figure visual tokens

Plot defaults are owned by
`src/dmw_experiments/shared/analysis/plotting/style.py`. Reuse its paper font,
grid, line, and export settings through `dmw_experiments.shared.analysis`
instead of redeclaring Matplotlib defaults in individual study plots.
