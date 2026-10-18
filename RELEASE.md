# v1.1.0 release candidate procedure

This document describes a proposed, owner-controlled release procedure. The current
branch is an unreleased candidate. No PyPI upload, GitHub tag, release, or external
publisher/environment configuration is part of preparing it.

## Local and GitHub dry run

Run the repository quality checks, then dispatch **Release distributions** from the
`release/v1.1.0` branch with `publish` left `false`. The workflow builds a wheel and
source archive in an isolated packaging environment, checks strict metadata and
archive contents, installs each artifact into a clean environment, and runs the
offline doctor, all init templates, demo, and deterministic JSON/Markdown report
checks. It uploads the validated artifacts and SHA256 manifest to that workflow run.
It has no publication job on branch dispatch. A push of a `v*` tag runs those same
checks only; it never publishes by itself.

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
```

Do not use a local dry run as evidence that GitHub OIDC or a PyPI upload works.
Those operations require owner configuration and a later explicitly authorized
tagged dispatch.

## Required owner configuration before publication

The owner reports creating a PyPI account, but account ownership and publisher
configuration have not been verified. First confirm the account and project owner.
The official project JSON endpoint for normalized name `strategy-backtest-agent`
returned HTTP 404 at `2026-10-18T19:19:44Z`; this says only that public project
metadata was absent then. It does not reserve the name or prove that it can be
registered. A pending publisher also does not reserve an uncreated project name.

In the owning PyPI account, configure the Trusted Publisher for:

| Setting | Value |
| --- | --- |
| PyPI project | `strategy-backtest-agent` |
| GitHub owner | `changelia` |
| Repository | `strategy-backtest-agent` |
| Workflow file | `release.yml` |
| GitHub environment | `pypi` |

If the project does not exist, create a pending publisher with those exact values;
the first valid OIDC upload can create the project, subject to name availability.
If the project exists, use its Publishing settings and verify the account has the
required project-owner permission. Do not create an API token for this workflow.

In GitHub repository Settings → Environments, create `pypi`. Require approval from
an appropriate release owner, enable prevention of self-review, and restrict
deployments to the intended `v*` tags. Confirm any available administrator bypass
policy is appropriate. Add a repository tag ruleset for `v*` that limits tag
creation, updates and deletion to authorized release administrators. A workflow
tag filter alone does not control who can create a matching tag. Verify the PyPI
publisher and GitHub environment values match exactly before enabling publication.

## Future publication boundary

These steps are future work and are not verified by this candidate:

1. Review and merge the candidate through the repository's normal approval and CI
   process. Confirm `main` contains the reviewed release commit and required checks
   pass.
2. Create and push an annotated `v1.1.0` tag at that exact `main` commit, only by an
   authorized release owner. The tag push runs validation but cannot publish.
3. After confirming the validation run succeeded and external settings are correct,
   manually dispatch **Release distributions** with ref `v1.1.0` and `publish=true`.
   Approve the protected `pypi` environment. The publishing job checks the tag is
   annotated, the tag matches `pyproject.toml`, and the tag, workflow checkout and
   fetched `origin/main` point to the exact same commit. It verifies the SHA256
   manifest and uploads the already-validated wheel and sdist without rebuilding.
4. Treat a PyPI conflict or failed upload as a release failure. The workflow does
   not use `skip-existing` or an API-token fallback.

The publication job is limited to a manual tagged dispatch and is skipped for pull
requests, branch pushes, tag pushes, and dispatches with `publish=false`. Its
`id-token: write` permission is job-scoped; the build job and workflow default have
only `contents: read`.

## Post-publication verification

After a future successful upload, an owner should:

1. Confirm the official PyPI project page and JSON metadata show exactly version
   `1.1.0` and the intended project links.
2. Download the wheel and sdist from PyPI and compare their SHA256 hashes with the
   successful workflow run's `SHA256SUMS` artifact.
3. In a fresh virtual environment, install the exact version with
   `python -m pip install strategy-backtest-agent==1.1.0`, run `pip check`, then run
   `strategy-backtest doctor`, `strategy-backtest --demo`, and offline JSON and
   Markdown report smoke checks without credentials.
4. Verify GitHub `main` and dereferenced `v1.1.0` tag point to the intended same
   commit, and confirm both validation and publication Actions runs succeeded.

These checks are future verification steps, not evidence completed for this
candidate. OIDC identity exchange, environment approval and a real PyPI upload have
not been tested locally.

## Official guidance

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [Creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
