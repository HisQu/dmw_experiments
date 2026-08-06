# Repository conventions

## Repo routing
- Warn me if the paths below appear outdated.
- Reuse existing helpers and utilities before adding new helper functions.
- Check these modules first:
  - `dmw_experiments.config`
  - `dmw_experiments.utils`
  - `apprc`
  - `apprc.cli`
- If a helper is broadly reusable, place it in the appropriate shared module.
- Put long-form docs in `docs/`:
  - procedures in `docs/How-To-User-Guides.md`
  - maintainer workflow in `docs/Development.md`
  - exact paths, commands, and public names in `docs/References.md`
  - concepts and architecture in `docs/Explanations.md`
- Put CLI behavior in `dmw_experiments.cli.app`; keep `dmw_experiments.main` as a
  thin public entry point wrapper.
- Check the TODO.md and assess if your task is related to any issues and should be resolved as part of your pass.

## Project rules
- Do not duplicate helpers or re-implement existing utilities without checking first.
- App configuration belongs in `dmw_experiments.config.owners` and should use AppRC `rc.Config` classes with `rc.field(...)` declarations.
- CLI behavior belongs in `dmw_experiments.cli.app`; keep `dmw_experiments.main` as a thin public entry point wrapper.
- Use stdlib `logging` for app-owned logs; AppRC integration should start from `import apprc as rc`.
- Import `dmw_experiments`-owned utility helpers through the facade: `import dmw_experiments.utils as ut`.
- Use explicit `ut.` prefixes for local utilities.
- For facade `__init__.py` files, prefer clean batch re-export imports plus file-level `# ruff: noqa: F401`; do not use redundant `symbol as symbol` aliases solely to satisfy Ruff.
- Update `README.md` or `docs/` if a change affects usage, setup, CLI behavior, public APIs, environment variables, or user-visible workflows.
- Add minimal `__main__` demo code only when it improves discoverability or manual testing.
- If a test needs a lighter setup, add or reuse a dedicated test helper instead of widening production code to `Any`.
- If a boundary is truly dynamic, model that boundary explicitly; do not probe strict domain objects defensively.

## Documentation rules
- Start major docs files with a compact table of contents.
- Use repeated `#` headings for major document parts.
- Use separator comments before major sections.
- Use GitHub callouts consistently.
- Use `[!NOTE]` callouts for related links and return links.
- Start one-line related-link callouts with `Related:`.
- Start multi-link related-link callouts with `Related links:`.
- Do not use standalone backlink labels in prose.
- Update the CHANGELOG.md after each pass
- Update the TODO.md 

## Verification
- Review the diff for duplicate helpers, naming drift, unnecessary abstractions, and regressions.
- Run the project’s relevant lint, type-check, and test commands before considering the task done.

## User Decisions
- Never answer questions on the user's behalf.
- Do not treat recommended options, defaults, timeouts, or auto-resolution as user approval or user preference.
- If a user decision is required, ask and wait for the user’s explicit answer.
