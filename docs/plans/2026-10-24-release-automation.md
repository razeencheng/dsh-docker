# DSH Docker Release Automation Implementation Plan

> **For Codex agent:** REQUIRED SUB-SKILL: Use codex:executing-plans to implement this plan task-by-task.

**Goal:** Publish a documented assistant image with optional developer tools and reliable automatic upstream-tag releases.

**Architecture:** Docker packages upstream source pinned to the resolved commit. A Python release planner records discovered tags and successful releases on a dedicated Git state branch. GitHub Actions builds and tests both native Linux architectures, publishes immutable packaging revisions, then advances aliases without regressing latest.

**Tech Stack:** Docker Buildx, Debian/Node, Python standard library, GitHub Actions, Docker Hub.

## Confirmed decisions

- Public repository: razeencheng/dsh-docker; image: razeencheng/dsh.
- Git/SSH and basic utilities always installed; Python, Go, Docker CLI/Buildx/Compose default enabled with build-time switches.
- Docker daemon access opt-in; MIT license; Chinese primary README plus English documentation.
- Include alpha/rc tags. First run establishes an existing-tag baseline and builds only the newest; subsequent runs build every newly observed tag, including lower-version maintenance tags.
- Poll every 30 minutes; manual historical builds and packaging revisions supported.
- Two successful architecture smoke tests required before final tags. Immutable -rN tags; simplified upstream version and latest are movable aliases. Older reruns never regress latest.
- Updating the registry does not update any running server container.

## Task 1: Image and smoke tests

Files: Dockerfile, docker/*, scripts/smoke-test.sh, .dockerignore.
Inspect current upstream build contracts; adapt source packaging, install tools with strict boolean flags, preserve licenses, non-root runtime and persistent home/cache. Verify enabled and disabled tools, CLI boot, HTTP health and sandbox availability. Run at least one local native build, then both architectures in Actions.

## Task 2: Release planner, state and tests

Files: scripts/release.py, tests/test_release.py.
Write failing tests first for semver ordering, annotated tags, initial baseline, all later new tags, retries, tag mutation, manual revisions, immutable revision reuse and latest rollback prevention. Implement pure planning and state transitions, then GitHub/registry integration. State is persisted before builds so failed jobs remain pending.

## Task 3: Workflows

Files: .github/workflows/ci.yml, release.yml, build-image.yml.
Read-only PR checks; least-privilege release jobs on main only; secrets supplied only to publishing jobs. Separate native amd64/arm64 builds, cache, smoke-test then push temporary architecture tags; merge both digests after success. Global release concurrency, persistent per-tag completion and retry behavior; manual dispatch.

## Task 4: Project structure and documentation

Files: README.md, README.en.md, LICENSE, CONTRIBUTING.md, SECURITY.md, docs/*, compose files, .env.example, .gitignore, Makefile.
Document quickstart, build toggles, persisted data/home, socket opt-in, publishing/secrets, schedule limitations, migration and manual rollback. Exclude credentials and runtime state. Retain applicable upstream notices.

## Task 5: Verify, review and publish

Run unit tests, shell syntax/lint, workflow validation, Compose validation, local image smoke test, code review. Initialize local Git from the existing non-Git directory and publish to the user's confirmed empty main repository. Trigger the latest upstream release, monitor both builds and validate Docker Hub's final multi-platform manifests. Do not claim completion before these results are known.
