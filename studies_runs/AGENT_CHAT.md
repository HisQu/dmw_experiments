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
