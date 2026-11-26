# Release procedure

This procedure releases version `X.Y.Z` of `strategy-backtest-agent`. Replace `X.Y.Z`
with the release version throughout. Candidate preparation performs no merge, tag or
upload; publication is a separate, authorized action by the maintainer. Records of
past candidates are kept in [past release records](docs/history/release-records.md).

## 1. Candidate branch

Create `release/vX.Y.Z` from reviewed `main` whose checks and packaging pass. Describe
the candidate scope in the branch's review notes. Runtime dependencies, `poetry.lock`,
financial behavior and report schemas change only when the release scope says so.

## 2. Version pins to update

Change the package version and its current-version fixtures together:

- `pyproject.toml`: the package `version`.
- `tests/test_doctor.py`: the mocked installed and source metadata versions.
- `tests/test_release_gate.py`: the version, `refs/tags/vX.Y.Z` and
  `refs/heads/release/vX.Y.Z` fixtures.
- `CHANGELOG.md`: a `vX.Y.Z` section for the release.

Customer pip install/upgrade commands stay unpinned. Exact version pins below are
only for post-publication verification.

## 3. Local validation and optional non-publishing workflow

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
actionlint .github/workflows/ci.yml .github/workflows/release.yml
```

Run the existing `tests/packaging_ci.py` with isolated build tooling and a fresh
workspace outside the checkout, as in
[CI packaging validation](docs/history/CI_PACKAGING_VALIDATION.md).
It builds a fresh wheel and sdist, runs `twine check --strict`, inspects archives,
installs each separately and runs offline installed smoke checks. Both artifacts
must report `X.Y.Z`, import from their own site-packages and pass `pip check`.

After independent review, an optional manual **Release distributions** dispatch
from `release/vX.Y.Z` with `publish=false` can validate artifacts remotely without
publication permission. The artifact is named `validated-distributions` and includes
`SHA256SUMS`. Local validation cannot establish OIDC identity exchange, environment
approval or a successful PyPI upload.

## Release workflow and gate

The existing `.github/workflows/release.yml` and `tests/release_gate.py` are
version-driven:

- A matching `v*` tag push builds and validates only. Branch/PR activity cannot publish.
- Publication requires a manual tagged dispatch with `publish=true`, a successful
  build/validation job and approval of the protected `pypi` environment.
- The gate requires an annotated tag matching `pyproject.toml` (`vX.Y.Z`) and exact
  equality of workflow SHA, checkout SHA, tag commit and fetched `origin/main`.
- Workflow/build permissions remain `contents: read`; `id-token: write` is scoped
  only to the publishing job. There is no API-token fallback or `skip-existing`.
- Publishing downloads the validated artifacts, verifies `SHA256SUMS`, requires one
  wheel and one sdist, and uploads those files without rebuilding.

## Publication steps after review and separate authorization

1. Approve and merge the release commit to `main`; confirm main checks and packaging
   pass at the exact release commit.
2. Verify PyPI Trusted Publisher settings: project `strategy-backtest-agent`, owner
   `changelia`, repository `strategy-backtest-agent`, workflow `release.yml`, environment
   `pypi`. Verify environment approval, prevention of self-review, intended version-tag
   deployment restrictions and a tag ruleset limiting creation/updates/deletion.
3. Create and push an **annotated** `vX.Y.Z` tag at that exact main commit through the
   authorized release process. Preserve all existing tags. Confirm its validation run
   succeeds; a tag push does not publish.
4. Manually dispatch **Release distributions** on `vX.Y.Z` with `publish=true`, then
   approve the protected environment. Confirm the gate, checksum check and upload
   succeed. Treat name/version conflicts or upload errors as release failures.

## Post-publication verification

1. Verify the official PyPI page/JSON metadata reports exactly `X.Y.Z`. Download its
   wheel/sdist and compare SHA256 against the publishing run's `SHA256SUMS`.
2. In a fresh environment, run `python -m pip install strategy-backtest-agent==X.Y.Z`
   and `python -m pip check`. Verify the installed version, `strategy-backtest doctor`,
   `strategy-backtest --demo`, public `BacktestClient` import, offline backtest and
   deterministic JSON/Markdown reports outside the checkout without credentials,
   plus any checks specific to the release scope.
3. Confirm main and dereferenced `vX.Y.Z` still identify the release commit and both
   tag-validation and publishing runs succeeded. Only then record publication verified.

## References

- [Past release records](docs/history/release-records.md)
- [Customer documentation review and defect record](docs/CUSTOMER_DOCUMENTATION_COVERAGE.md)
- [Changelog](CHANGELOG.md)
- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
