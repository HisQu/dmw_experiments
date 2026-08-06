<div align="center">

# DMW experiments

*Part of:*

<a href="https://hisqu.de" target="_blank">
  <img
    src="https://avatars.githubusercontent.com/u/196629600?s=200&v=4"
    width="100px" alt="HisQu logo">
</a>

<br>

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/type%20checked-pyright-blue)](https://microsoft.github.io/pyright/)
[![pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC)](https://docs.pytest.org/)

</div>

`dmw_experiments` owns reproducible experiment execution, supervision, raw
artifacts, analysis, and plots for the DMW technology stack. It is separate
from Haiu so experiment tooling can change without publishing a new Haiu
release.

## Table of contents

1. [DMW experiments](#dmw-experiments)
   1. [Table of contents](#table-of-contents)
   2. [Repository map](#repository-map)
   3. [Install](#install)
   4. [Configure](#configure)
   5. [Run an experiment](#run-an-experiment)
   6. [Inspect and resume](#inspect-and-resume)
   7. [Analyze raw data](#analyze-raw-data)
   8. [Development](#development)

## Repository map

| Path | Contents |
| --- | --- |
| `studies/` | Tracked scientific inputs, run specifications, and release contracts. |
| `src/dmw_experiments/shared/` | Reusable lifecycle, supervision, artifacts, configuration, and plotting code. |
| `src/dmw_experiments/studies/` | Scientific execution and analysis code, separated by study. |
| `output/` | The only default location for generated runs, logs, workbooks, and plots. |
| `tests/` | Offline regression and lifecycle tests. |
| `docs/` | Operational procedures, architecture, study summaries, and exact interfaces. |
| `requirements-runtime.lock` | Plain-pip runtime lock for published and analysis dependencies. |

The active study is
[`studies/haiu_comparison`](studies/haiu_comparison/README.md).
Its full AcademicCloud header--sublemma run contains 480 input units and three
conditions, or 1,440 terminal cells.

The narrative study overview is
[`docs/studies/haiu_comparison.md`](docs/studies/haiu_comparison.md). Update it
with the operational study README whenever the study contract changes.

## Install

Python 3.12 or 3.13 is required. The release lock retrieves the published DMW
1.1.3, OPA 2.1.2, GTA 0.2.4, Haiu 1.8.0, MongoDBAPI 1.0.2, and analysis stack
from their remote package or Git sources. Sibling repository clones are not
required.

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-runtime.lock
.venv/bin/python -m pip install --no-deps -e "."
```

The explicit `--no-deps` is required because NER 0.1.2 and OPA 2.1.2 publish
stale Git requirements that disagree with the DMW 1.1.3 release contract. The
runtime lock already contains every resolved dependency and therefore must be
installed as a complete set.

`uv` is an optional convenience. It applies the same two metadata corrections
and installs the locked runtime plus development tools:

```bash
uv sync --locked --all-groups --python 3.12
```

## Configure

Create one ignored dotenv file below `output/private/`. It must contain the
DMW, MongoDB, Haiu, and AcademicCloud values required by the published stack,
including these experiment-owned names:

```dotenv
DATAMODEL_LOGIN="..."
DATAMODEL_PASSWORD="..."
FAISS_INDEX_PATH="/absolute/path/to/paraphrase-multilingual-mpnet-resolved"
```

Point AppRC at that file and the generated-output root:

```bash
export DMW_EXPERIMENTS_STORAGE="output"
export DMW_EXPERIMENTS_ACADEMICCLOUD_ENV_FILE="output/private/academiccloud.env"
dmw_experiments config doctor
```

> [!CAUTION]
> Never commit the runtime dotenv file. `output/` is ignored, and launch
> commands retain only its path. Credentials are not copied into manifests,
> service arguments, logs, or BABYSIT journals.

`FAISS_INDEX_PATH` is the local NER few-shot example index, not a DMW package
or repository checkout. The lifecycle requires an absolute existing file so
service working directories cannot change which asset NER reads.

## Run an experiment

Validate the complete local and scientific contract without changing storage:

```bash
dmw_experiments validate
```

Start the disposable one-unit smoke:

```bash
dmw_experiments smoke
```

Inspect its three terminal cells. Only then start the independent full run:

```bash
dmw_experiments status \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
dmw_experiments run
```

Each launch creates one self-contained directory at
`output/runs/<run-id>/`. It freezes the run specification before preparing
isolated DMW storage, captures schema-v2 release provenance, and starts the
backend, runner, and watchdog as user-systemd services.

> [!IMPORTANT]
> Context, length, and other terminal model failures are experimental evidence.
> The lifecycle preserves them and does not use recovery-amendment flags.

## Inspect and resume

```bash
dmw_experiments status --spec PATH_TO_ORIGINAL_SPEC
dmw_experiments pause --spec PATH_TO_ORIGINAL_SPEC
dmw_experiments resume --spec PATH_TO_ORIGINAL_SPEC
```

`pause` stops watchdog, runner, and backend in that order. `resume` accepts
only the byte-identical run specification and frozen run artifacts. See the
run-local `logs/BABYSIT-*.md` for readable handoff notes and
`operations/events.jsonl` for machine-readable lifecycle events.

## Analyze raw data

The analysis command rebuilds provider workbooks, an ungraded historian review,
and plots from raw observations:

```bash
dmw_experiments analyze \
  --academiccloud-run output/runs/ACADEMICCLOUD_RUN_ID \
  --lmstudio-run output/runs/LMSTUDIO_RUN_ID
```

Derived files are written below `output/analyses/<timestamp>/`. Human grades
remain separate inputs and are never overwritten. The command replaces only
exporter-owned per-run workbooks by default; pass `--no-overwrite` to require
empty derived-output locations.

## Development

```bash
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/pyright
.venv/bin/pytest
```

Use [the how-to guide](docs/How-To-User-Guides.md) for full operational
recipes, [the architecture explanation](docs/Explanations.md) for ownership
boundaries, and [the reference](docs/References.md) for exact names.
Maintainers use the CI-backed tagged release cycle in
[the development guide](docs/Development.md#github-release-cycle).
