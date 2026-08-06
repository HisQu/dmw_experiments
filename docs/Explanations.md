<!-- ======================================================== -->
## Table Of Contents
<!-- ======================================================== -->

1. [Explanations](#1-explanations)
2. [System Architecture](#2-system-architecture)
   1. [System Model](#system-model)
   2. [Package Layout](#package-layout)
3. [Configuration And Dependency Model](#3-configuration-and-dependency-model)
   1. [Configuration Model](#configuration-model)
   2. [Dependency Model](#dependency-model)
4. [Failure Model](#4-failure-model)

<br>

# 1. Explanations

Use this file when you need to understand why `dmw_experiments` is shaped the way
it is. Use [How-To User Guides](How-To-User-Guides.md) for commands and
[References](References.md) for exact names.

<br>

# 2. System Architecture

<!-- ======================================================== -->
## System Model
<!-- ======================================================== -->

`dmw_experiments` is a src-layout Python project. Runtime code lives under
[src/dmw_experiments](../src/dmw_experiments), tests live under [tests](../tests),
and long-form documentation lives under [docs](.).

The main idea is simple:

1. `pyproject.toml` describes the package and development tools.
2. `src/dmw_experiments` owns importable runtime behavior.
3. `tests` verifies behavior from the outside where possible.
4. `docs` explains setup, workflows, exact names, and design context.
5. `justfile` provides repeatable maintainer commands.

> [!NOTE]
> Related links:
> - Use [install the package](How-To-User-Guides.md#install-the-package) for the first setup path.
> - Use [project paths](References.md#project-paths) for exact source owners.
> - Use [repository routing](Development.md#repository-routing) before moving behavior.

<br>

<!-- ======================================================== -->
## Package Layout
<!-- ======================================================== -->

The project uses a `src` layout so imports come from the installed package
rather than accidentally from the repository root.

Core boundaries:

| Area | Responsibility |
|---|---|
| `src/dmw_experiments` | Runtime behavior and package-owned helpers. |
| `src/dmw_experiments/cli` | Typer command tree and CLI presentation. |
| `src/dmw_experiments/config` | AppRC config contract, packaged defaults, and config facade. |
| `tests` | Behavior checks, fixtures, and regression tests. |
| `examples` | Small user-facing examples. |
| `docs` | Longer usage, reference, and architecture material. |
| `assets` | Static project assets. |

Keep broadly reusable helpers near the package area that owns the domain. Keep
one-off diagnostics in the nearest existing tooling, test, or experiment area.

> [!NOTE]
> Related: use [Development: source editing rules](Development.md#source-editing-rules)
> for implementation rules that preserve these boundaries.

<br>

# 3. Configuration And Dependency Model

<!-- ======================================================== -->
## Configuration Model
<!-- ======================================================== -->

`dmw_experiments` uses AppRC for application configuration. The application owns
its typed `rc.Config` declarations in `src/dmw_experiments/config/owners.py`;
AppRC derives the normalized owner inventory from `APP_RC` and owns the
repeatable workflows around it:

- packaged defaults in `src/dmw_experiments/config/.env.shared`
- optional multi-storage index selected by `DMW_EXPERIMENTS_APPRC_TOML`
- storage-local overrides in `<storage-root>/.env.apprc-storage`
- shell and explicit dotenv overrides for one process
- generated `config` CLI commands and the Textual editor

Keep new config fields in the AppRC `rc.Config` class before reading them from
runtime code. That keeps defaults, docs metadata, CLI editing, and validation
pointing at the same contract.

When configuration affects a user-visible workflow, update
[How-To User Guides](How-To-User-Guides.md) and [References](References.md)
together.

> [!NOTE]
> Related: use [environment variables](References.md#environment-variables) for
> exact variable names and [configuration files](References.md#configuration-files)
> for file owners.

<br>

<!-- ======================================================== -->
## Dependency Model
<!-- ======================================================== -->

The project separates dependency types by audience:

| Dependency Type | Owner | Audience |
|---|---|---|
| Runtime dependency | `[project].dependencies` | Users who install the package. |
| Optional extra | `[project.optional-dependencies]` | Users who opt into an optional runtime feature. |
| Dependency group | `[dependency-groups]` | Maintainers who run tests, typing, linting, docs, or profiling. |

This split keeps normal installs small while leaving maintainer workflows
repeatable. AppRC is a runtime dependency because the generated command tree
uses AppRC for dotenv layering, storage registry management, config editing,
and logging setup.

> [!NOTE]
> Related links:
> - Use [install the package](How-To-User-Guides.md#install-the-package) for install commands.
> - Use [dependency surfaces](References.md#dependency-surfaces) for exact `pyproject.toml` sections.

<br>

# 4. Failure Model

Most failures become easier to debug when checked in this order:

1. Confirm the current directory is the project root.
2. Confirm the active Python executable.
3. Confirm the package imports from `src/dmw_experiments` or the editable install.
4. Confirm dependencies are installed for the workflow.
5. Confirm the command is documented in [References](References.md).
6. Re-run the smallest command that reproduces the problem.

```bash
pwd
python -c "import sys; print(sys.executable)"
python -c "import dmw_experiments; print(dmw_experiments.__file__)"
just --list
```

> [!NOTE]
> Related links:
> - Use [environment problems](How-To-User-Guides.md#environment-problems) for import and interpreter checks.
> - Use [command problems](How-To-User-Guides.md#command-problems) when a recipe fails.
> - Use [command reference](References.md#command-reference) for the expected command names.
