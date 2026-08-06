<!-- ======================================================== -->
## Table Of Contents
<!-- ======================================================== -->

1. [References](#1-references)
2. [Project Reference](#2-project-reference)
   1. [Project Paths](#project-paths)
   2. [Command Reference](#command-reference)
   3. [Dependency Surfaces](#dependency-surfaces)
   4. [Environment Variables](#environment-variables)
   5. [Configuration Files](#configuration-files)
   6. [Public Interfaces](#public-interfaces)
   7. [Figure Visual Tokens](#figure-visual-tokens)

<br>

# 1. References

Use this file when you need an exact path, command, environment variable, or
public name. Use [How-To User Guides](How-To-User-Guides.md) for procedure and
[Explanations](Explanations.md) for concepts.

<br>

# 2. Project Reference

<!-- ======================================================== -->
## Project Paths
<!-- ======================================================== -->

Core paths:

| Path | Role |
|---|---|
| [README.md](../README.md) | Short setup entry point. |
| [CHANGELOG.md](../CHANGELOG.md) | Release history and unreleased change notes. |
| [TODO.md](../TODO.md) | Tracked parking lot for actionable follow-up work. |
| [AGENTS.md](../AGENTS.md) | Local coding and documentation guidance for agents. |
| [pyproject.toml](../pyproject.toml) | Package metadata, dependencies, and tool configuration. |
| [justfile](../justfile) | Development commands. |
| [src/dmw_experiments](../src/dmw_experiments) | Runtime package source. |
| [tests](../tests) | Test suite. |
| [examples](../examples) | Small user-facing examples. |
| [assets](../assets) | Project assets. |
| [docs](.) | Long-form project documentation. |

> [!NOTE]
> Related: use [Development: repository routing](Development.md#repository-routing)
> before adding files or moving behavior between directories.

<br>

<!-- ======================================================== -->
## Command Reference
<!-- ======================================================== -->

Common commands:

| Command | Role |
|---|---|
| `just --list` | Show available development recipes. |
| `just sync` | Sync the full maintainer environment from `uv.lock`. |
| `python -m pip install -e "."` | Install runtime package dependencies without `uv`. |
| `python -m pip install -e "." --group dev` | Install maintainer tools without `uv`. |
| `dmw_experiments --help` | Show the console command tree. |
| `dmw_experiments version` | Print the installed package version. |
| `dmw_experiments diagnose` | Print local package and Python diagnostics. |
| `dmw_experiments config setup --yes --storage-root STORAGE_ROOT` | Create first-run single-storage AppRC setup. |
| `dmw_experiments config doctor` | Check AppRC storage setup. |
| `dmw_experiments config storage add NAME STORAGE_ROOT --yes` | Register a named storage root in the AppRC index. |
| `dmw_experiments config storage list` | List AppRC named-storage registrations. |
| `dmw_experiments config storage remove NAME` | Remove an AppRC named-storage registration. |
| `dmw_experiments config show --json` | Show resolved runtime config metadata. |
| `dmw_experiments config edit` | Open the AppRC Textual config editor. |
| `python -m dmw_experiments --help` | Smoke-test the module entry point. |
| `ruff format .` | Format Python files. |
| `ruff check .` | Lint Python files. |
| `pyright` | Type-check Python files. |
| `python -m pytest` | Run the test suite. |

> [!NOTE]
> Related: use [How-To User Guides: run tests](How-To-User-Guides.md#run-tests)
> for the command sequence.

<br>

<!-- ======================================================== -->
## Dependency Surfaces
<!-- ======================================================== -->

Dependency locations:

| Surface | File Section | Use |
|---|---|---|
| Runtime dependencies | `[project].dependencies` | Packages required by normal users. |
| Optional feature extras | `[project.optional-dependencies]` | Published extras for optional runtime features. |
| Dependency groups | `[dependency-groups]` | Local maintainer tools such as tests, linting, typing, docs, and profiling. |
| Lock file | `uv.lock` | Reproducible `uv` installs. |

> [!NOTE]
> Related: use [dependency model](Explanations.md#dependency-model) for why
> optional runtime features and maintainer-only tools stay separate.

<br>

<!-- ======================================================== -->
## Environment Variables
<!-- ======================================================== -->

Common environment variables:

| Name | Role |
|---|---|
| `DMW_EXPERIMENTS_STORAGE` | Active storage selector, usually a storage-root path in single-storage mode. |
| `DMW_EXPERIMENTS_APPRC_TOML` | Optional AppRC TOML index file for named multi-storage workflows. |
| `DMW_EXPERIMENTS_MESSAGE` | Starter example setting loaded from `config/.env.shared` or local storage. |
| `VIRTUAL_ENV` | Active virtual environment path. |
| `PYTHONPATH` | Import-path override for local smoke tests. Prefer editable installs for normal development. |
| `UV_PROJECT_ENVIRONMENT` | Optional `uv` virtual environment path override. |

> [!NOTE]
> Related: use [How-To User Guides: environment problems](How-To-User-Guides.md#environment-problems)
> for the first checks when imports resolve from the wrong location.

<br>

<!-- ======================================================== -->
## Configuration Files
<!-- ======================================================== -->

Important config files:

| File | Role |
|---|---|
| [pyproject.toml](../pyproject.toml) | Python packaging, dependencies, and tool settings. |
| [src/dmw_experiments/config/.env.shared](../src/dmw_experiments/config/.env.shared) | Packaged AppRC defaults loaded before local and shell overrides. |
| `DMW_EXPERIMENTS_APPRC_TOML -> <path>/dmw_experiments.apprc.toml` | Optional AppRC TOML index file for named multi-storage roots. |
| `<storage-root>/.env.apprc-storage` | Storage-local AppRC overrides written by `dmw_experiments config set --scope storage`. |
| [.envrc](../.envrc) | `direnv` integration. |
| [.gitignore](../.gitignore) | Local and generated files excluded from Git. |
| [.github/workflows_inactive](../.github/workflows_inactive) | Inactive starter CI workflows. |

> [!NOTE]
> Related: use [configuration model](Explanations.md#configuration-model) for
> how local settings, environment variables, and package defaults should stay
> understandable.

<br>

<!-- ======================================================== -->
## Public Interfaces
<!-- ======================================================== -->

Document public surfaces here as the project grows:

| Surface | Current Name | Stability |
|---|---|---|
| Package import | `dmw_experiments` | Public once README examples use it. |
| Console script | `dmw_experiments` | Public command declared in `pyproject.toml`. |
| Module entrypoint | `python -m dmw_experiments` | Public module execution path. |
| CLI app owner | `dmw_experiments.cli.app` | Command tree implementation owner. |
| Entrypoint wrapper | `dmw_experiments.main` | Thin wrapper for package metadata entry points. |
| Config env declarations | `dmw_experiments.config.owners` | App-owned AppRC `rc.Config` field inventory. |
| Config facade | `dmw_experiments.config.APP_RC` | Public AppRC facade used by CLI bootstrap and config commands. |

> [!NOTE]
> Related: use [How-To User Guides: run the first command](How-To-User-Guides.md#run-the-first-command)
> for the first user-facing smoke test.

<br>

<!-- ======================================================== -->
## Figure Visual Tokens
<!-- ======================================================== -->

Graphigs owns the figure theme, token names, and rendered color swatches. Keep
figure captions and generated asset names stable here, but do not duplicate
rendered theme swatches in this repository.

> [!NOTE]
> Related links:
> - Use [Graphigs Theme](https://github.com/markur4/graphigs/blob/main/docs/Theme.md)
>   for current figure token values and swatches.
> - Use [static figure rules](Development.md#static-figure-rules) before adding docs figures.
> - Use [documentation authoring](Development.md#documentation-authoring) before changing docs structure or figure assets.
