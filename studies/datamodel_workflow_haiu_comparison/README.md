# DMW--Haiu ontology comparison

This study compares three ontology-generation conditions on the same input
units:

1. DMW with the complete reference ontology.
2. DMW with Haiu-retrieved ontology context.
3. Standalone generation with Haiu-retrieved ontology context.

The header--sublemma experiment contains 480 input units. Each unit is one
header paired with one sublemma and includes the complete source regest text
needed to interpret that pair. The full run therefore schedules 1,440 cells.

`inputs/` contains immutable scientific inputs. `specs/` contains the separate
AcademicCloud smoke and full-run contracts. Generated artifacts never belong
here; they are written below the active `output/` storage root.

Use the repository root CLI:

```bash
dmw_experiments validate --spec studies/datamodel_workflow_haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
dmw_experiments smoke --spec studies/datamodel_workflow_haiu_comparison/specs/academiccloud-header-sublemma-smoke.json
```
