# How-to user guides

## Table of contents

1. [Configure the machine](#configure-the-machine)
2. [Create a run](#create-a-run)
3. [Validate and start](#validate-and-start)
4. [Inspect, pause, and resume](#inspect-pause-and-resume)
5. [Migrate a stopped legacy run](#migrate-a-stopped-legacy-run)
6. [Analyze](#analyze)
7. [Promote a selected run](#promote-a-selected-run)

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

## Migrate a stopped legacy run

Only runs started with the former flat result layout need this operation.
Finish the current provider attempt or stop at another durable checkpoint,
then run:

```bash
./run.sh pause --execution academiccloud
./run.sh migrate-artifacts --execution academiccloud
./run.sh status --execution academiccloud
./run.sh resume --execution academiccloud
```

The migration refuses to start while a selected backend, runner, or watchdog
is active or while a schema-v2 checkpoint still says `retry_pending`. Resume
until that retry chain is terminal before migrating. The migration retains an
exact, hash-inventoried source snapshot below
`environment/artifact-migration-backups/`, writes and verifies the per-unit
bundles, and records the old and new clean harness commits in
`environment/<execution>-artifact-layout-migration.json`. The original
scientific environment lock is not rewritten.

> [!IMPORTANT]
> Do not delete the migration backup during collection. If the command reports
> a partial migration instead of a completed record, inspect the snapshot and
> active paths before retrying or resuming.

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
Each invocation uses one timestamp in the provider overview, masked review,
review sidecar, reveal key, quality-analysis workbook, and plot directory.

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
