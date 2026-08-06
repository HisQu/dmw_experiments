# How-to user guides

## Table of contents

1. [Configure the machine](#configure-the-machine)
2. [Create a run](#create-a-run)
3. [Validate and start](#validate-and-start)
4. [Inspect, pause, and resume](#inspect-pause-and-resume)
5. [Analyze](#analyze)
6. [Promote a selected run](#promote-a-selected-run)

## Configure the machine

Install the locked repository environment, then initialize AppRC:

```bash
uv sync --locked --all-groups
dmw_experiments config app init
dmw_experiments config edit
```

Put `DATAMODEL_LOGIN`, `DATAMODEL_PASSWORD`, `MONGO_URI`, `JWT_SECRET`,
`GITHUB_TOKEN`, provider keys, and the absolute `FAISS_INDEX_PATH` in AppRC's
app-wide environment. Do not put them in a run directory.

## Create a run

```bash
dmw_experiments new-run \
  --study haiu_comparison \
  --run-id RUN_ID \
  --mode full \
  --execution academiccloud \
  --execution lmstudio
```

Use `--mode smoke` for a one-unit run. Smoke and full runs are copied into
different ignored roots and receive different storage identities. You may
also copy the complete tracked template manually, but the destination basename
must equal `run_id` in `run.toml`.

Before launch:

1. Edit the copied `README.md` with the concrete purpose and changes.
2. Review every field in `run.toml`.
3. Review `run.env` and both provider override files.
4. Read `run.AGENT.md` before delegating babysitting.

## Validate and start

From the copied run directory:

```bash
dmw_experiments config doctor
./run.sh validate
./run.sh start
```

Select one execution without stopping the other:

```bash
dmw_experiments --storage "$PWD" --skip-dotenv-layers \
  start --run-dir "$PWD" --execution academiccloud
```

Validation checks the TOML shape, exhaustive environment inventory, AppRC
credential sources, runtime assets, provider profiles, input population, and
storage isolation before launch changes external state.

## Inspect, pause, and resume

```bash
./run.sh status
./run.sh pause
./run.sh resume
```

Provider services and journals are independent. A provider interruption does
not block the other provider. `pause` stops watchdog, runner, then backend.
`resume` requires the original frozen `run.toml` and first-launch evidence.

> [!IMPORTANT]
> A terminal model failure is a datapoint. Do not change settings or use a
> recovery amendment unless the user separately approves a scientific
> amendment.

## Analyze

```bash
./run.sh analyze
```

Strict analysis requires all enabled provider cells to be terminal. For an
interim view:

```bash
dmw_experiments --storage "$PWD" --skip-dotenv-layers \
  analyze --run-dir "$PWD" --allow-partial
```

Raw evidence is never overwritten. Analysis owns only its derived files.
Human-evaluated workbooks remain explicit inputs paired with a reveal key.

## Promote a selected run

Runs remain wholly ignored until the user selects one. Prepare the selected
run in place:

```bash
dmw_experiments prepare-promotion --run-dir "$PWD"
```

This validates terminal counts and creates the matching experiment wheel and
source archive under `locks/dist/`. Review the whole run, then copy it to
`studies_runs/haiu_comparison/git_tracked/<run-id>/` and commit that promotion
separately. Use `--allow-partial` only when the incomplete dataset is itself
the explicitly intended publication artifact.
