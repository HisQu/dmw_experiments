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
3. [{initial\_version} - {scaffold\_date}](#initial_version---scaffold_date)

<br>

---

<br>

<!-- ======================================================== -->

# [Unreleased]

<br>

### 💥 Breaking Change Summary

- Breaking: Removed the scaffold-only `app.message` configuration field.
  Affected: Users of the initial project scaffold.
  Migration: Remove `DMW_EXPERIMENTS_MESSAGE`; configure the experiment
  storage and runtime fields instead.

<br>

### ➕ Added

- Added the packaged DMW--Haiu comparison execution and analysis harness.
- Added immutable header--sublemma inputs, isolated smoke/full specifications,
  the published DMW-stack contract, and the ignored `output/` workspace.
- Added locked publication and analysis dependency sets for Python 3.12.
<br>

### 💔 Changed

- Changed experiment ownership from Haiu to the standalone
  `dmw_experiments` package while preserving the tested scientific behavior.
<br>

### ⚠️ Deprecated

<br>

### 🗑️ Removed

<br>

### 🔨 Fixed

<br>

---

<br>

<!-- ======================================================== -->

# 0.1.0 - 2026-08-06

<br>

### ➕ Added

- Released `dmw_experiments`.
- Added src-layout packaging, Typer CLI entrypoints, AppRC configuration, documentation, tests, and maintainer tooling.
