# Experiment output

This is the default storage root for generated experiment artifacts. Its
contents are ignored by Git.

- `runs/<run-id>/` contains one provider run and its operational logs.
- `analyses/<analysis-id>/` contains derived cross-run workbooks and figures.
- `logs/archive/` contains historical logs that cannot be assigned to one run.

Run `dmw_experiments output` to print the active storage root. Set
`DMW_EXPERIMENTS_STORAGE` to use a different root.
