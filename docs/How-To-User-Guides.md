<!-- ======================================================== -->
## Table Of Contents
<!-- ======================================================== -->

1. [How-To User Guides](#1-how-to-user-guides)
   1. [Recipe Map](#recipe-map)
2. [First-Time Setup](#2-first-time-setup)
   1. [Install The Package](#install-the-package)
   2. [Run The First Command](#run-the-first-command)
3. [Common Workflows](#3-common-workflows)
   1. [Sync Dependencies](#sync-dependencies)
   2. [Run Tests](#run-tests)
   3. [Inspect The Project](#inspect-the-project)
4. [Troubleshooting](#4-troubleshooting)
   1. [Environment Problems](#environment-problems)
   2. [Command Problems](#command-problems)

<br>

# 1. How-To User Guides

<!-- ======================================================== -->
## Recipe Map
<!-- ======================================================== -->

Use this file when you want commands in order. Use
[References](References.md) when you need exact names and
[Explanations](Explanations.md) when you need the system model.

> [!NOTE]
> Related: use [documentation standards](Development.md#4-documentation-standards)
> when adding new recipes so headings, callouts, and links stay consistent.

<br>

# 2. First-Time Setup

<!-- ======================================================== -->
## Install The Package
<!-- ======================================================== -->

Use this recipe from the project root.

1. Create or activate a Python environment.
2. Install the package for runtime use:

```bash
python -m pip install -e "."
```

3. Install the maintainer tools when you plan to edit the project:

```bash
python -m pip install -e "." --group dev
```

4. If you use `uv`, sync the locked maintainer environment:

```bash
just sync
```

> [!NOTE]
> Related: use [dependency surfaces](References.md#dependency-surfaces) for the
> difference between runtime dependencies, optional extras, and dependency
> groups.

<br>

<!-- ======================================================== -->
## Run The First Command
<!-- ======================================================== -->

Show the command tree through the console script:

```bash
dmw_experiments --help
```

The module entry point should show the same command tree:

```bash
python -m dmw_experiments --help
```

Run the starter commands:

```bash
dmw_experiments version
dmw_experiments diagnose
dmw_experiments diagnose --json
```

Initialize AppRC storage before commands that need local runtime state:

```bash
dmw_experiments config setup --yes --storage-root ./local-storage
export DMW_EXPERIMENTS_STORAGE="$(pwd)/local-storage"
dmw_experiments config doctor
dmw_experiments config show --json
```

> [!NOTE]
> Related: use [public interfaces](References.md#public-interfaces) for the
> commands and import paths users can rely on.

<br>

# 3. Common Workflows

<!-- ======================================================== -->
## Sync Dependencies
<!-- ======================================================== -->

Use `just sync` to install the full maintainer environment from `uv.lock`:

```bash
just sync
```

Use plain `pip` when you only need the package and do not want `uv`:

```bash
python -m pip install -e "."
```

> [!NOTE]
> Related: use [configuration and dependency model](Explanations.md#configuration-and-dependency-model)
> for why runtime installs and maintainer installs are documented separately.

<br>

<!-- ======================================================== -->
## Run Tests
<!-- ======================================================== -->

Run the focused tests first:

```bash
python -m pytest tests
```

Run the quality tools before finishing a code change:

```bash
ruff format .
ruff check .
pyright
python -m pytest
```

> [!NOTE]
> Related: use [Development: verification](Development.md#verification) for
> the maintainer checklist before a commit.

<br>

<!-- ======================================================== -->
## Inspect The Project
<!-- ======================================================== -->

Use these commands when you need to understand the current shape:

```bash
rg --files
git status --short
dmw_experiments diagnose
dmw_experiments config doctor
python -m dmw_experiments --help
```

When a command fails, copy the exact command, current directory, exit code, and
stderr into the issue or debugging note.

> [!NOTE]
> Related links:
> - Use [project paths](References.md#project-paths) for the main source and docs locations.
> - Use [system model](Explanations.md#system-model) for the package and tooling boundaries.

<br>

# 4. Troubleshooting

<!-- ======================================================== -->
## Environment Problems
<!-- ======================================================== -->

Check the active Python and environment first:

```bash
python --version
python -c "import sys; print(sys.executable)"
python -c "import dmw_experiments; print(dmw_experiments.__file__)"
```

If the package imports from an unexpected location, reinstall it from the
project root.

> [!NOTE]
> Related: use [failure model](Explanations.md#failure-model) for the normal
> order of checks when a command behaves differently across machines.

<br>

<!-- ======================================================== -->
## Command Problems
<!-- ======================================================== -->

When a `just` recipe fails:

1. Run `just --list`.
2. Run the underlying command manually.
3. Check whether the virtual environment is active.
4. Check whether the command exists in `.venv/bin`.

```bash
just --list
ls .venv/bin
```

> [!NOTE]
> Related: use [command reference](References.md#command-reference) for the
> expected commands and their owners.
