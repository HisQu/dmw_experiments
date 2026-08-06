# Experiment output

This is the default storage root for generated experiment artifacts. Its
contents are ignored by Git.

- `runs/<run-id>/` contains one provider run and its operational logs.
- `analyses/<analysis-id>/` contains derived cross-run workbooks and figures.
- `runtime/release-checkouts/` contains ignored source evidence cloned from
  published tags.

Run `dmw_experiments config show --json` to inspect the active storage. Set
`DMW_EXPERIMENTS_STORAGE` to use a different root.
