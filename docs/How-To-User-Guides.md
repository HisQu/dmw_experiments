# How-to guides

## Table of contents

1. [Prepare a machine](#prepare-a-machine)
2. [Validate without mutation](#validate-without-mutation)
3. [Run the required smoke](#run-the-required-smoke)
4. [Start the full matrix](#start-the-full-matrix)
5. [Pause before a restart](#pause-before-a-restart)
6. [Resume after an interruption](#resume-after-an-interruption)
7. [Hand off babysitting](#hand-off-babysitting)
8. [Regenerate analyses](#regenerate-analyses)

## Prepare a machine

Install the locked Python 3.12 environment:

```bash
uv sync --locked --all-groups --python 3.12
```

Plain `pip` uses the exported release lock and does not need `uv` or sibling
repository clones:

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-runtime.lock
.venv/bin/python -m pip install --no-deps -e "."
```

Do not omit the first command or remove `--no-deps`. The lock is the resolved
runtime contract; ordinary dependency resolution sees incompatible legacy
MongoDBAPI and GTA URLs in the published OPA and NER metadata.

Create `output/private/academiccloud.env`. Merge every runtime variable needed
by the published DMW application, MongoDBAPI, Haiu, and AcademicCloud into this
single ignored file. Add `DATAMODEL_LOGIN` and `DATAMODEL_PASSWORD` for DMW API
authentication. Set `FAISS_INDEX_PATH` to the absolute path of the local NER
few-shot example index; do not leave the old DMW-relative value in place.

```bash
export DMW_EXPERIMENTS_STORAGE="output"
export DMW_EXPERIMENTS_ACADEMICCLOUD_ENV_FILE="output/private/academiccloud.env"
dmw_experiments config doctor
```

> [!IMPORTANT]
> The smoke and full specs have different run IDs, DMW branches, raw
> collections, annotation collections, and ontology collections. Never reuse a
> smoke identity for the full matrix.

## Validate without mutation

```bash
dmw_experiments validate \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
```

Validation checks the schema-v2 contract, smoke/full isolation, required
inputs, interpreter, required runtime keys, absolute NER index, and ignored
runtime file. It does not connect to MongoDB, start DMW, or call a model.

## Run the required smoke

First confirm no AcademicCloud experiment is active:

```bash
systemctl --user list-units '*academiccloud*.service'
```

Then run:

```bash
dmw_experiments smoke
```

The command performs these actions in order:

1. Freezes `run_spec.json` inside the run directory.
2. Creates or verifies the isolated DMW branch and collections.
3. Clones ignored release-evidence checkouts from the four pinned tags.
4. Captures `provenance/environment_lock.json` with schema version 2.
5. Starts backend, runner, and watchdog as user-systemd services.
6. Records every intervention in the run-local BABYSIT journal.

Use `dmw_experiments status --spec ...smoke.json` until all three cells are
terminal. A terminal model failure remains a smoke result; it is not silently
retried as an amendment.

## Start the full matrix

After reviewing the smoke, start the fresh 480-unit environment:

```bash
dmw_experiments run
```

The full run uses `--limit 0` and schedules all three conditions. The command
refuses a smoke spec and refuses to start while another AcademicCloud unit is
active.

## Pause before a restart

```bash
dmw_experiments pause \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-full.json
```

The command stops the watchdog, sends SIGINT to the runner, waits for an
orderly checkpoint, and then stops runner and backend. Do not delete raw or
attempt files.

## Resume after an interruption

```bash
dmw_experiments resume \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-full.json
```

Resume requires the byte-identical specification, its SHA-256 sidecar, DMW
input manifest, schema-v2 environment lock, and immutable runner manifest. It
passes only `--resume`; recovery-amendment selectors are deliberately absent.

## Hand off babysitting

Give the next operator these paths from one run directory:

- `run_spec.json` defines exactly what may resume.
- `operations/services.json` names the owned service units.
- `operations/events.jsonl` lists structured lifecycle events.
- `logs/BABYSIT-*.md` contains readable checkpoints and interventions.
- `logs/backend.log`, `logs/runner.log`, and `logs/watchdog.log` contain process
  output.
- `raw/`, `attempts/`, and `annotation_attempts/` are authoritative progress.

Run `dmw_experiments status --spec PATH` instead of inferring completion from
log text. Strict analysis can proceed only when every scheduled cell has a raw
record and no cell is `retry_pending`.

## Regenerate analyses

```bash
dmw_experiments analyze \
  --academiccloud-run output/runs/ACADEMICCLOUD_RUN_ID \
  --lmstudio-run output/runs/LMSTUDIO_RUN_ID
```

For a diagnostic snapshot of an incomplete source matrix, add
`--allow-partial`. For graded plots, pass both
`--quality-review-workbook PATH` and `--quality-reveal-key PATH`.
Exporter-owned per-run workbooks are regenerated by default. Use
`--no-overwrite` when an existing derived file should stop the command.

> [!NOTE]
> Analysis files are derived. Regenerate them from raw data; do not hand-edit
> generated workbooks or plots.
