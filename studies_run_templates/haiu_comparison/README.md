# Haiu comparison run template

## Table of contents

1. [Purpose](#purpose)
2. [Template contract](#template-contract)
3. [Configuration contract](#configuration-contract)
4. [Directory contract](#directory-contract)
5. [Lessons learned](#lessons-learned)

## Purpose

The `template/` directory is the complete source for a copied Haiu comparison
run. It contains the 480 header--sublemma inputs, published stack locks,
explicit runtime configuration, provider output directories, analysis
destinations, and operator scripts.

## Template contract

- Keep all Python logic in `src/dmw_experiments/studies/haiu_comparison/`.
- Keep that Python package organized by lifecycle: `model`, `preparation`,
  `data_collection`, `operations`, `analysis`, and `entrypoints`. Route CLI and
  external Python orchestration through `HaiuComparisonStudy` in `study.py`.
- Keep the three condition names identical to `run.toml`.
- Keep `run.env` exhaustive and keep real credentials in AppRC's app-wide
  configuration.
- Record pending template work in the repository-root `TODO.md`; do not create
  another template todo file.
- Update this README when a run exposes a lesson that should affect later
  copies.

## Configuration contract

`run.toml` owns the input population, conditions, output budgets, provider
profiles, and isolated DMW storage. `run.env` names all shared settings used by
the measured paths. Commented secret keys are required inventory entries; real
values come from AppRC's app-wide configuration. Provider files contain only
the execution-specific differences.

The lifecycle selects the copied run as one AppRC storage. It then loads
`run.env`, loads the selected provider file with explicit override semantics,
and derives collection and Haiu storage values from `run.toml`.

## Directory contract

Keep provider and condition outputs flat. Organize evidence below each
condition by input unit and attempt:

```text
raw-<execution>/
├── manifest.json
├── provenance/
├── intermediates-shared_annotations/<unit-id>/
│   ├── annotation.json
│   └── attempts.json
├── intermediates-workflow_full_ontology/<unit-id>/
│   ├── checkpoint.json
│   └── attempts/<NNN[-failed]>/
├── intermediates-workflow_rag/<unit-id>/
├── intermediates-haiu_rag_ontologizer/<unit-id>/
├── result-workflow_full_ontology/<unit-id>/
│   ├── result.json
│   └── ontology.ttl
├── result-workflow_rag/<unit-id>/
└── result-haiu_rag_ontologizer/<unit-id>/
```

Do not introduce a nested `raw/`, `conditions/`, or `executions/` layer.
Every failed attempt has the explicit suffix `-failed`. Each attempt contains
its metadata, prompts, responses, exact provider assistant-message sidecars,
optional retrieval evidence, and the exact upstream result as compressed JSON.
Provider-message sidecars retain provider-specific reasoning fields even when
ordinary content is empty. `result.json` is a small terminal index;
it does not repeat the complete provider payload. Shared annotations are
stored once because both DMW conditions consume the same frozen annotation.
Analysis intermediates and timestamped workbooks stay below `analysis/`; final
figures and captions stay below `plots/`; service logs and BABYSIT journals
stay below `logs/`.

For a stopped run written by the former flat layout, use
`./run.sh migrate-artifacts`. The migration retains a hash-inventoried recovery
snapshot, verifies all new artifact references and exact payloads, removes
only the verified active duplicates, and records the clean harness transition.
It refuses a `retry_pending` schema-v2 checkpoint because that result is not
terminal. Resume only after the retry chain and migration both succeed.

For a stopped long run that adopts an operational patch, record the exact
clean source and dependency transition with `./run.sh
adopt-runtime-transition --reason "<factual reason>"`. Use `./run.sh
refresh-artifacts` to rebuild only deterministic metadata and Turtle
projections from the unchanged compressed upstream payloads.

## Lessons learned

- Smoke and full runs require separate run directories, DMW branches, and
  MongoDB collections.
- Provider interruptions resume the same locked run. Terminal model failures
  remain observations and are not recovery-amended automatically.
- AcademicCloud and LM Studio executions must be independently supervised so
  either provider can advance without waiting for the other.
- Prepare the branch-aware reference index before condition timing. Both RAG
  conditions must use the ontology ref in `INPUTS/retrieval_workspace.json`;
  neither condition should inherit one-time indexing work from execution
  order.
- Keep `ontology_example_limit = 0` for header--sublemma runs. The published
  whole-regest FAISS index has no query identity for synthetic pair IDs, so a
  nonzero value cannot provide the declared example.
- Remove obsolete TUSTEP layout controls while materializing the catalogue.
  Normalize only fields that contain a control, preserve all other input text
  byte-for-byte, and keep the normalization evidence in the catalogue.
