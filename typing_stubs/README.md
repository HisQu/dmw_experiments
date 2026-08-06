# DMW type stubs

These stubs are deliberately limited to the two public DMW imports used by
`run_lmstudio_backend.py`. They support static checking of the experiment in
the Haiu development environment; they are never imported at runtime and do
not replace the pinned DMW distribution used by the publication backend.

Run the scoped check from the repository root:

```bash
.venv/bin/pyright -p experiments/datamodel_workflow_haiu_comparison/pyright-experiment.json
```
