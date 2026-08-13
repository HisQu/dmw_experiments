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
3. [0.5.6 - 2026-08-11](#056---2026-08-11)
4. [0.5.5 - 2026-08-11](#055---2026-08-11)
5. [0.5.4 - 2026-08-11](#054---2026-08-11)
6. [0.5.3 - 2026-08-10](#053---2026-08-10)
7. [0.5.2 - 2026-08-10](#052---2026-08-10)
8. [0.5.1 - 2026-08-10](#051---2026-08-10)
9. [0.5.0 - 2026-08-10](#050---2026-08-10)
10. [0.4.1 - 2026-08-10](#041---2026-08-10)
11. [0.4.0 - 2026-08-07](#040---2026-08-07)
12. [0.3.0 - 2026-08-06](#030---2026-08-06)
13. [0.2.0 - 2026-08-06](#020---2026-08-06)
14. [0.1.0 - 2026-08-06](#010---2026-08-06)

<br>

---

<br>

<!-- ======================================================== -->

# [Unreleased]

<br>

### 💥 Breaking changes

- Breaking: Analysis workbooks and matching reveal keys now include the shared
  invocation timestamp in their filenames.
  Affected: Scripts that open fixed names such as `overview.xlsx` or
  `masked_historian_quality_review.xlsx`.
  Migration: Read the paths returned by `analyze`, or select the required
  timestamped snapshot below `analysis/workbooks/<execution>/`.

<br>

### ➕ Added

<br>

### 💔 Changed

<br>

### ⚠️ Deprecated

<br>

### 🗑️ Removed

<br>

### 🔨 Fixed

- Accepted the flat reveal-key and `Historian_Review` worksheet layout emitted
  by single-provider runs when generating historian-grade analyses or
  recovering a matching key from immutable review content. Numeric Excel
  values of `3` are normalized to the documented top-coded `3+` interpretation
  band.

<br>

### 🔒 Security

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.6 - 2026-08-11

<br>

### 🔨 Fixed

- Updated the governed runtime to OPA 2.1.4. Empty Stage-1 replies now retain
  provider metadata and exact provider messages; confirmed output-length
  exhaustion is terminal instead of being retried as generic unavailability.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.5 - 2026-08-11

<br>

### 🔨 Fixed

- Kept collection preflight, environment-lock capture, and published release
  checkouts on one GTA 0.2.5 contract. Resume no longer rejects the tagged
  observability runtime before provider work starts.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.4 - 2026-08-11

<br>

### 🔨 Fixed

- Preserved exact GTA assistant messages as per-stage response sidecars for DMW
  conditions, including provider reasoning fields when length-limited responses
  have empty ordinary content. Compact analytical metadata no longer duplicates
  those potentially large documents.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.3 - 2026-08-10

<br>

### 🔨 Fixed

- Included every configured provider attempt when deriving the outer condition
  wall-clock guard. A later attempt can now return its own response or timeout
  diagnostic instead of being interrupted at the duration of the first two
  calls.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.2 - 2026-08-10

<br>

### 🔨 Fixed

- Extended the outer condition wall-clock guard beyond the configured DMW
  worker and sequential provider-call limits. Provider and worker failures can
  now return their diagnostic payload before the harness interrupts a cell.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.1 - 2026-08-10

<br>

### 🔨 Fixed

- Allowed an existing run to retain its frozen DMW 1.1.3 stack identity while
  adopting the exact DMW 1.1.4 and OPA 2.1.3 runtime transition. New run
  templates continue to require the current DMW 1.1.4 stack identity.

<br>

---

<br>

<!-- ======================================================== -->

# 0.5.0 - 2026-08-10

<br>

### 💥 Breaking changes

- Breaking: Replaced flat per-condition result files and duplicate full-result
  JSON/YAML mirrors with schema-v3 per-unit attempt and terminal bundles.
  Affected: Scripts that read `result-<condition>/<unit-id>.*` or
  `intermediates-<condition>/<unit-id>.*` directly.
  Migration: Pause the provider, run `./run.sh migrate-artifacts --execution
  <execution>`, verify `./run.sh status`, then resume the same frozen run. New
  readers should follow artifact references from each nested `result.json`.

<br>

### ➕ Added

- Added immutable numbered attempt directories whose failed attempts always
  end in `-failed`, with separate metadata, prompts, responses, retrieval
  evidence, and an exact compressed upstream result.
- Added verified, idempotent migration for stopped schema-v2 runs. It retains
  a hash-inventoried recovery snapshot and records the clean experiment-harness
  transition without rewriting the scientific environment lock.
- Added content hashes to every external artifact reference and made analysis
  reject missing or changed schema-v3 evidence.
- Added stopped-run artifact refresh and explicit runtime-transition commands.
  They preserve the immutable environment lock while recording the exact
  clean harness and governed DMW-stack package identities adopted during a
  long run.

<br>

### 💔 Changed

- Stored a shared NER annotation once per input unit instead of copying it into
  both DMW condition directories.
- Disabled DMW's redundant server-side debug-file copy because the returned
  debug payload is preserved exactly in the attempt's compressed upstream
  result.
- Updated the experiment runtime to Haiu 1.8.1. Non-streaming calls now retain
  complete provider assistant messages for terminal failure analysis.
- Updated the experiment runtime to DMW 1.1.4 and OPA 2.1.3. Failed workflows
  now retain the exact successful Stage-1 assistant reply when a later stage
  fails, without changing model calls or retry decisions.
- Treat one complete outer Markdown `ttl` or `turtle` fence as a serialization
  wrapper. Exact provider text stays in `stage-2.raw.txt`; `ontology.ttl`,
  syntax validation, and downstream analysis use the unwrapped Turtle body.

<br>

### 🔨 Fixed

- Fixed completed schema-v2 cells overwriting the annotation JSON with Stage-1
  capture metadata by giving both artifacts unambiguous schema-v3 paths.
- Fixed copied Bash and PowerShell entry points using an unrelated system
  Python when the repository virtual environment is available.
- Fixed failed standalone calls discarding provider-native output when
  `message.content` is empty, and fixed fence-wrapped valid Turtle being
  counted as a parser failure.

<br>

---

<br>

<!-- ======================================================== -->

# 0.4.1 - 2026-08-10

<br>

### 🔨 Fixed

- Removed obsolete TUSTEP layout controls from the 44 affected
  header--sublemma input units while preserving every unaffected text field
  byte-for-byte. The catalogue records the normalization evidence and rejects
  stale control-bearing inputs before external storage or provider work.

<br>

---

<br>

<!-- ======================================================== -->

# 0.4.0 - 2026-08-07

<br>

### 💥 Breaking changes

- Breaking: Reorganized Haiu comparison Python imports around the experiment
  lifecycle instead of the former `comparison_experiment`,
  `haiu_ontologizer`, and root-script layout.
  Affected: Python callers importing study internals directly.
  Migration: Use `HaiuComparisonStudy` for supported orchestration or import
  domain contracts from `dmw_experiments.studies.haiu_comparison.model`.

<br>

### ➕ Added

- Added typed condition, execution, run-contract, and copied-run models so all
  lifecycle phases resolve artifacts through one validated run directory.
- Added `HaiuComparisonStudy` as the supported Python façade for the same run
  lifecycle exposed by the CLI.
- Added an authoritative branch-aware retrieval-workspace contract. Each
  pair run now verifies or prepares the shared reference index before timed
  conditions, so condition order cannot assign indexing work to one RAG path.
- Added strict workbook and plot export for the provider executions enabled by
  a run, including AcademicCloud-only studies. Cross-provider review export is
  retained when both providers are enabled.
- Declared zero DMW ontology examples for the header--sublemma study because
  the published whole-regest FAISS index has no query identity for synthetic
  pair IDs. This keeps the configured contract equal to the effective prompt.

<br>

### 💔 Changed

- Separated Haiu comparison model and preparation code from collection,
  operations, and analysis implementations.
- Moved provider process launchers below `entrypoints` and separated runtime,
  environment-lock, status, and repository-path ownership below `operations`.
- Separated derived reporting into `analysis.workbooks`, `analysis.quality`,
  and `analysis.plots`, with import-boundary tests between domain, collection,
  operations, and analysis code.

<br>

### 🗑️ Removed

- Removed the v0.2 finalizer and raw-materialization wrappers, which read an
  obsolete run layout and were not used by the v0.3 lifecycle.
- Removed the Haiu 1.7.3 preliminary exporter and separate-provider historian
  CLI wrapper. Current analysis starts from one copied schema-v3 run.

<br>

### 🔨 Fixed

- Fixed first launch so stack-version validation reads the nested installed
  package table returned by environment-lock capture.
- Fixed provider launch so every fresh execution receives isolated run-owned
  Haiu storage and LMStudio uses the endpoint resolved from its run environment.
- Completed the exhaustive run environment with DMW's ontology repository and
  app-wide GitHub credential settings so annotation guideline retrieval cannot
  silently target an undefined repository.
- Allowed the header--sublemma publication protocol to collect the complete
  three-condition matrix with either registered provider profile.
- Made pause tolerate the short systemd restart interval in which a supervised
  runner has no current main process.
- Corrected AppRC setup documentation to use `config app init` and
  `config edit`.
- Fixed standalone HAIU retrieval attaching to the obsolete default workdir
  instead of the reference workspace identified by the frozen DMW branch.

<br>

---

<br>

<!-- ======================================================== -->

# 0.3.0 - 2026-08-06

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
- Breaking: Replaced tracked `studies/` specifications and generated `output/`
  routing with complete templates, ignored full/smoke run roots, and an
  explicit promoted-run area.
  Affected: Operators, scripts, and agents using JSON specs or separate raw,
  log, analysis, and plot directories.
  Migration: Create a copy with `dmw_experiments new-run`, then operate the
  copied directory through `run.sh`, `run.ps1`, or `--run-dir` commands.
- Breaking: Replaced the `smoke` and `run` commands plus every `--spec` option
  with `new-run` and `start --run-dir`; analysis now accepts one complete run
  instead of two provider run paths.
  Affected: CLI automation written for 0.2.0.
  Migration: Create one run with the required repeated `--execution` options,
  then use `validate|start|status|pause|resume|analyze --run-dir PATH`.
- Breaking: Changed canonical raw artifact paths to flat
  `raw-<execution>/intermediates-<condition>` and
  `raw-<execution>/result-<condition>` directories.
  Affected: Analysis or archival code reading 0.2.0 raw layouts.
  Migration: Finish old runs with v0.2.0. New runs and the 0.3.0 exporter use
  only the new copied-run layout; no legacy reader is provided.

<br>

### ➕ Added

- Added Python 3.12 and 3.13 CI plus a tag-triggered workflow that validates
  artifacts and creates a GitHub Release from the matching changelog section.
- Added `just release-check` and `just release patch|minor|major` as the single
  local release preparation path.
- Added synchronized study overviews below `docs/studies/` and
  `studies_run_templates/haiu_comparison/` with the scientific design,
  source/output map, published repositories, and evidence rules.
- Added a complete data-only Haiu comparison template with Bash, PowerShell,
  and agent entry points, exhaustive non-secret configuration, locks, inputs,
  independent provider areas, analysis destinations, plots, and logs.
- Added AppRC app-wide credential ownership, one run per AppRC storage,
  redacted effective-setting provenance, and explicit provider override layers.
- Added independent AcademicCloud and LM Studio user-systemd service sets in
  one run, schema-v3 environment locks, and per-provider BABYSIT journals.
- Added `prepare-promotion` to validate the selected dataset and build the
  matching experiment wheel and source archive below `locks/dist/`.

<br>

### 💔 Changed

- Separated reusable Python code under `dmw_experiments.shared` from
  scientific code under `dmw_experiments.studies`.
- Made the published DMW stack and complete analysis stack core dependencies;
  tagged releases resolve remote versions and do not require sibling clones.
- Made workbooks, diagnostics, normalized data, plots, logs, and environment
  evidence children of the run they describe.

<br>

### 🗑️ Removed

- Removed scaffold PyPI publishing and alternative version-tag recipes so a
  release tag can only follow the documented GitHub Release preparation path.
- Removed old tracked JSON run specifications, the old default output routing,
  and the obsolete run-spec validation entry point.

<br>

### 🔨 Fixed

- Fixed retrieval-sidecar validation so `.retrieved.ttl` and
  `.retrieved.yaml` keep the `.retrieved` filename marker.
- Made every materialized result, prompt, Stage-1 response, attempt, and
  retrieval path relative to the complete copied run.

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
