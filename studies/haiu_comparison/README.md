# Haiu comparison study

## Table of contents

1. [Question and design](#question-and-design)
2. [Repository map](#repository-map)
3. [Published stack](#published-stack)
4. [Run the study](#run-the-study)
5. [Evidence rules](#evidence-rules)
6. [Documentation synchronization](#documentation-synchronization)

## Question and design

This study compares three ontology-generation conditions on the same input
units:

1. DMW with the complete reference ontology.
2. DMW with Haiu-retrieved ontology context.
3. Standalone generation with Haiu-retrieved ontology context.

The header--sublemma experiment contains 480 units. Each unit is one header
paired with one sublemma and includes the complete source regest text needed
to interpret that pair. The full run schedules 1,440 cells.

## Repository map

| Path | Owner |
| --- | --- |
| `src/dmw_experiments/shared/` | Reusable lifecycle, storage, supervision, configuration, and plotting support. |
| `src/dmw_experiments/studies/haiu_comparison/` | Study runner, conditions, exports, and study-specific analysis. |
| `studies/haiu_comparison/inputs/` | Immutable population, instructions, ontology, and retrieval identity. |
| `studies/haiu_comparison/specs/` | Separate disposable-smoke and complete-run contracts. |
| `studies/haiu_comparison/locks/` | Published DMW-stack release contract. |
| `output/runs/<run-id>/` | Raw observations, attempts, provenance, services, and BABYSIT logs. |
| `output/analyses/<analysis-id>/` | Derived workbooks and plots. |
| `tests/studies/haiu_comparison/` | Offline scientific and runner regressions. |

Generated artifacts never belong below `studies/haiu_comparison/`.

## Published stack

| Component | Release | Repository |
| --- | --- | --- |
| DMW | 1.1.3 | [HisQu/datamodel-workflow](https://github.com/HisQu/datamodel-workflow) |
| OPA | 2.1.2 | [HisQu/OPA](https://github.com/HisQu/OPA) |
| GTA | 0.2.4 | [HisQu/GTA](https://github.com/HisQu/GTA) |
| Haiu | 1.8.0 | [HisQu/haiu](https://github.com/HisQu/haiu) |
| MongoDBAPI | 1.0.2 | [HisQu/MongoDBAPI](https://github.com/HisQu/MongoDBAPI) |

The exact contract is
[`locks/published-dmw-stack-1.1.3.json`](locks/published-dmw-stack-1.1.3.json).
Tagged experiment releases use remote component tags and do not require
sibling repository clones.

## Run the study

Use the repository-root CLI:

```bash
dmw_experiments validate \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
dmw_experiments smoke \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
```

Review the three smoke cells before starting the complete independent run:

```bash
dmw_experiments run \
  --spec studies/haiu_comparison/specs/academiccloud-header-sublemma-full.json
```

## Evidence rules

- Context, length, and other terminal model failures are observations.
- Provider or machine interruption resumes only the same byte-identical run.
- The runner does not use recovery-amendment selectors.
- Smoke storage is disposable and must never be reused by the full run.
- Raw records and frozen provenance are authoritative; workbooks and plots are
  derived.

## Documentation synchronization

The narrative study chapter is
[`docs/studies/haiu_comparison.md`](../../docs/studies/haiu_comparison.md).
Update both files in the same change whenever the question, conditions,
population, stack, source locations, run contract, or evidence rules change.

> [!NOTE]
> Related: use the root [README](../../README.md) for installation and the
> [how-to guide](../../docs/How-To-User-Guides.md) for complete operations.
