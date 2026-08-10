# Haiu comparison

## Table of contents

1. [Scientific question](#scientific-question)
2. [Experimental unit and conditions](#experimental-unit-and-conditions)
3. [Run template and storage](#run-template-and-storage)
4. [Configuration and AppRC](#configuration-and-apprc)
5. [Evidence and analysis](#evidence-and-analysis)
6. [Published stack](#published-stack)

## Scientific question

The study tests whether Haiu retrieval gives DMW enough relevant ontology
context to generate ontologies as reliably and effectively as the complete
reference ontology. A standalone Haiu condition separates the effect of
retrieval from the DMW workflow.

## Experimental unit and conditions

The frozen population contains 480 header--sublemma units. Each unit contains
one header, one ordered sublemma, and source-regest lineage. It is not the
whole multi-sublemma regest as one generation target.

The catalogue removes obsolete TUSTEP layout controls (`&w&w`, `&w&`, `&w`,
and `&y`) before freezing the experimental text. Whitespace is collapsed only
in a field that contains one of these controls; every other field remains
byte-for-byte identical to the verified source snapshot. The catalogue records
the rule, affected counts, affected source IDs, and both source and normalized
content hashes. The current population changes 44 input units from nine source
regesta, all in headers; no sublemma is changed.

| Internal condition | Display condition | Measured path |
| --- | --- | --- |
| `workflow_full_ontology` | DMW + Full Ontology | DMW receives the complete reference ontology. |
| `workflow_rag` | DMW + HAIU | DMW receives Haiu-retrieved ontology context. |
| `haiu_rag_ontologizer` | HAIU | Direct generation receives Haiu-retrieved context. |

Each enabled provider schedules all 1,440 cells. Pairwise analysis uses DMW
versus DMW + HAIU and DMW + HAIU versus HAIU.

Both retrieval conditions use the ontology ref declared in
`INPUTS/retrieval_workspace.json`. Before the first timed condition, the
runner checks this ref against the frozen Turtle, DMW import manifest,
embedding model, and ontology repository setting. It then verifies or builds
the shared branch-aware canonical index. This preparation is outside condition
duration, so randomized condition order does not assign one-time indexing to
one condition.

`ontology_example_limit = 0` disables DMW's separate whole-regest example
retrieval for this study. The published FAISS example index is keyed by numeric
complete-regest IDs and does not define queries for synthetic header--sublemma
units. Sending a nonzero limit would therefore declare an example that OPA
cannot retrieve. The ontology-context condition remains the only intended
context difference between DMW + Full Ontology and DMW + HAIU.

## Run template and storage

The complete data template lives at
[`studies_run_templates/haiu_comparison/template`](../../studies_run_templates/haiu_comparison/template/README.md).
Python behavior stays in
[`src/dmw_experiments/studies/haiu_comparison`](../../src/dmw_experiments/studies/haiu_comparison).
That package follows the experiment lifecycle: `model`, `preparation`,
`data_collection`, `operations`, `analysis`, and `entrypoints`.
`HaiuComparisonStudy` in `study.py` is the supported Python orchestration
interface.

A copied run has flat provider areas:

```text
raw-academiccloud/
├── intermediates-workflow_full_ontology/
├── intermediates-workflow_rag/
├── intermediates-haiu_rag_ontologizer/
├── result-workflow_full_ontology/
├── result-workflow_rag/
└── result-haiu_rag_ontologizer/
```

`raw-lmstudio/` has the same shape. Executions are not nested and do not wait
for one another. `logs/BABYSIT-*.md`, `environment/`, `analysis/`, and `plots/`
remain beside the raw areas in the same run.

Full runs belong under `studies_runs/haiu_comparison/`; smoke runs belong
under `studies_runs_smoketests/haiu_comparison/`. Both are wholly ignored.
Only a user-selected completed run is copied below
`studies_runs/haiu_comparison/git_tracked/`.

## Configuration and AppRC

`run.toml` is the typed scientific and storage contract. `run.env` is the
exhaustive shared non-secret runtime contract. Provider files contain only
execution-specific overrides.

Each run is selected as one AppRC storage and uses `run.env` as its
storage-local environment. Real credentials, including `GITHUB_TOKEN`, and the
machine-local NER index path belong to AppRC's app-wide environment. Launch
evidence records redacted setting origins and derived storage identities, not
credential values.

Smoke and full runs require different run directories, DMW branches, raw
collections, annotation collections, ontology collections, and Haiu storage.

## Evidence and analysis

Result JSON, YAML, Turtle, provider attempts, prompts, Stage-1 replies,
retrieval sidecars, environment locks, and run manifests remain in the copied
run. Terminal context, length, and other model failures are observations.
Infrastructure interruption resumes only the same frozen contract.
The run manifest records the stable shared-workspace identity; process logs
record whether a launch had to synchronize it.

Strict analysis requires every scheduled cell of every enabled execution to be
terminal. Provider workbooks and plots follow the enabled execution set. The
cross-provider historian review packet is emitted only when both executions
are enabled. Derived files are organized as follows:

| Path | Contents |
| --- | --- |
| `analysis/intermediate/` | Machine-readable normalized data. |
| `analysis/diagnostics/` | Validation and exclusion diagnostics. |
| `analysis/workbooks/` | Provider, pairwise, and review workbooks. |
| `plots/` | Timestamped figures, manifests, and captions. |

## Published stack

| Component | Release |
| --- | --- |
| DMW | 1.1.3 |
| OPA | 2.1.2 |
| GTA | 0.2.4 |
| Haiu | 1.8.0 |
| MongoDBAPI | 1.0.2 |

The template locks remote releases. Local editable checkouts are temporary
development overlays and never part of a tagged experiment release.

> [!NOTE]
> Keep this page and
> [`studies_run_templates/haiu_comparison/README.md`](../../studies_run_templates/haiu_comparison/README.md)
> synchronized when the study or template contract changes.
