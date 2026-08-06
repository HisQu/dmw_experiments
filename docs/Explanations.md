# Architecture

## Table of contents

1. [Ownership model](#ownership-model)
2. [Run lifecycle](#run-lifecycle)
3. [Output model](#output-model)
4. [Dependency model](#dependency-model)
5. [Failure model](#failure-model)

## Ownership model

The repository has one public command, `dmw_experiments`, and two top-level
data owners:

- `studies/` contains tracked facts: frozen inputs, run specs, and stack locks.
- `output/` contains generated facts: runs, logs, provenance snapshots,
  analyses, and temporary release checkouts.

Package responsibilities are narrow:

| Package | Responsibility |
| --- | --- |
| `shared.artifacts` | Durable run-directory layout and operational journals. |
| `shared.execution` | Published-stack checkout and validation support. |
| `shared.supervision` | user-systemd process ownership and stall detection. |
| `shared.analysis.plotting` | Plot formatting frozen with this repository. |
| `studies.haiu_comparison` | Scientific conditions, runner, exports, and study-specific analysis. |
| `studies.haiu_comparison.operations` | Validate, launch, pause, resume, and report this study's status. |

The root `cli` package is a thin application boundary. Reusable behavior must
not accumulate there. Shared modules must not import a concrete study; the CLI
and lifecycle select a study explicitly at the orchestration boundary.

The DMW, OPA, GTA, and Haiu repositories do not own this harness. Their
published packages are measured dependencies.

## Run lifecycle

One run moves through a small state sequence:

```text
tracked spec
    -> frozen workspace
    -> isolated DMW storage
    -> schema-v2 environment lock
    -> backend + runner + watchdog
    -> terminal matrix
    -> derived analysis
```

The runner checkpoints each completed condition under `raw/`. A system restart
does not create a new run; `resume` verifies the original spec and immutable
artifacts, then reconciles the same matrix.

The watchdog observes durable progress, not console output. It waits four
hours by default because one condition may use three one-hour provider
attempts. On a real stall it interrupts only the runner so the same run can
resume.

## Output model

Every run is self-contained:

```text
output/runs/<run-id>/
├── run_spec.json
├── operations/
├── logs/
├── provenance/
├── raw/
├── attempts/
├── annotation_attempts/
└── summaries/
```

Historical runs may retain the older `summaries/run_manifest.json` location;
new lifecycle metadata does not rewrite scientific manifests. Cross-run
workbooks and figures belong under `output/analyses/<analysis-id>/`.

## Dependency model

All execution and analysis dependencies are core project dependencies. The
DMW stack uses exact published remote tags and does not require local
repository clones. `uv.lock`, `pylock.toml`, and
`requirements-runtime.lock` retain the resolved release environment.

`[tool.uv].override-dependencies` contains only two compatibility corrections:
OPA 2.1.2 and NER 0.1.2 publish older MongoDBAPI and GTA URLs than DMW 1.1.3.
The override selects the DMW publication contract's MongoDBAPI 1.0.2 and GTA
0.2.4 remote tags. It is not a local editable-source mechanism.

Commented `[tool.uv.sources]` examples are temporary developer conveniences.
They must remain disabled in a tagged experiment release.

Plain pip cannot express dependency overrides. It installs the complete
exported `requirements-runtime.lock` with `--no-deps`, then installs this
project the same way. This bypasses only the stale transitive URL declarations;
it does not select different package versions.

## Failure model

The lifecycle distinguishes three categories:

- A terminal model result is data, including context or length exhaustion. It
  stays in `raw/` and does not make the service restart.
- A retry-pending provider attempt is provisional. It prevents strict analysis
  until the runner reaches a terminal result.
- An infrastructure interruption has no terminal row for the active cell. The
  same run may resume with identical settings.

Recovery-amendment flags are intentionally absent from the header--sublemma
lifecycle. A code patch or changed scientific setting requires an explicit
decision, not an automatic retry.
