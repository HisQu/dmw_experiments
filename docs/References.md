# Reference

## Table of contents

1. [Project paths](#project-paths)
2. [Haiu comparison package](#haiu-comparison-package)
3. [Python interface](#python-interface)
4. [Commands](#commands)
5. [Run files](#run-files)
6. [Configuration layers](#configuration-layers)
7. [Release commands](#release-commands)

## Project paths

| Path | Owner |
| --- | --- |
| `src/dmw_experiments/shared/` | Reusable code. |
| `src/dmw_experiments/studies/haiu_comparison/` | Haiu comparison code. |
| `studies_run_templates/haiu_comparison/template/` | Complete tracked data template. |
| `studies_runs/haiu_comparison/` | Ignored full runs. |
| `studies_runs/haiu_comparison/git_tracked/` | User-promoted runs. |
| `studies_runs_smoketests/haiu_comparison/` | Ignored smoke runs. |
| `docs/studies/haiu_comparison.md` | Synchronized study overview. |

## Haiu comparison package

| Path | Responsibility |
| --- | --- |
| `model/` | Condition IDs, input population, run contract, results, and copied-run paths. |
| `preparation/` | Catalogue materialization and isolated DMW storage preparation. |
| `data_collection/dmw/` | DMW client, annotation, and workflow conditions. |
| `data_collection/haiu/` | Standalone Haiu retrieval, prompts, and generation. |
| `data_collection/runner.py` | Provider-cell scheduling, retries, and checkpoints. |
| `operations/` | Lifecycle, runtime, status, environment locks, run creation, and promotion. |
| `analysis/workbooks/` | Raw-result, pairwise, and quality-review workbooks. |
| `analysis/quality/` | Blinded grade and error analysis. |
| `analysis/plots/` | Diagnostic and publication plot exports. |
| `entrypoints/` | Backend, runner bootstrap, and LM Studio proxy processes. |
| `study.py` | Supported lifecycle façade. |

## Python interface

Construct
`dmw_experiments.studies.haiu_comparison.HaiuComparisonStudy` with
`AppRuntimeConfig`. Its public methods are `new_run`, `validate`, `start`,
`status`, `pause`, `resume`, `analyze`, and `prepare_promotion`. The Typer CLI
calls this façade. The lifecycle packages above are implementation modules,
not a second public orchestration interface.

## Commands

| Command | Effect |
| --- | --- |
| `dmw_experiments new-run` | Copy and initialize a run template. |
| `dmw_experiments validate --run-dir PATH` | Validate without storage or service mutation. |
| `dmw_experiments start --run-dir PATH` | Prepare fresh storage and launch selected executions. |
| `dmw_experiments status --run-dir PATH` | Count terminal and provisional cells. |
| `dmw_experiments pause --run-dir PATH` | Stop selected provider services safely. |
| `dmw_experiments resume --run-dir PATH` | Resume the exact frozen run. |
| `dmw_experiments analyze --run-dir PATH` | Regenerate derived workbooks and plots. |
| `dmw_experiments prepare-promotion --run-dir PATH` | Validate publication readiness and build harness distributions. |

Lifecycle commands accept repeated `--execution academiccloud|lmstudio`.
Omitting the filter selects every enabled execution.

## Run files

| File or directory | Contract |
| --- | --- |
| `run.toml` | Scientific, provider, and storage identity. |
| `run.env` | Exhaustive shared non-secret runtime settings. |
| `run.<execution>.env` | Small provider override layer. |
| `run.sh`, `run.ps1` | Human entry points. |
| `run.AGENT.md` | Agent entry point and evidence rules. |
| `INPUTS/` | Frozen study inputs copied before launch. |
| `locks/` | Stack and dependency locks; promotion distributions. |
| `raw-<execution>/intermediates-<condition>/` | Pipeline checkpoints and sidecars. |
| `raw-<execution>/result-<condition>/` | Terminal JSON, YAML, and Turtle. |
| `environment/` | Frozen locks, manifests, events, and service identities. |
| `logs/` | Provider logs and BABYSIT journals. |
| `analysis/` | Intermediates, diagnostics, and workbooks. |
| `plots/` | Figures, captions, and plot manifests. |

## Configuration layers

AppRC resolves settings in this order: packaged shared defaults, app-wide
machine configuration, run-local `run.env`, provider file, then lifecycle-
derived identities. Explicit run files override earlier non-secret defaults.
Real credentials must resolve from the app-wide file. `RG_RAW_COLLECTION`,
annotation/ontology collections, and `HAIU_STORAGE` derive from `run.toml` and
the run identity.

## Release commands

| Recipe | Effect |
| --- | --- |
| `just release-check` | Run both Python environments and validate artifacts. |
| `just release patch|minor|major` | Prepare a checked version commit and annotated tag. |
| `just build` | Build the wheel and source archive locally. |

A pushed `v*` tag triggers CI and creates the GitHub Release after all gates
pass.
