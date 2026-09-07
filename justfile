# ===============================================================
# Justfile for Python projects using uv + pyproject.toml
# ===============================================================
# Why this exists:
# - One command to install exactly what's in uv.lock (safe for CI).
# - A clear, explicit path to re-lock/upgrade when you WANT changes.
# - Optional exports for the "I only understand requirements.txt" crowd.
#
# References (summarized):
# - uv auto-locks by default; --locked disables that and errors if stale.
# - uv can export a requirements.txt-style file and can also "compile" one.
#   See: uv concepts: lock/sync, uv export, uv pip compile.
#
# Dependencies: uv (and optionally direnv). Python itself is handled by uv.
# ===============================================================

# Let recipes use Bash features and fail-fast in pipelines
set shell := ["bash", "-euo", "pipefail", "-c"]

# > Include PyPI in normal tag releases. Keep this policy in version control.
RELEASE_PYPI := "false"

# Run `just` with no recipe to list tasks
default:
    @just --list

# ---------------------------------------------------------------
# Internal guards (kept private so they don't clutter `just --list`)
# ---------------------------------------------------------------
[private]
_note-direnv:
    @if command -v direnv >/dev/null; then \
        test -n "${VIRTUAL_ENV-}" || echo "ℹ direnv detected but VIRTUAL_ENV not active. Run: direnv allow && direnv reload"; \
    fi

[private]
_check-uv:
    : ${UV_PROJECT_ENVIRONMENT:="$PWD/.venv"}
    @command -v uv >/dev/null || { \
        echo "✗ uv not found. Install from https://docs.astral.sh/uv/ then retry." >&2; \
        exit 127; \
    }

[private]
_check-gh:
    @command -v gh >/dev/null || { \
        echo "gh not found. Install it from https://cli.github.com/ and retry." >&2; \
        exit 127; \
    }
    @gh auth status >/dev/null 2>&1 || { \
        echo "gh is not authenticated. Run 'gh auth login' and retry." >&2; \
        exit 1; \
    }

[private]
_check-clean-worktree action="publishing":
    @git diff --quiet || { \
        echo "Unstaged changes exist. Commit or stash before {{ action }}." >&2; \
        exit 1; \
    }
    @git diff --cached --quiet || { \
        echo "Staged changes exist. Commit before {{ action }}." >&2; \
        exit 1; \
    }
    @test -z "$(git ls-files --others --exclude-standard)" || { \
        echo "Untracked files exist. Commit, ignore, or remove them before {{ action }}:" >&2; \
        git ls-files --others --exclude-standard >&2; \
        exit 1; \
    }

# ---------------------------------------------------------------
# Clean / environment helpers
# ---------------------------------------------------------------

# Remove transient junk: uv cache,  __pycache__, .pytest_cache, .mypy_cache, .ruff_cache. Does NOT touch uv.lock or your venv.
clean:
    @echo "🧹 Cleaning caches and build artifacts..."
    find . -type d -name "__pycache__" -prune -exec rm -rf {} + || true
    rm -rf .pytest_cache .mypy_cache .ruff_cache dist build *.egg-info || true
    uv cache prune -y || true

# Rebuilds python venv from uv.lock
reset-venv:
    @echo "♻ Rebuilding virtual environment..."
    uv venv --seed --clear
    uv sync --frozen --all-groups

# ---------------------------------------------------------------
# Install flows
# ---------------------------------------------------------------
# Key rule: CI and teammates should *not* relock by accident.
# We therefore install with `--locked` which errors if uv.lock is stale.
# If it errors, you intentionally run `just lock` or `just upgrade`.
# > --all-groups: Install all local groups from [dependency-groups], such as dev.
# > --no-default-groups: Skip uv's default groups, including dev, for runtime-only installs.
# > --frozen: Sync from uv.lock while ignoring pyproject.toml
# > --locked: Exit non-zero if pyproject.toml differs from uv.lock

# Install or sync everything from uv.lock into venv. (CI should use this)
# `python -m pip install -e ".[<all_extras>]" --group dev`
sync:
    just _note-direnv
    just _check-uv
    uv sync --all-groups --locked
alias install := sync

# Overlay neighboring source checkouts without changing pyproject.toml or the
# release locks. Run `just sync` to restore the published stack.
sync-local-stack:
    just sync
    @for repository in ../datamodel-workflow ../GTA ../haiu ../OPA; do \
        test -f "$repository/pyproject.toml" || { \
            echo "Missing local checkout: $repository" >&2; \
            exit 1; \
        }; \
    done
    uv pip install --python .venv/bin/python --no-deps --editable \
        ../datamodel-workflow ../GTA ../haiu ../OPA

# ---------------------------------------------------------------
# Locking and upgrading
# ---------------------------------------------------------------
# Examples:
#   just lock                   # resolve using current constraints
#   just lock --upgrade         # allow upgrades while resolving
#   just lock --python 3.12     # resolve for a specific interpreter

# Creates uv.lock based on pyproject.toml and exports pylock.toml.
lock *ARGS:
    just _check-uv
    uv lock {{ ARGS }}
    uv export -o pylock.toml --all-extras --all-groups --quiet
    uv export -o requirements-runtime.lock --no-dev --no-emit-project --no-hashes --quiet

# Re-lock with --upgrade & install from the new lock.
upgrade *ARGS:
    just lock --upgrade {{ ARGS }}
    uv sync --all-groups --locked

# Re-lock with --upgrade ONLY git-based dependencies & uv sync from the new lock.
upgrade-repos *ARGS:
    @echo "⬆️  Upgrading only git-based dependencies to latest revisions..."
    uv lock \
        # --upgrade-package mongodbapi \
        # --upgrade-package gta \
        # --upgrade-package embedding \
        # --upgrade-package haiu \
        {{ ARGS }}
    uv sync --all-extras --all-groups --locked
alias uprep := upgrade-repos

# --- Switch python versions -------

# Switches major Python version for the project. Usage: just py-switch 3.13t
py-switch version="3.13":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🐍 Switching project Python to {{ version }}"
    # > Ensure the requested interpreter exists.
    uv python install {{ version }}
    # > Persist the project's default interpreter request.
    uv python pin {{ version }}
    # > Recreate the project venv with that interpreter.
    uv venv --python {{ version }} --seed --clear
    # > Sync dependencies for the recreated environment.
    uv sync --all-extras --all-groups
    # > Verify via uv, so shell activation state cannot mislead you.
    uv run python -c 'import sys; print(sys.version); print(sys.executable)'

# ---------------------------------------------------------------
# Testing
# ---------------------------------------------------------------

[private]
_ci-check-python version environment:
    #!/usr/bin/env bash
    set -euo pipefail
    export UV_PROJECT_ENVIRONMENT="{{ environment }}"
    export UV_LINK_MODE=copy
    export MPLCONFIGDIR="{{ environment }}/matplotlib"
    export MPLBACKEND=Agg
    unset VIRTUAL_ENV
    echo "Python {{ version }}: preparing an isolated CI environment..."
    uv sync \
        --python "{{ version }}" \
        --locked \
        --all-groups \
        --quiet \
        --no-progress
    mkdir -p "$MPLCONFIGDIR"
    uv lock --check --quiet
    uv run --python "{{ version }}" --locked --no-sync ruff format . --check
    uv run --python "{{ version }}" --locked --no-sync ruff check .
    uv run --python "{{ version }}" --locked --no-sync \
        pyright --venvpath "$(dirname "$UV_PROJECT_ENVIRONMENT")"
    uv run --python "{{ version }}" --locked --no-sync pytest
    uv run --python "{{ version }}" --locked --no-sync \
        python -m compileall -q src tests
    echo "Python {{ version }}: CI checks passed."

# ---------------------------------------------------------------
# Build / GitHub releases
# ---------------------------------------------------------------

# Build release artifacts with the configured pyproject backend.
build:
    just _check-uv
    rm -rf dist
    uv build --python 3.12 --no-sources

[private]
_release-artifact-check notes_output:
    #!/usr/bin/env bash
    set -euo pipefail
    version="$(uv version --short)"
    tag="${GITHUB_REF_NAME:-v${version}}"
    notes_output="{{ notes_output }}"
    artifact_root="$(mktemp -d)"
    trap 'rm -rf "$artifact_root"' EXIT

    mkdir -p "$(dirname "$notes_output")"
    PYTHONPATH=src python -m dmw_experiments.shared.release_notes \
        "$version" \
        --output "$notes_output"

    just build

    shopt -s nullglob
    wheels=(dist/*.whl)
    sdists=(dist/*.tar.gz)
    if [[ "${#wheels[@]}" -ne 1 || "${#sdists[@]}" -ne 1 ]]; then
        echo "Expected exactly one wheel and one sdist in dist/." >&2
        exit 1
    fi

    expected_wheel="dmw_experiments-${version}-py3-none-any.whl"
    expected_sdist="dmw_experiments-${version}.tar.gz"
    if [[ "$(basename "${wheels[0]}")" != "$expected_wheel" ]]; then
        echo "Expected $expected_wheel, found ${wheels[0]}." >&2
        exit 1
    fi
    if [[ "$(basename "${sdists[0]}")" != "$expected_sdist" ]]; then
        echo "Expected $expected_sdist, found ${sdists[0]}." >&2
        exit 1
    fi

    wheel="$(realpath "${wheels[0]}")"
    sdist="$(realpath "${sdists[0]}")"
    uv run --with twine --no-project -- twine check "$wheel" "$sdist"

    artifact_number=0
    for artifact in "$wheel" "$sdist"; do
        for python_version in 3.12 3.13; do
            artifact_number=$((artifact_number + 1))
            environment="$artifact_root/artifact-${artifact_number}"
            uv venv --python "$python_version" "$environment" --quiet
            uv pip install \
                --python "$environment/bin/python" \
                --no-deps \
                "$artifact" \
                --quiet
            "$environment/bin/python" -c \
                'import importlib.metadata; import dmw_experiments; assert importlib.metadata.version("dmw_experiments") == "'"$version"'"'
        done
    done

    echo "Release artifacts for $tag passed Python 3.12 and 3.13 smoke checks."

# Rehearse the complete release gate without uploading anything.
release-check:
    #!/usr/bin/env bash
    set -euo pipefail
    just _check-uv
    check_root="$(mktemp -d)"
    trap 'rm -rf "$check_root"' EXIT

    current_version="$(uv version --short)"
    prepared_version="$(PYTHONPATH=src python -c 'from pathlib import Path; from dmw_experiments.shared.release_notes import latest_release_version; print(latest_release_version(Path("CHANGELOG.md").read_text(encoding="utf-8")))')"
    if [[ "${DMW_EXPERIMENTS_RELEASE_IN_PROGRESS:-}" != 1 && "$prepared_version" != "$current_version" ]]; then
        PYTHONPATH=src python -c 'import sys; from dmw_experiments.shared.release_notes import validate_newer_release; validate_newer_release(*sys.argv[1:])' "$current_version" "$prepared_version"

        version_root="$check_root/version"
        mkdir -p "$version_root"
        cp \
            pyproject.toml \
            uv.lock \
            pylock.toml \
            requirements-runtime.lock \
            "$version_root/"
        restore_version_files=true
        cleanup() {
            exit_code=$?
            trap - EXIT
            if [[ "$restore_version_files" == true ]]; then
                cp "$version_root/pyproject.toml" pyproject.toml
                cp "$version_root/uv.lock" uv.lock
                cp "$version_root/pylock.toml" pylock.toml
                cp "$version_root/requirements-runtime.lock" requirements-runtime.lock
            fi
            rm -rf "$check_root"
            exit "$exit_code"
        }
        trap cleanup EXIT

        uv version "$prepared_version" --no-sync
        uv export -o pylock.toml --all-extras --all-groups --quiet
        uv export \
            -o requirements-runtime.lock \
            --no-dev \
            --no-emit-project \
            --no-hashes \
            --quiet
        DMW_EXPERIMENTS_RELEASE_IN_PROGRESS=1 just release-check
        exit $?
    fi

    for python_version in 3.12 3.13; do
        just _ci-check-python \
            "$python_version" \
            "$check_root/python-${python_version}/.venv"
        # > The locked stack includes multi-GB CUDA wheels. Retain one CI
        # > environment at a time so the release gate fits on GitHub runners.
        rm -rf "$check_root/python-${python_version}"
    done
    just _release-artifact-check "$check_root/release-notes.md"
    echo "Local release rehearsal passed; nothing was uploaded."

# Prepare a checked version commit and annotated local release tag.
release-prepare level="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    just _check-uv
    just _check-clean-worktree "preparing the release"

    next_version="$(uv version --bump "{{ level }}" --dry-run --short)"
    tag="v${next_version}"
    if git rev-parse --verify --quiet "refs/tags/${tag}" >/dev/null; then
        echo "Tag ${tag} already exists. Choose another release level." >&2
        exit 1
    fi

    release_root="$(mktemp -d)"
    restore_version_files=false
    cleanup() {
        exit_code=$?
        trap - EXIT
        if [[ "$restore_version_files" == true ]]; then
            cp "$release_root/pyproject.toml" pyproject.toml
            cp "$release_root/uv.lock" uv.lock
            cp "$release_root/pylock.toml" pylock.toml
            cp "$release_root/requirements-runtime.lock" requirements-runtime.lock
        fi
        rm -rf "$release_root"
        exit "$exit_code"
    }
    trap cleanup EXIT

    PYTHONPATH=src python -m dmw_experiments.shared.release_notes \
        "$next_version" \
        --output "$release_root/release-notes.md"

    cp \
        pyproject.toml \
        uv.lock \
        pylock.toml \
        requirements-runtime.lock \
        "$release_root/"
    restore_version_files=true

    uv version --bump "{{ level }}" --no-sync
    uv export -o pylock.toml --all-extras --all-groups --quiet
    uv export \
        -o requirements-runtime.lock \
        --no-dev \
        --no-emit-project \
        --no-hashes \
        --quiet
    just release-check

    git commit \
        --only \
        pyproject.toml \
        uv.lock \
        pylock.toml \
        requirements-runtime.lock \
        -m "Bump version to ${next_version}"
    restore_version_files=false
    git tag -a "$tag" -m "Release $tag"

    echo "Prepared $tag locally; nothing was uploaded."
    echo "Review the commit and tag, then run:"
    echo "  just release-push $tag"
    echo "GitHub will rerun CI and create the GitHub Release."

# Push a prepared release commit and tag as one remote operation.
release-push tag:
    #!/usr/bin/env bash
    set -euo pipefail
    just _check-clean-worktree "pushing the release"
    tag="{{ tag }}"

    if [[ ! "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        echo "Invalid release tag '${tag}'; expected vMAJOR.MINOR.PATCH." >&2
        exit 1
    fi
    if [[ "$(git branch --show-current)" != "main" ]]; then
        echo "Release pushes must run from the main branch." >&2
        exit 1
    fi
    if ! git cat-file -e "${tag}^{tag}" 2>/dev/null; then
        echo "Annotated local tag ${tag} does not exist." >&2
        exit 1
    fi
    if [[ "$(git rev-list -n 1 "$tag")" != "$(git rev-parse HEAD)" ]]; then
        echo "Tag ${tag} does not point to the current main commit." >&2
        exit 1
    fi
    release_pypi="$(just --evaluate RELEASE_PYPI)"
    if [[ "$release_pypi" != "true" && "$release_pypi" != "false" ]]; then
        echo "RELEASE_PYPI must be \"true\" or \"false\", found '${release_pypi}'." >&2
        exit 1
    fi

    echo "Pushing main and ${tag} atomically. RELEASE_PYPI=${release_pypi}."
    if ! git push --atomic origin main "$tag"; then
        echo "The remote push failed. The release remains prepared locally." >&2
        echo "Retry with: just release-push ${tag}" >&2
        exit 1
    fi
    echo "GitHub Actions will create the release. This command does not wait for it."
    echo "If PyPI was skipped, run: just publish-pypi ${tag}"

# Prepare and push a release. GitHub Actions owns artifact publication.
release level="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    just release-prepare "{{ level }}"
    tag="v$(uv version --short)"
    if ! just release-push "$tag"; then
        echo "Release ${tag} remains prepared locally." >&2
        echo "Retry with: just release-push ${tag}" >&2
        exit 1
    fi

# Publish the artifacts attached to an existing GitHub Release.
publish-pypi tag:
    #!/usr/bin/env bash
    set -euo pipefail
    just _check-gh
    tag="{{ tag }}"

    if [[ ! "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        echo "Invalid release tag '${tag}'; expected vMAJOR.MINOR.PATCH." >&2
        exit 1
    fi
    if ! is_draft="$(gh release view "$tag" --json isDraft --jq .isDraft)"; then
        echo "GitHub Release ${tag} does not exist." >&2
        exit 1
    fi
    if [[ "$is_draft" == "true" ]]; then
        echo "GitHub Release ${tag} is still a draft and cannot be published." >&2
        exit 1
    fi
    wheel_count="$(gh release view "$tag" --json assets --jq '[.assets[].name | select(endswith(".whl"))] | length')"
    sdist_count="$(gh release view "$tag" --json assets --jq '[.assets[].name | select(endswith(".tar.gz"))] | length')"
    if [[ "$wheel_count" != 1 || "$sdist_count" != 1 ]]; then
        echo "GitHub Release ${tag} must contain exactly one wheel and one source archive." >&2
        exit 1
    fi

    gh workflow run release.yml --raw-field "release_tag=${tag}"
    echo "Requested PyPI publication for ${tag}. Follow the workflow URL above."

# Run GitHub Actions triggered by push locally using act
gitactions:
    act push \
      --secret-file .env.secret \
      -P ubuntu-latest=catthehacker/ubuntu:act-latest \
      --container-options "-v $HOME/.act-uv-cache:/root/.cache/uv" \
      --action-offline-mode

# ---------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------

# Example: just run -- python -m yourpkg --help
# Runs your package’s CLI or module under the locked environment.
run *CMD:
    just _check-uv
    uv run --locked -- {{ CMD }}

# Print effective dependency tree (won’t modify lock when used with --locked)
tree:
    just _check-uv
    uv tree --locked || uv tree

# Show uv + Python info for debugging bug reports
diagnose:
    just _check-uv
    uv --version
    uv python list || true
    uv sync --check --all-groups

# ---------------------------------------------------------------
# Example recipe written in python (executes venv/python):
# pyyy:
#     #!/usr/bin/env python3
#     import sys
#     print(sys.executable)
#     print('Hello from python!')
