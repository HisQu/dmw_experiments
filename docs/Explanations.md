# Explanations

## Table of contents

1. [Ownership model](#ownership-model)
2. [Why the run is the unit of organization](#why-the-run-is-the-unit-of-organization)
3. [Configuration model](#configuration-model)
4. [Execution and failure model](#execution-and-failure-model)
5. [Promotion model](#promotion-model)

## Ownership model

Reusable behavior belongs to `src/dmw_experiments/shared/`. Scientific
behavior belongs to `src/dmw_experiments/studies/<study>/`. Complete data
templates belong to `studies_run_templates/<study>/template/`. Python code is
never copied into a run.

Runs and smoke tests are generated data, so their normal roots are ignored.
This prevents half-finished experiments, secrets, provider logs, and large raw
artifacts from entering Git by accident.

## Why the run is the unit of organization

One run directory contains its inputs, configuration, locks, raw provider
evidence, pipeline intermediates, environment evidence, logs, analysis, plots,
captions, and operator notes. A tired operator does not need to correlate an
analysis directory with a separately named raw run or log directory.

Providers remain flat siblings inside that run. Conditions remain flat
siblings inside each provider. This makes both axes visible in paths without a
deep execution/condition/raw hierarchy.

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

The runner checkpoints attempts and terminal results before continuing. The
watchdog observes both `result-*` and `intermediates-*`. After infrastructure
interruption, resume uses the exact frozen contract. Context or length
exhaustion is a terminal model outcome and is not retried as infrastructure.

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
