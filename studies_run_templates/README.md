# Study run templates

## Table of contents

1. [Purpose](#purpose)
2. [Workflow](#workflow)

## Purpose

Each study owns one complete, copyable run directory here. Templates contain
data and operator entry points only. Python implementation belongs below
`src/dmw_experiments/studies/`.

## Workflow

Create a run with `dmw_experiments new-run`, or copy the study's `template/`
directory manually. Edit the copied `README.md`, `run.toml`, and dotenv files
before validation. Never execute a publication run inside this tracked
template directory.
