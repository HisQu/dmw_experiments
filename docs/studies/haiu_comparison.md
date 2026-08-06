# Haiu comparison

## Table of contents

1. [Scientific question](#scientific-question)
2. [Experimental unit and conditions](#experimental-unit-and-conditions)
3. [Source and output ownership](#source-and-output-ownership)
4. [Published technology stack](#published-technology-stack)
5. [Execution contract](#execution-contract)
6. [Analysis contract](#analysis-contract)
7. [Documentation synchronization](#documentation-synchronization)

## Scientific question

The study tests whether Haiu retrieval gives the DMW enough relevant ontology
context to generate ontologies as reliably and effectively as supplying the
complete reference ontology. A standalone Haiu-retrieval condition separates
the effect of retrieval from the effect of the DMW workflow.

## Experimental unit and conditions

The frozen population contains 480 header--sublemma units. A unit contains one
header, one sublemma, and the complete source regest text required to interpret
that pair. It is not the complete multi-sublemma regest as one indivisible
generation target.

Every unit is scheduled under three conditions:

| Condition | Measured path |
| --- | --- |
| DMW + Full Ontology | DMW receives the complete reference ontology. |
| DMW + HAIU | DMW receives ontology context retrieved by Haiu. |
| HAIU | Standalone ontology generation receives Haiu-retrieved context. |

The complete matrix contains 1,440 cells. Pairwise analyses use the two
scientific comparisons DMW versus DMW + HAIU and DMW + HAIU versus HAIU.

## Source and output ownership

| Path | Responsibility |
| --- | --- |
| `src/dmw_experiments/studies/haiu_comparison/` | Scientific execution and analysis code. |
| `src/dmw_experiments/shared/` | Reusable lifecycle, configuration, supervision, artifacts, and plotting code. |
| `studies/haiu_comparison/inputs/` | Immutable scientific inputs. |
| `studies/haiu_comparison/specs/` | Reviewable smoke and full-run contracts. |
| `studies/haiu_comparison/locks/` | Exact published DMW-stack contract. |
| `tests/studies/haiu_comparison/` | Study regressions. |
| `output/runs/<run-id>/` | Authoritative raw data and run-local operational evidence. |
| `output/analyses/<analysis-id>/` | Derived workbooks, review packets, and plots. |

The top-level `studies/` directory contains tracked scientific facts. The
Python package's `studies` namespace contains code. The two locations share a
study name so a tired operator can move between them without translation.

## Published technology stack

| Component | Release | Repository | Role |
| --- | --- | --- | --- |
| DMW | 1.1.3 | [HisQu/datamodel-workflow](https://github.com/HisQu/datamodel-workflow) | Workflow and API under test. |
| OPA | 2.1.2 | [HisQu/OPA](https://github.com/HisQu/OPA) | Ontology prompting used by DMW. |
| GTA | 0.2.4 | [HisQu/GTA](https://github.com/HisQu/GTA) | Generation transport and metadata. |
| Haiu | 1.8.0 | [HisQu/haiu](https://github.com/HisQu/haiu) | Retrieval and standalone condition. |
| MongoDBAPI | 1.0.2 | [HisQu/MongoDBAPI](https://github.com/HisQu/MongoDBAPI) | Versioned DMW persistence. |

The experiment release locks remote tags and resolved commits. Local editable
clones are temporary development conveniences, not part of a released run.

## Execution contract

The canonical AcademicCloud smoke uses one unit and independent disposable
DMW storage. The full run uses all 480 units and a second fresh branch and
collection set. Both schedule all three conditions.

The lifecycle freezes the chosen spec, prepares storage, captures schema-v2
environment provenance, and launches backend, runner, and watchdog as
user-systemd services. A machine interruption may resume the same run only
when the spec and frozen artifacts are byte-identical.

Terminal model outcomes, including context and length exhaustion, remain
observations. Infrastructure interruption is not converted into a model
failure, and recovery-amendment selectors are not used.

## Analysis contract

Raw JSON records are authoritative. Workbooks, review packets, plots, and
audit tables are derived and may be regenerated. Human grade inputs are kept
separate and are never overwritten by the analysis command.

Strict export requires every scheduled cell to be terminal. Diagnostic export
of an incomplete matrix must be requested explicitly with `--allow-partial`.

## Documentation synchronization

The operational counterpart is
[`studies/haiu_comparison/README.md`](../../studies/haiu_comparison/README.md).
Update both documents in the same change when the question, population,
conditions, stack, paths, execution contract, or analysis contract changes.

> [!NOTE]
> Related links:
> - Use the [how-to guide](../How-To-User-Guides.md) to launch, pause, resume,
>   hand off, and analyze a run.
> - Use the exact [reference paths](../References.md#study-files) when writing
>   commands or automation.
