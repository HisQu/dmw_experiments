# Explanations

## Table of contents

1. [Ownership model](#ownership-model)
2. [Study package lifecycle](#study-package-lifecycle)
3. [Why the run is the unit of organization](#why-the-run-is-the-unit-of-organization)
4. [Configuration model](#configuration-model)
5. [Execution and failure model](#execution-and-failure-model)
6. [Promotion model](#promotion-model)

## Ownership model

Reusable behavior belongs to `src/dmw_experiments/shared/`. Scientific
behavior belongs to `src/dmw_experiments/studies/<study>/`. Complete data
templates belong to `studies_run_templates/<study>/template/`. Python code is
never copied into a run.

Runs and smoke tests are generated data, so their normal roots are ignored.
This prevents half-finished experiments, secrets, provider logs, and large raw
artifacts from entering Git by accident.

## Study package lifecycle

The Haiu comparison package follows the order in which a scientist uses it:

```text
haiu_comparison/
├── model/             # Stable IDs, run contracts, inputs, results, and paths
├── preparation/       # Frozen input catalogue and isolated DMW storage
├── data_collection/   # DMW and standalone Haiu condition adapters
├── operations/        # Validation, supervision, status, locks, and promotion
├── analysis/          # Workbooks, quality review, and plots
├── entrypoints/       # Processes started by user-systemd
└── study.py           # Supported HaiuComparisonStudy façade
```

`model` does not import a lifecycle implementation. `data_collection` does
not import analysis. Analysis reads preserved evidence and model contracts; it
does not call collection or operational code. `entrypoints` only bootstraps
supervised processes. Architecture tests enforce these directions.

The CLI and Python callers use `HaiuComparisonStudy`. Internal module imports
may change when the study implementation is refactored; the façade is the
supported orchestration boundary.

## Why the run is the unit of organization

One run directory contains its inputs, configuration, locks, raw provider
evidence, pipeline intermediates, environment evidence, logs, analysis, plots,
captions, and operator notes. A tired operator does not need to correlate an
analysis directory with a separately named raw run or log directory.

Providers remain flat siblings inside that run. Conditions remain flat
siblings inside each provider. Within a condition, one input-unit directory
owns its checkpoint, numbered attempts, and terminal result. This keeps both
experimental axes visible while preventing prompts, responses, and retries
from becoming one undifferentiated file list.

## Configuration model

`run.toml` answers what is measured and where isolated storage lives.
`run.env` answers which shared runtime settings apply. Provider dotenv files
state only differences. AppRC app-wide configuration owns real credentials
and machine-local assets.

The lifecycle selects the copied run as one AppRC storage, loads the explicit
run and provider files with override semantics, derives storage settings from
`run.toml`, and records redacted provenance. This gives each run inspectable
settings without copying secrets.

## Execution and failure model

Each provider owns a backend, runner, watchdog, DMW branch, MongoDB
collections, Haiu storage, logs, and BABYSIT journal. Provider progress is
independent.

The runner checkpoints attempts and terminal results before continuing. Every
unsuccessful attempt is visibly named `<NNN>-failed`; terminal model failure
does not look like a missing attempt. Shared annotation evidence is stored
once, while each condition attempt owns its prompts, responses, retrieval
evidence, and exact compressed upstream payload. The small terminal index
groups scalar fields and verifies its external files by hash.

The watchdog observes both `result-*` and `intermediates-*`. After
infrastructure interruption, resume uses the exact frozen contract. Context or
length exhaustion is a terminal model outcome and is not retried as
infrastructure.

## Promotion model

A new run is wholly untracked. The user decides whether it becomes a published
artifact only after inspecting the results. Promotion preparation validates
the matrix and builds the exact `dmw_experiments` wheel and source archive in
the run's `locks/dist/`. The user then copies the whole run into the explicit
`git_tracked/` area.

This separates gathering data from choosing evidence. It also makes an
incomplete promoted dataset an explicit user decision instead of a side effect
of creating every run in a partly tracked directory.

> [!NOTE]
> Use [the how-to guide](How-To-User-Guides.md) for commands and
> [the reference](References.md) for exact path names.
