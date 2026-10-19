# v1.2.0 release procedure

Version `1.2.0` is prepared for review. **PyPI publication is pending verification**;
no upload is performed during candidate preparation. The candidate contains the public
Python API and preserves the released CLI, financial calculations, report schemas,
and runtime dependency policy.

## Local checks and non-publishing dry run

Run the quality checks locally, then manually dispatch **Release distributions** from
`release/v1.2.0` with `publish` set to `false`. That path builds and validates the
wheel and source distribution, installs each into a clean environment, runs the
installed offline smoke checks, and saves the validated artifacts and SHA256 manifest
to that workflow run. The artifact name is version-neutral: `validated-distributions`.
This dispatch does not grant OIDC publication permission or call the upload action.

A push of a matching `v*` tag runs build and validation only. It does not publish.
Only a manual dispatch on a version tag with `publish=true`, after the validation job
passes and the protected `pypi` environment is approved, can reach the publishing job.

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
```

A local dry run cannot verify GitHub OIDC identity exchange, environment approval, or
a real PyPI upload.

## Required external settings

The `strategy-backtest-agent` project is present on PyPI at v1.1.0. Before publishing,
the project owner must confirm account access and configure or verify its Trusted
Publisher settings:

| Setting | Value |
| --- | --- |
| PyPI project | `strategy-backtest-agent` |
| GitHub owner | `changelia` |
| Repository | `strategy-backtest-agent` |
| Workflow file | `release.yml` |
| GitHub environment | `pypi` |

In GitHub repository Settings → Environments, verify the `pypi` environment requires
release-owner approval, prevents self-review, and restricts deployments to intended
version tags. Add or verify a `v*` tag ruleset limiting tag creation, updates, and
deletion to authorized release administrators. A workflow tag filter alone does not
restrict who can create tags. Do not add an API-token secret; the workflow uses OIDC.

The official [PyPI project metadata](https://pypi.org/pypi/strategy-backtest-agent/json)
showed v1.1.0 during preparation. This confirms an existing public project, not the
current Trusted Publisher configuration or permission of the intended release owner.

## Publication sequence after review

1. Review and approve the release commit. Merge it to `main` through the normal
   repository process, then confirm the required `main` checks pass.
2. Create and push an **annotated** `v1.2.0` tag at that exact `main` commit using the
   authorized release process. Its tag-push run validates but cannot publish.
3. Confirm that validation run succeeds and the external `pypi` settings above are
   correct. Manually dispatch **Release distributions** on ref `v1.2.0` with
   `publish=true`, then approve the protected environment. The publish gate checks
   the annotated tag, package-version match, and that workflow checkout, tag commit,
   and fetched `origin/main` are the same commit. It checks `SHA256SUMS` and uploads
   the already-validated artifacts; it does not rebuild them.
4. Treat a name/version conflict or failed upload as a release failure. The workflow
   has no API-token fallback and does not use `skip-existing`.

The workflow is limited to a manual tagged dispatch for publication. Ordinary
pull-request and branch work, tag pushes, and dispatches with `publish=false` cannot
upload. `id-token: write` is limited to the publishing job; workflow defaults and the
build/validation job retain read-only contents permission.

## Post-publication verification

After the upload completes, the release owner should:

1. Verify the official PyPI page and JSON metadata report exactly `1.2.0` and the
   expected project links.
2. Download the wheel and sdist from PyPI and compare their SHA256 hashes with the
   successful publishing workflow's `SHA256SUMS` artifact.
3. In a fresh virtual environment, install
   `python -m pip install strategy-backtest-agent==1.2.0`, run `pip check`, and verify
   `strategy-backtest doctor`, `strategy-backtest --demo`, public `BacktestClient`
   import, offline backtest, and deterministic JSON/Markdown reports without
   credentials.
4. Verify `main` and dereferenced `v1.2.0` point to the same commit and confirm both
   the tag-validation and publishing GitHub Actions runs succeeded.

These are future release checks, not completed evidence for this candidate. No
GitHub merge, tag, OIDC publication, or PyPI upload is part of preparation.

## Official guidance

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [Creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
