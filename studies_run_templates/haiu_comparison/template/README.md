# Run: template

## Table of contents

1. [Purpose](#purpose)
2. [Changes from the template](#changes-from-the-template)
3. [Configuration](#configuration)
4. [Operation](#operation)

## Purpose

Replace this paragraph with the concrete purpose, date, providers, and scope
of the copied run.

## Changes from the template

List every deliberate change to `run.toml`, inputs, environment settings, or
the published dependency lock. Write `None` when the copy is unchanged apart
from generated identities.

Before starting, read the study template README, root `TODO.md`, and the
README files of relevant earlier runs. Record reusable lessons in the study
template README when they are not already implemented there.

## Configuration

- `run.toml` is authoritative for the scientific and storage contract.
- `run.env` is exhaustive for shared non-secret runtime settings.
- `run.academiccloud.env` and `run.lmstudio.env` contain provider differences.
- AppRC app-wide configuration contains every real credential and the
  machine-local NER index path.
- `INPUTS/retrieval_workspace.json` is the authoritative branch-aware
  reference-index identity shared by DMW + HAIU and standalone HAIU. The
  runner validates and prepares it before condition timing begins.

Never assign real credentials or absolute machine paths in this directory.

## Operation

```bash
./run.sh validate
./run.sh start
./run.sh status
./run.sh pause
./run.sh resume
./run.sh analyze
./run.sh prepare-promotion
```

Read `run.AGENT.md` before delegating operation or babysitting to an agent.
