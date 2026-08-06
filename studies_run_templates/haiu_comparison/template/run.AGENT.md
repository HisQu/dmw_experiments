# Agent run instructions

Read the repository `AGENTS.md`, this run's `README.md`, the Haiu comparison
template README, root `TODO.md`, and relevant earlier run READMEs before acting.

Use `./run.sh` or `./run.ps1` as the only operator entry point. Keep the
execution-specific `BABYSIT-*.md` files current with launches, checkpoints,
failures, retries, resumptions, and interventions. Use `status` to determine
progress; do not infer completion from log text.

Terminal model failures, including context or length exhaustion, are evidence.
Resume only identical settings after infrastructure interruption. Do not use
recovery-amendment flags or patch dependencies without explaining the evidence
and receiving approval.

Never place credentials, absolute machine paths, or private host information
in this directory. Real credentials come from AppRC's app-wide configuration.
