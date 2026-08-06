# Changelog

All notable changes to `dmw_experiments` will be documented in this file.

> [!IMPORTANT]
> ## Rules
> 1) Do not remove or change this header and TOC without very good reason. 
> 1) When bumping version, move the sub-sections from `[Unreleased]` to
>    the new version -section. Remove empty sub-sections under released
>    versions. Provide a new `[Unreleased]` section at the top of the
>    changelog with all sections empty (don't remove those).
> 1) Do not remove emojis and use `<br>` and `---`.
> 1) Changelog entries must describe the final net difference from the
>    previous released version. Do not list intermediate pre-release
>    names, helper shapes, fixes, or refactors that were overwritten
>    before release.
> 1) Use `🔨 Fixed` only for defects in previously released behavior.
>    For new features, describe the final shipped behavior under `➕
>    Added`, even if the implementation went through pre-release fixes.



<br>

---

<br>

## Table Of Contents

1. [Changelog](#changelog)
   1. [Table Of Contents](#table-of-contents)
2. [\[Unreleased\]](#unreleased)
3. [0.2.0 - 2026-08-06](#020---2026-08-06)
4. [0.1.0 - 2026-08-06](#010---2026-08-06)

<br>

---

<br>

<!-- ======================================================== -->

# [Unreleased]

<br>

### 💥 Breaking changes

- Breaking: Moved reusable modules below `dmw_experiments.shared`, including
  `analysis`, `artifacts`, `config`, `execution`, `supervision`, and `utils`.
  Affected: Python callers importing these modules from the package root.
  Migration: Insert `.shared` after `dmw_experiments` in those imports.
- Breaking: Renamed the `datamodel_workflow_haiu_comparison` study, Python
  package, test tree, tracked data directory, and run-spec study identifier to
  `haiu_comparison`.
  Affected: Custom scripts, imports, and run specifications using the former
  study name; active runs created with 0.2.0.
  Migration: Replace the old study name in paths and imports. Finish or resume
  an active 0.2.0 run with the v0.2.0 checkout because frozen run identities
  are intentionally not rewritten during an upgrade.

<br>

### ➕ Added

- Added Python 3.12 and 3.13 CI plus a tag-triggered workflow that validates
  artifacts and creates a GitHub Release from the matching changelog section.
- Added `just release-check` and `just release patch|minor|major` as the single
  local release preparation path.
- Added synchronized study overviews below `docs/studies/` and
  `studies/haiu_comparison/` with the scientific design, source/output map,
  published repositories, and evidence rules.

<br>

### 💔 Changed

- Separated reusable Python code under `dmw_experiments.shared` from
  scientific code under `dmw_experiments.studies`.
- Assigned fresh 2026-08-07 smoke and full-run storage identities after the
  earlier disposable smoke was paused during provider congestion.

<br>

### ⚠️ Deprecated

<br>

### 🗑️ Removed

- Removed scaffold PyPI publishing and alternative version-tag recipes so a
  release tag can only follow the documented GitHub Release preparation path.

<br>

### 🔨 Fixed

<br>

### 🔒 Security

<br>

---

<br>

<!-- ======================================================== -->

# 0.2.0 - 2026-08-06

<br>

### 💥 Breaking changes

- Breaking: Removed the scaffold-only `app.message` configuration field.
  Affected: Users of the initial project scaffold.
  Migration: Remove `DMW_EXPERIMENTS_MESSAGE`; configure the experiment
  storage and runtime fields instead.
- Breaking: Replaced the scaffold command surface with the experiment
  lifecycle commands `validate`, `smoke`, `run`, `status`, `pause`, `resume`,
  and `analyze`.
  Affected: Users invoking the 0.1.0 example command.
  Migration: Use the command matching the required run-lifecycle action.

<br>

### ➕ Added

- Added the packaged DMW--Haiu comparison execution and analysis harness.
- Added immutable header--sublemma inputs, isolated smoke/full specifications,
  the published DMW-stack contract, and the ignored `output/` workspace.
- Added run-local service logs, BABYSIT journals, lifecycle events, frozen
  specifications, and schema-v2 provenance artifacts.
- Added one user-systemd owner for the backend, resumable runner, and
  progress watchdog of each run.
- Added locked core publication and analysis dependencies for Python 3.12 and
  3.13, including a plain-pip runtime export.
<br>

### 💔 Changed

- Changed experiment ownership from Haiu to the standalone
  `dmw_experiments` package while preserving the tested scientific behavior.
- Changed release-stack provenance checkouts to clone ignored published tags
  automatically instead of requiring neighboring source repositories.
<br>

### 🔨 Fixed

- Kept user-systemd launches attached to the locked virtual-environment
  interpreter instead of resolving its executable symlink to the base Python.
- Rejected missing or repository-relative NER example indexes before creating
  storage or starting a smoke service.

<br>

---

<br>

<!-- ======================================================== -->

# 0.1.0 - 2026-08-06

<br>

### ➕ Added

- Released `dmw_experiments`.
- Added src-layout packaging, Typer CLI entrypoints, AppRC configuration, documentation, tests, and maintainer tooling.
