# Agent chat

This file is a low-frequency coordination channel for long-running studies.
It is not a run log. Routine progress, retries, interruptions, and terminal
outcomes belong in the active run's ignored `logs/BABYSIT-*.md` journal.

## Protocol

1. Pull `main` before editing this file.
2. Append a UTC or timezone-qualified timestamped message under `Messages`.
3. State the sender as `User` or `Agent`.
4. Commit and push the message to `origin/main`.
5. Never include credentials, private host data, or machine-specific absolute
   paths.

The babysitting agent checks `origin/main` approximately every three hours and
fast-forwards a clean checkout before reading new messages. The agent works
independently between checks and writes here only for a necessary question,
decision, or useful acknowledgement.

## Message template

```text
### 2026-08-07T09:00:00+02:00 — User

Message text.
```

## Messages

### 2026-08-06T23:10:00+02:00 — Agent

Channel created. AcademicCloud smoke testing and the subsequent full
header–sublemma run remain under active supervision.

### 2026-08-07T00:10:00+02:00 — Agent

Smoke testing found that published OPA's separate ontology-example search is
defined only for numeric complete-regest IDs, not the synthetic
header–sublemma IDs. It safely fell back to zero examples, but that disagreed
with the configured limit of one. I am making the full run's declared limit
zero so its configuration matches the effective prompt. Both DMW conditions
remain identical on this setting; their intended difference is still full
ontology versus HAIU retrieval context. No published stack dependency is being
patched.

### 2026-08-07T01:05:00+02:00 — Agent

v0.4.0 is published and its smoke run passed all three conditions, but the
full run stopped during input preflight at 0/1,440 cells. The frozen catalogue
contains legacy TUSTEP controls (`&w&w` and `&y`) in 44 of 480 units across 9
source regesta. The controls occur only in headers. RG_data's documented
canonical import removes exactly these controls and collapses whitespace, but
the copied catalogue predates that cleanup. Refreshing isolated MongoDB from
the current catalogue therefore reproduces the problem.

I paused all services before any model cell ran. I recommend applying RG_data's
established deterministic text cleanup to the catalogue, retaining all 480
units and their order and source lineage, recording the normalization in its
metadata, recomputing content hashes, releasing a dmw_experiments patch, and
starting a new run with fresh storage. This does not patch DMW or HAIU.

Please approve or reject that input normalization. Until then I will keep the
0-cell run paused and will not weaken the guard or silently change scientific
inputs.
