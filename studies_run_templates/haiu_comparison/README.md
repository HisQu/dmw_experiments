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

Keep provider and condition outputs flat:

```text
raw-<execution>/
├── intermediates-workflow_full_ontology/
├── intermediates-workflow_rag/
├── intermediates-haiu_rag_ontologizer/
├── result-workflow_full_ontology/
├── result-workflow_rag/
└── result-haiu_rag_ontologizer/
```

Do not introduce a nested `raw/`, `conditions/`, or `executions/` layer.
Analysis intermediates and workbooks stay below `analysis/`; final figures and
captions stay below `plots/`; service logs and BABYSIT journals stay below
`logs/`.

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
