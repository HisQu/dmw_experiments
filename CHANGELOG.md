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
3. [0.1.0 - 2026-08-06](#010---2026-08-06)

<br>

---

<br>

<!-- ======================================================== -->

# [Unreleased]

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

### ⚠️ Deprecated

<br>

### 🗑️ Removed

<br>

### 🔨 Fixed

- Kept user-systemd launches attached to the locked virtual-environment
  interpreter instead of resolving its executable symlink to the base Python.

<br>

---

<br>

<!-- ======================================================== -->

# 0.1.0 - 2026-08-06

<br>

### ➕ Added

- Released `dmw_experiments`.
- Added src-layout packaging, Typer CLI entrypoints, AppRC configuration, documentation, tests, and maintainer tooling.
