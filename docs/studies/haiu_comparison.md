# Haiu comparison

## Table of contents

1. [Scientific question](#scientific-question)
2. [Experimental unit and conditions](#experimental-unit-and-conditions)
3. [Condition workflows and interpretation](#condition-workflows-and-interpretation)
4. [Run template and storage](#run-template-and-storage)
5. [Configuration and AppRC](#configuration-and-apprc)
6. [Evidence and analysis](#evidence-and-analysis)
7. [Published stack](#published-stack)

## Scientific question

The study tests whether Haiu retrieval gives DMW enough relevant ontology
context to generate ontologies as reliably and effectively as the complete
reference ontology. A standalone Haiu condition provides a system-level
comparison with direct generation that does not use DMW's generated entity
annotations or workflow orchestration.

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

## Condition workflows and interpretation

The two DMW conditions use the published DMW and OPA workflow. Before either
timed ontology condition runs, DMW generates or adopts one entity annotation
for the input unit, accepts it without changing its content, and freezes its
digest. Both DMW conditions must use that exact annotation. Annotation
preparation is therefore neither part of condition duration nor a source of
variation between the two DMW conditions.

The standalone HAIU condition bypasses DMW. It queries Haiu directly with the
frozen raw header--sublemma text, renders a versioned local transcription of
OPA's two-stage prompt structure, and calls the provider through Haiu's LLM
client. Stage 1 produces a modelling plan. Stage 2 remains in the same model
thread and converts that plan into Turtle. The standalone Stage-1 prompt adds
the raw input text and the historian-curated annotation guidelines because it
does not receive a generated DMW entity annotation.

| Aspect | DMW + Full Ontology / DMW + HAIU | Standalone HAIU |
| --- | --- | --- |
| Source representation | Raw text plus the same generated, accepted, and frozen DMW entity annotation. | Raw text plus the general historian annotation guidelines; no generated entity annotation. |
| Ontology context | Complete frozen reference ontology or a Haiu-retrieved subset. | Haiu-retrieved subset. |
| Retrieval integration | DMW delegates retrieval and context construction through OPA. | The experiment runner calls the canonical Haiu workspace directly. |
| Generation path | Published DMW/OPA planner and Turtle-coder stages. | Locally rendered OPA-parity planner and Turtle-coder stages called through Haiu. |
| Workflow services | DMW API, branch and record management, annotation verification, and OPA validation. | No DMW API, annotation generation, or DMW persistence. |
| Completion semantics | DMW reports workflow success after its pipeline checks. | The runner records provider completion; common analysis separately requires syntactically valid Turtle. |
| Primary duration | DMW ontology-stage attempt time; annotation preparation and runner backoff are excluded. | Direct retrieval, prompt construction, and both LLM stages; runner backoff is excluded. |

Within one provider execution, all three conditions use the same frozen input
unit, generation model, historian ontology instructions, output-token cap,
safety margin, and disabled text-interpretation policy. Both retrieval
conditions use the same ontology-ref identity, embedding model, and prepared
canonical index. Each condition nevertheless performs and records its own
retrieval operation. DMW's separate ontology-example retrieval is disabled,
and the standalone path has no separate example-retrieval stage.

The planned pairwise comparisons answer different questions:

- **DMW + Full Ontology versus DMW + HAIU** is the controlled ontology-context
  comparison. The DMW workflow and frozen annotation remain constant; the
  complete ontology is replaced by retrieved context.
- **DMW + HAIU versus standalone HAIU** is a system-level comparison. It
  changes DMW orchestration, generated entity annotations, prompt construction,
  validation, and persistence together. It must not be interpreted as a pure
  retrieval effect.

DMW + Full Ontology versus standalone HAIU is not a planned direct comparison
because both the context scope and the surrounding workflow change.

## Run template and storage

The complete data template lives at
[`studies_run_templates/haiu_comparison/template`](../../studies_run_templates/haiu_comparison/template/README.md).
Python behavior stays in
[`src/dmw_experiments/studies/haiu_comparison`](../../src/dmw_experiments/studies/haiu_comparison).
That package follows the experiment lifecycle: `model`, `preparation`,
`data_collection`, `operations`, `analysis`, and `entrypoints`.
`HaiuComparisonStudy` in `study.py` is the supported Python orchestration
interface.

A copied run has flat provider and condition areas, then groups evidence by
input unit and attempt:

```text
raw-academiccloud/
├── manifest.json
├── provenance/
├── intermediates-shared_annotations/<unit-id>/
│   ├── annotation.json
│   └── attempts.json
├── intermediates-workflow_full_ontology/<unit-id>/
│   ├── checkpoint.json
│   └── attempts/
│       ├── 001-failed/
│       └── 002/
├── intermediates-workflow_rag/<unit-id>/
├── intermediates-haiu_rag_ontologizer/<unit-id>/
├── result-workflow_full_ontology/<unit-id>/
│   ├── result.json
│   └── ontology.ttl
├── result-workflow_rag/<unit-id>/
└── result-haiu_rag_ontologizer/<unit-id>/
```

`raw-lmstudio/` has the same shape. Executions are not nested and do not wait
for one another. `logs/BABYSIT-*.md`, `environment/`, `analysis/`, and `plots/`
remain beside the raw areas in the same run.

Every failed attempt is named `<NNN>-failed`; successful attempts use `<NNN>`.
An attempt owns `metadata.json`, its `prompts/`, its `responses/`, optional
`retrieval/`, and the exact upstream result in `upstream-result.json.gz`.
`result.json` is a small terminal index with content hashes and grouped scalar
measurements. It does not repeat large prompts or responses. Shared NER output
is stored once under `intermediates-shared_annotations/` because both DMW
conditions use the same frozen annotation.

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

Exact upstream JSON, Turtle, provider attempts, prompts, Stage-1 replies,
provider assistant-message sidecars, retrieval sidecars, environment locks,
and run manifests remain in the copied run. Assistant-message sidecars retain
provider-specific fields such as reasoning content when ordinary content is
empty. The active layout does not keep a second YAML rendering of the full
result. Terminal context, length, and other model failures are observations.
Infrastructure interruption resumes only the same frozen contract.
The run manifest records the stable shared-workspace identity; process logs
record whether a launch had to synchronize it.

A stopped schema-v2 run can use `./run.sh migrate-artifacts` before resuming.
The migration first retains every source byte in a hash-inventoried recovery
snapshot, verifies all schema-v3 bundles and exact decoded payloads, then
removes only verified duplicates from the active view. The original frozen
environment lock remains unchanged; a separate migration record proves the
old and new clean experiment-harness commits. A schema-v2 `retry_pending`
checkpoint must reach a terminal result before migration so its provisional
failure cannot be mistaken for an observation.

Strict analysis requires every scheduled cell of every enabled execution to be
terminal. Provider workbooks and plots follow the enabled execution set. The
cross-provider historian review packet is emitted only when both executions
are enabled. Derived files are organized as follows:

| Path | Contents |
| --- | --- |
| `analysis/intermediate/` | Machine-readable normalized data. |
| `analysis/diagnostics/` | Validation and exclusion diagnostics. |
| `analysis/workbooks/` | Timestamped provider, pairwise, and review workbooks. |
| `plots/` | Timestamped figures, manifests, and captions. |

One analysis invocation uses the same timestamp for every derived workbook and
its plot directory. This keeps partial snapshots distinct while raw artifacts
continue to accumulate. A successful suite archives older generated provider
workbooks below `analysis/diagnostics/workbook-archives/`; a failed suite leaves
the last successful active snapshot in place.

## Published stack

| Component | Release |
| --- | --- |
| DMW | 1.1.4 |
| OPA | 2.1.4 |
| GTA | 0.2.5 |
| Haiu | 1.8.1 |
| MongoDBAPI | 1.0.2 |

The template locks remote releases. Local editable checkouts are temporary
development overlays and never part of a tagged experiment release.

> [!NOTE]
> Keep this page and
> [`studies_run_templates/haiu_comparison/README.md`](../../studies_run_templates/haiu_comparison/README.md)
> synchronized when the study or template contract changes.
