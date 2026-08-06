<!-- ======================================================== -->
## Table Of Contents
<!-- ======================================================== -->

1. [Development](#1-development)
2. [Maintainer Workflow](#2-maintainer-workflow)
   1. [Maintainer Loop](#maintainer-loop)
   2. [Repository Routing](#repository-routing)
   3. [Before Editing](#before-editing)
   4. [GitHub Release Cycle](#github-release-cycle)
3. [Implementation Standards](#3-implementation-standards)
   1. [Source Editing Rules](#source-editing-rules)
   2. [Documentation Authoring](#documentation-authoring)
4. [Documentation Standards](#4-documentation-standards)
   1. [Heading Structure](#heading-structure)
   2. [Markdown Formatting Rules](#markdown-formatting-rules)
   3. [GitHub Callouts](#github-callouts)
   4. [Link And Backlink Rules](#link-and-backlink-rules)
   5. [Static Figure Rules](#static-figure-rules)
5. [Verification And Commit](#5-verification-and-commit)
   1. [Verification](#verification)
   2. [Review Checklist](#review-checklist)
   3. [Commit Checklist](#commit-checklist)

<br>

# 1. Development

Use this file before changing `dmw_experiments`.

<br>

# 2. Maintainer Workflow

<!-- ======================================================== -->
## Maintainer Loop
<!-- ======================================================== -->

The maintainer loop is:

1. Read [AGENTS.md](../AGENTS.md), this file, and the relevant docs chapter.
2. Check the current worktree.
3. Locate the source owner for the behavior.
4. Edit the smallest source surface that owns the behavior.
5. Run focused verification.
6. Run broader verification when shared behavior changes.
7. Review the Git diff.
8. Commit.

> [!NOTE]
> Related links:
> - Use [How-To User Guides](How-To-User-Guides.md) for user-facing command recipes.
> - Use [References](References.md) for exact paths, commands, and public surfaces.
> - Use [Explanations](Explanations.md) for the project model behind the workflow.

<br>

<!-- ======================================================== -->
## Repository Routing
<!-- ======================================================== -->

Put changes where the repo already has an owner.

| Change Type | Owner |
|---|---|
| Reusable runtime and analysis behavior | [src/dmw_experiments/shared](../src/dmw_experiments/shared) |
| Scientific behavior | [src/dmw_experiments/studies](../src/dmw_experiments/studies) |
| Shared tests | [tests/shared](../tests/shared) |
| Study tests | [tests/studies](../tests/studies) |
| Copyable study data | [studies_run_templates](../studies_run_templates) |
| Static assets | [assets](../assets) |
| Documentation | [docs](.) |
| Project metadata and dependency declarations | [pyproject.toml](../pyproject.toml) |
| Development recipes | [justfile](../justfile) |
| Local agent guidance | [AGENTS.md](../AGENTS.md) |

Ask before creating a new top-level directory when one of these owners is a
reasonable fit.

> [!NOTE]
> Related: use [project paths](References.md#project-paths) for source file
> owners and [ownership model](Explanations.md#ownership-model) for import
> boundaries.

<br>

<!-- ======================================================== -->
## Before Editing
<!-- ======================================================== -->

Run these checks before a non-trivial change:

```bash
git status --short
rg --files
```

Then read the source owner and nearby files. For example, a CLI change usually
requires checking `src/dmw_experiments/cli/app.py`, the thin wrapper in
`src/dmw_experiments/main.py`, tests, README, and docs references.

Use `just sync-local-stack` when debugging against neighboring editable DMW,
GTA, Haiu, and OPA checkouts. This overlays the active `.venv` only; it does
not edit `pyproject.toml` or any release lock. Run `just sync` to restore the
published stack before verification or release.

> [!IMPORTANT]
> Do not weaken production contracts to make a test easier. Add or reuse a
> dedicated test helper when a test needs lighter setup.

> [!NOTE]
> Related: use [verification](#verification) for the local verification
> checklist.

<br>

<!-- ======================================================== -->
## GitHub Release Cycle
<!-- ======================================================== -->

Tagged releases create GitHub Releases with a validated wheel, source archive,
and the matching `CHANGELOG.md` section. PyPI publishing is not part of this
release path.

Prepare and publish a release in this order:

1. Move the current `[Unreleased]` entries into the next version section in
   `CHANGELOG.md`. Leave every `[Unreleased]` category present and empty.
2. Commit the changelog and all intended source changes.
3. Run the complete local rehearsal:

   ```bash
   just release-check
   ```

4. Prepare the version commit and annotated tag. Choose the semantic version
   level explicitly:

   ```bash
   just release patch
   # or: just release minor
   # or: just release major
   ```

5. Review the generated version commit and local tag.
6. Push `main` and the tag together:

   ```bash
   git push origin main vX.Y.Z
   ```

The `release` recipe does not upload anything. A pushed `v*` tag starts
`.github/workflows/release.yml`. GitHub reruns the Python 3.12 and 3.13 CI
matrix, rebuilds and smoke-checks the wheel and source archive, extracts the
matching changelog section, and creates the GitHub Release only after every
gate passes. A failed workflow leaves the tag visible but does not publish a
Release object.

| Recipe | Purpose |
| --- | --- |
| `just release-check` | Run both supported Python environments and validate release artifacts without uploading. |
| `just release patch\|minor\|major` | Prepare the checked version commit and annotated local tag. |
| `just build` | Rebuild the wheel and source archive for inspection. |

> [!IMPORTANT]
> Do not create or push a release tag manually before the changelog section and
> version files agree. The workflow deliberately refuses missing release notes
> or incorrectly named artifacts.

> [!NOTE]
> Related: use the [dependency surfaces](References.md#dependency-surfaces) to
> verify which lock files belong in the version commit.

<br>

# 3. Implementation Standards

<!-- ======================================================== -->
## Source Editing Rules
<!-- ======================================================== -->

Follow these rules for normal edits:

- Keep reusable runtime and analysis behavior in
  [src/dmw_experiments/shared](../src/dmw_experiments/shared).
- Keep scientific behavior in the matching package below
  [src/dmw_experiments/studies](../src/dmw_experiments/studies).
- Organize study code by lifecycle ownership. For the Haiu comparison, use
  `model`, `preparation`, `data_collection`, `operations`, `analysis`, and
  `entrypoints`; route supported orchestration through `study.py`.
- Keep CLI behavior in `src/dmw_experiments/cli/app.py`; keep
  `src/dmw_experiments/main.py` wrapper-only.
- Keep tests in [tests](../tests).
- Reuse existing helpers before adding new helpers.
- Keep `__init__.py` files limited to imports and module docstrings.
- Prefer exact domain attributes over defensive probes against strict objects.
- Document public behavior with Sphinx-style docstrings.
- Update docs when a change affects setup, usage, CLI behavior, public APIs,
  environment variables, or user-visible workflows.

> [!NOTE]
> Related: use [the Python interface](References.md#python-interface) for the
> surfaces that need stable names and documentation.

<br>

<!-- ======================================================== -->
## Documentation Authoring
<!-- ======================================================== -->

Docs live in [docs](.) and follow the standards in this file.

When editing docs:

1. Keep [docs/README.md](README.md) as the reading map.
2. Put procedures in [How-To User Guides](How-To-User-Guides.md).
3. Put maintainer workflow in [Development](Development.md).
4. Put exact names in [References](References.md).
5. Put system concepts in [Explanations](Explanations.md).
6. Keep each file below [docs/studies](studies) synchronized with its
   template README below [studies_run_templates](../studies_run_templates).
7. Use separator comments before major sections.
8. Add direct links to source files when a reader may need to edit them.
9. Add `[!NOTE]` related-link callouts from concept sections to task recipes.
10. Use [figure visual tokens](References.md#figure-visual-tokens) before
   choosing reusable figure colors, strokes, fills, and typography.
11. Update figure assets when prose changes a diagrammed concept.

> [!NOTE]
> Related links:
> - Use [Markdown formatting rules](#markdown-formatting-rules) for docs layout.
> - Use [link and backlink rules](#link-and-backlink-rules) for related-link callouts.
> - Use [static figure rules](#static-figure-rules) for docs assets.
> - Use [figure visual tokens](References.md#figure-visual-tokens) for the Graphigs-owned figure theme source of truth.

<br>

# 4. Documentation Standards

<!-- ======================================================== -->
## Heading Structure
<!-- ======================================================== -->

Long docs files may use multiple `#` headings. Use them for major document
parts, not only for the file title. The table of contents must mirror the real
structure so a reader can tell which sections are sequences, which sections are
tool groups, and which sections are independent references.

Use this hierarchy:

| Level | Use |
|---|---|
| `#` | Major document parts, for example `First-Time Setup`, `Common Workflows`, or `Failure Model`. |
| `##` | Recipes or concept chapters inside a major part. |
| `###` | Ordered substeps inside a large recipe. |

Avoid a flat file where every section is a `##` peer. A long sequence should be
one recipe with substeps, not a cluster of unrelated recipes.

<br>

<!-- ======================================================== -->
## Markdown Formatting Rules
<!-- ======================================================== -->

- Start every major docs file with a compact table of contents.
- Make the ToC match the heading hierarchy.
- Use the repository terms from [Repository Terms](README.md#repository-terms).
- Use exact technical names: source paths, environment variables, CLI commands,
  config attributes, and file names.
- Avoid generic advice such as "check settings"; say which value to inspect,
  for example `DMW_EXPERIMENTS_STORAGE`, `VIRTUAL_ENV`, or `src/dmw_experiments`.
- Use separator comments before major sections:

```md
<!-- ======================================================== -->
## Section Title
<!-- ======================================================== -->
```

- Use centralized reference links near the bottom of a file when a link is
  reused:

```md
<!-- --- URLs --------------------------------------------------- -->
[`uv`]: https://github.com/astral-sh/uv
```

- Use `<details>` dropdowns for long examples inside procedural docs:

````md
<details><summary> <u> <i> Longer command sequence </i> </u> </summary>
<blockquote>

```bash
just sync
just test
```

</blockquote></details>
````

<br>

<!-- ======================================================== -->
## GitHub Callouts
<!-- ======================================================== -->

Use callouts to mark the job a paragraph does. GitHub renders only the fixed
labels `TIP`, `NOTE`, `IMPORTANT`, `WARNING`, and `CAUTION`; text after the
marker is not rendered as a custom title.

### Callout Syntax

````md
> [!TIP]
> Explanation text goes here.
>
> ```bash
> just sync
> ```
````

### Callout Types

> [!TIP]
> Optional advice that improves speed, clarity, or workflow.

> [!NOTE]
> Helpful context that is not required to complete the task.

> [!IMPORTANT]
> Required prerequisites, environment variables, version constraints, or
> architecture rules.

> [!WARNING]
> Risks, deprecated behavior, high-cost operations, or temporary bugs.

> [!CAUTION]
> Destructive or security-relevant actions.

<br>

<!-- ======================================================== -->
## Link And Backlink Rules
<!-- ======================================================== -->

- Prefer relative links.
- Link to exact chapters when the target section matters.
- Use `[!NOTE]` callouts for return links from concept and reference sections.
- Start one-line related-link callouts with `Related:`.
- Start multi-link related-link callouts with `Related links:`.
- Add a short purpose phrase for every related link so the reader knows why it
  matters.
- Do not use standalone backlink labels in prose.
- Add return links from explanations to the relevant how-to recipes and
  references.
- Add reference links from recipes when exact paths, config keys, or
  environment variables matter.
- Link to source files directly when a user may need to edit the file.
- After moving docs, check file links, image links, and local anchors together.

<br>

<!-- ======================================================== -->
## Static Figure Rules
<!-- ======================================================== -->

Static docs figures live in [assets](assets/). This scaffold starts with one
small static SVG. Put repeatable figure builders in Graphigs and keep only
generated SVG/PNG assets here.

Figure rules:

1. Change the Graphigs figure builder for generated figures.
2. Edit small one-off SVG assets directly only when no builder exists.
3. Keep the canvas transparent.
4. Keep black text on a readable surface fill so GitHub dark mode remains
   legible.
5. Use neutral strokes for outlines and edges.
6. Use [figure visual tokens](References.md#figure-visual-tokens) for the
   Graphigs-owned figure theme source of truth.
7. Embed SVG files in Markdown with a centered table:

```md
| ![Alt text](assets/example.svg) |
|:--:|
| **Fig. N - Figure Title:** Caption sentence. |
```

> [!NOTE]
> Related links:
> - Use [documentation authoring](#documentation-authoring) before expanding
>   the docs structure or adding new figure assets.
> - Use [References: figure visual tokens](References.md#figure-visual-tokens)
>   for the Graphigs-owned figure theme source of truth.

<br>

# 5. Verification And Commit

<!-- ======================================================== -->
## Verification
<!-- ======================================================== -->

Run verification that matches the change.

For Python changes:

```bash
ruff format .
ruff check .
pyright
python -m pytest
```

For docs-only changes:

```bash
git diff --check
rg -n "TO[D]O|FIX[M]E|content[R]eference|oai[c]ite" README.md docs
python -c "import pathlib, xml.etree.ElementTree as ET; [ET.parse(p) for p in pathlib.Path('docs/assets').glob('*.svg')]"
```

> [!NOTE]
> The exact command depends on the local environment. If a command is not
> installed, state that in the final report and verify the closest safe
> surface.

<br>

<!-- ======================================================== -->
## Review Checklist
<!-- ======================================================== -->

Before finishing, review:

- The change is in the existing owner file or directory.
- New names match existing terminology.
- Docs link to exact files and exact chapters.
- Tests cover the behavior changed.
- The diff does not include unrelated formatting churn.
- New comments follow the local comment style.

> [!NOTE]
> Related: use [Development: before editing](#before-editing) before widening
> the scope of a change.

<br>

<!-- ======================================================== -->
## Commit Checklist
<!-- ======================================================== -->

Before committing:

1. Run focused tests for the touched area.
2. Run broader checks when shared behavior changed.
3. Review `git diff --check`.
4. Review `git status --short`.
5. Write a commit message that names the user-facing behavior.

> [!NOTE]
> Related: use [verification](#verification) for the short command recipe.
