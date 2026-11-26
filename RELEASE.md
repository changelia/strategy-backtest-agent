# v1.2.2 patch release procedure

Version `1.2.2` is a release candidate for independent review. **Publication remains
pending until verified**; candidate preparation performs no merge, tag or upload.
The candidate starts from reviewed main
`3c4619afac92f3c74b5b647841d0649d5382cf9e`, whose checks and packaging passed.
The [original v1.2.1 preparation record](docs/history/release-records.md#historical-v121-preparation-record) is
preserved verbatim, including its historical pending-publication wording and local
artifact hashes. It describes that earlier candidate, not the current release state.

## Candidate scope

This patch packages the reviewed direct natural-language DSL timestamp validation
fix. `BacktestClient.run(text, ...)` and `await client.arun(text, ...)` now validate
serialized backtest JSON consistently with explicit-config execution. Strict
validation, typed timezone-aware UTC evaluation boundaries, the original
`input` / `parsed_strategy` / `backtest_result` envelope, financial values, execution
assumptions, provenance and deterministic JSON/Markdown reports are preserved.

Published **1.2.0 and 1.2.1** are affected. With those releases, use
`config = client.parse(text)` followed by `client.run(config=config, demo=True)`.
The candidate fixes demo and non-demo direct execution; tests use mocked parsing
and an offline custom provider with a fixed end. No paid OpenAI or live Binance
request is needed for verification.

Preparation changes package metadata and current-version test fixtures to `1.2.2`
and updates release/customer documentation. Runtime dependencies, `poetry.lock`,
financial behavior and report schemas remain unchanged. Customer pip install/upgrade
commands stay unpinned; they do not yet install this correction. Exact version pins
below are only for post-publication verification.

## Local validation and optional non-publishing workflow

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
actionlint .github/workflows/ci.yml .github/workflows/release.yml
```

Run the existing `tests/packaging_ci.py` with isolated build tooling and a fresh
workspace outside the checkout, as in [CI packaging validation](docs/history/CI_PACKAGING_VALIDATION.md).
It builds a fresh wheel and sdist, runs `twine check --strict`, inspects archives,
installs each separately and runs offline installed smoke checks. Both artifacts
must report `1.2.2`, import from their own site-packages and pass `pip check`.
The installed direct DSL probe mocks only parsing with the complete validated
`examples/customer-ai-strategy.json`; it checks sync/async execution, config parity,
typed UTC boundaries, the source envelope, and deterministic direct/saved-source
JSON/Markdown reports. Application socket operations are denied.

After independent review, an optional manual **Release distributions** dispatch
from `release/v1.2.2` with `publish=false` can validate artifacts remotely without
publication permission. The artifact is named `validated-distributions` and includes
`SHA256SUMS`. This preparation task does not dispatch publication or create tags.
Local validation cannot establish OIDC identity exchange, environment approval or
a successful PyPI upload.

## Release workflow and gate review

The existing `.github/workflows/release.yml` and `tests/release_gate.py` are
version-driven and need no behavior change for this patch:

- A matching `v*` tag push builds and validates only. Branch/PR activity cannot publish.
- Publication requires a manual tagged dispatch with `publish=true`, a successful
  build/validation job and approval of the protected `pypi` environment.
- The gate requires an annotated tag matching `pyproject.toml` (`v1.2.2`) and exact
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
3. Create and push an **annotated** `v1.2.2` tag at that exact main commit through the
   authorized release process. Preserve all existing tags. Confirm its validation run
   succeeds; a tag push does not publish.
4. Manually dispatch **Release distributions** on `v1.2.2` with `publish=true`, then
   approve the protected environment. Confirm the gate, checksum check and upload
   succeed. Treat name/version conflicts or upload errors as release failures.
5. Verify the official PyPI page/JSON metadata reports exactly `1.2.2`. Download its
   wheel/sdist and compare SHA256 against the publishing run's `SHA256SUMS`.
6. In a fresh environment, run `python -m pip install strategy-backtest-agent==1.2.2`
   and `python -m pip check`. Verify installed version, doctor/CLI offline demo,
   direct DSL sync/async with mocked parsing, explicit-config parity, UTC types and
   deterministic JSON/Markdown reports outside the checkout with sockets denied.
7. Confirm main and dereferenced `v1.2.2` still identify the release commit and both
   tag-validation and publishing runs succeeded. Only then record publication verified.

No merge, tag, OIDC publication or PyPI upload is part of candidate preparation.

## Historical evidence

- [v1.2.1 preparation and local artifact hashes](docs/history/release-records.md#historical-v121-preparation-record)
- [Customer documentation review and defect record](docs/CUSTOMER_DOCUMENTATION_COVERAGE.md)
- [Changelog](CHANGELOG.md)

## Official guidance

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)
