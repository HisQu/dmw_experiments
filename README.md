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

`dmw_experiments` owns reproducible execution, supervision, raw evidence,
analysis, and plots for DMW studies. One copied run directory contains
everything needed to start, resume, inspect, analyze, and publish that run.

## Table of contents

1. [Repository map](#repository-map)
2. [Install](#install)
3. [Configure AppRC](#configure-apprc)
4. [Create and operate a run](#create-and-operate-a-run)
5. [Analyze and promote](#analyze-and-promote)
6. [Python API and study package](#python-api-and-study-package)
7. [Development and releases](#development-and-releases)

## Repository map

| Path | Contents |
| --- | --- |
| `studies_run_templates/` | Complete Git-tracked data templates; no Python code. |
| `studies_runs/` | Ignored full runs and the explicit `git_tracked/` promotion area. |
| `studies_runs_smoketests/` | Fully ignored disposable smoke runs. |
| `src/dmw_experiments/shared/` | Reusable configuration, supervision, artifacts, and plotting code. |
| `src/dmw_experiments/studies/` | Study-specific execution and analysis code. |
| `docs/studies/` | Scientific and operational study summaries. |
| `tests/` | Offline contract and regression tests. |

The Haiu comparison template is
[`studies_run_templates/haiu_comparison/template`](studies_run_templates/haiu_comparison/template/README.md).
It contains one obvious entry point (`run.sh` or `run.ps1`) and one obvious
output boundary: the copied run directory itself.

## Install

Python 3.12 or 3.13 is supported. DMW, OPA, GTA, Haiu, MongoDBAPI, and the
analysis packages are core dependencies pinned by the release locks.
Neighboring source checkouts are not required.

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-runtime.lock
.venv/bin/python -m pip install --no-deps -e .
```

`uv sync --locked --all-groups` is an optional convenience. Temporary local
editable sources may be supplied to `uv` during development, but tagged
releases retain only the remote version pins in `pyproject.toml`.

## Configure AppRC

Each copied run is one AppRC storage. Its storage-local file is `run.env`.
That tracked-with-the-run file names every relevant setting, but assigns no
real credential. Put real credentials, including `GITHUB_TOKEN`, and the
machine-local `FAISS_INDEX_PATH` in AppRC's app-wide environment:

```bash
dmw_experiments config app init
dmw_experiments config edit
```

> [!CAUTION]
> Never put credentials in a run, command line, log, BABYSIT journal, or Git
> commit. `run.env` contains commented secret names so omissions are visible.

Provider files such as `run.academiccloud.env` and `run.lmstudio.env` contain
only small, explicit execution overrides. Lifecycle launch validates the
effective AppRC sources before storage or services are changed.

## Create and operate a run

Create a disposable smoke or ignored full run from the same template:

```bash
dmw_experiments new-run \
  --study haiu_comparison \
  --run-id header-sublemma-smoke-20260807 \
  --mode smoke \
  --execution academiccloud

dmw_experiments new-run \
  --study haiu_comparison \
  --run-id header-sublemma-full-20260807 \
  --mode full \
  --execution academiccloud \
  --execution lmstudio
```

Edit the copied `README.md`, `run.toml`, and environment files before launch.
Then use its self-contained scripts:

```bash
cd studies_runs/haiu_comparison/header-sublemma-full-20260807
./run.sh validate
./run.sh start
./run.sh status
./run.sh pause
./run.sh resume
```

AcademicCloud and LM Studio have independent backend, runner, watchdog,
storage, logs, and BABYSIT journals. Either may advance without waiting for
the other. A resume reuses the exact frozen `run.toml`; terminal model
failures, including context exhaustion, remain evidence.

## Analyze and promote

```bash
./run.sh analyze
```

Analysis reads `raw-academiccloud/` and `raw-lmstudio/`, writes intermediates
below `analysis/`, workbooks below `analysis/workbooks/`, and timestamped
figures below `plots/`. Use `--allow-partial` only for an explicitly
diagnostic export.

Runs remain wholly ignored until the user chooses one for publication. To
prepare reproducibility artifacts without moving it:

```bash
dmw_experiments prepare-promotion --run-dir "$PWD"
```

Review the run, then copy it to
`studies_runs/haiu_comparison/git_tracked/<run-id>/` in a separate commit.
`locks/dist/` contains the matching experiment wheel and source archive.

## Python API and study package

`HaiuComparisonStudy` is the supported Python entry point. It exposes the same
`new_run`, `validate`, `start`, `status`, `pause`, `resume`, `analyze`, and
`prepare_promotion` lifecycle used by the CLI:

```python
from dmw_experiments.shared.config import AppRuntimeConfig
from dmw_experiments.studies.haiu_comparison import HaiuComparisonStudy

study = HaiuComparisonStudy(AppRuntimeConfig())
status = study.status(run_dir)
```

Study internals are organized by lifecycle: `model`, `preparation`,
`data_collection`, `operations`, `analysis`, and `entrypoints`. External code
should not import those implementations when the façade provides the required
operation.

## Development and releases

```bash
.venv/bin/ruff format .
.venv/bin/ruff check .
.venv/bin/pyright
.venv/bin/pytest
```

Use [the how-to guide](docs/How-To-User-Guides.md) for operator procedures,
[the Haiu comparison summary](docs/studies/haiu_comparison.md) for the study
contract, and [the development guide](docs/Development.md#github-release-cycle)
for the CI-backed GitHub Release cycle.
