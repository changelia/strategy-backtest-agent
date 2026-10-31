# v1.2.2 patch release procedure

Version `1.2.2` is a release candidate for independent review. **Publication remains
pending until verified**; candidate preparation performs no merge, tag or upload.
The candidate starts from reviewed main
`3c4619afac92f3c74b5b647841d0649d5382cf9e`, whose checks and packaging passed.
The [original v1.2.1 preparation record](#historical-v121-preparation-record) is
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
workspace outside the checkout, as in [CI packaging validation](CI_PACKAGING_VALIDATION.md).
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

- [v1.2.1 preparation and local artifact hashes](#historical-v121-preparation-record)
- [Customer documentation review and defect record](docs/CUSTOMER_DOCUMENTATION_COVERAGE.md)
- [Changelog](CHANGELOG.md)

## Official guidance

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)

## Historical v1.2.1 preparation record

The original record below preserves historical status, procedures, validation results
and artifact hashes. Use the v1.2.2 procedure above for the current candidate.

<details>
<summary>Original v1.2.1 preparation record</summary>

# v1.2.1 release procedure

Version `1.2.1` is prepared for review. **PyPI publication is pending verification**;
no upload is performed during candidate preparation. The candidate starts from main
at `73856232468e8f7efa75d2bb21a5a33d5e46a970`, including the reviewed customer guides
and runnable examples. It packages documentation improvements alongside the existing
public Python API and CLI, preserving runtime behavior, financial calculations,
report/schema versions and dependencies. The previously published baseline is v1.2.0.

## Candidate scope and known issue

This is a documentation patch candidate, not a runtime bug-fix release. The known
direct natural-language single-backtest DSL defect remains: `client.run(text,
demo=True)` can reject serialized UTC timestamps when parsing returns a `RuleStrategy`.
Use `config = client.parse(text)` followed by `client.run(config=config, demo=True)`.
Do not describe the candidate as fixing this issue. See the
[coverage and defect record](docs/CUSTOMER_DOCUMENTATION_COVERAGE.md#discovered-product-defect-direct-natural-language-dsl-backtest).

Customer install/upgrade commands stay unpinned. Exact version pins below are only
for release verification. The README embedded in already uploaded distributions
cannot be changed by a GitHub edit; v1.2.1 publication is a separate, later action.

## Local checks and non-publishing dry run

Run the quality checks locally, then manually dispatch **Release distributions** from
`release/v1.2.1` with `publish` set to `false`. That path builds and validates the
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
actionlint
poetry run strategy-backtest --demo
```

A local dry run cannot verify GitHub OIDC identity exchange, environment approval, or
a real PyPI upload.

## Required external settings

The `strategy-backtest-agent` project is present on PyPI at v1.2.0. Before publishing,
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
was verified directly at v1.2.0 during the customer-documentation review. This
confirms an existing public project, not the current Trusted Publisher configuration
or permission of the intended release owner.

## Publication sequence after review

1. Review and approve the release commit. Merge it to `main` through the normal
   repository process, then confirm the required `main` checks pass.
2. Create and push an **annotated** `v1.2.1` tag at that exact `main` commit using the
   authorized release process. Its tag-push run validates but cannot publish.
3. Confirm that validation run succeeds and the external `pypi` settings above are
   correct. Manually dispatch **Release distributions** on ref `v1.2.1` with
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

1. Verify the official PyPI page and JSON metadata report exactly `1.2.1` and the
   expected project links.
2. Download the wheel and sdist from PyPI and compare their SHA256 hashes with the
   successful publishing workflow's `SHA256SUMS` artifact.
3. In a fresh virtual environment, install
   `python -m pip install strategy-backtest-agent==1.2.1`, run `pip check`, and verify
   `strategy-backtest doctor`, `strategy-backtest --demo`, public `BacktestClient`
   import, offline backtest, and deterministic JSON/Markdown reports without
   credentials.
4. Verify `main` and dereferenced `v1.2.1` point to the same commit and confirm both
   the tag-validation and publishing GitHub Actions runs succeeded.

These are future release checks, not completed evidence for this candidate. No
GitHub merge, tag, OIDC publication, or PyPI upload is part of preparation.

## Local candidate verification — 2026-10-19

The reviewed customer documentation is included through the main baseline above.
Only package version metadata, current-version test fixtures, changelog and this
release procedure change for the candidate. `poetry.lock` needs no update;
`poetry check --lock` passes with unchanged dependency declarations.

| Command | Result |
| --- | --- |
| `poetry run pytest -q` | 1,425 passed in 9.14 seconds |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | 126 files already formatted |
| `poetry run mypy` | No issues in 120 source files |
| `poetry check --lock` | All set |
| `actionlint` | Passed |
| `poetry run strategy-backtest --demo` | Passed; final 123.09, return -98.77%, 45 trades, zero winners (existing synthetic baseline) |

The fresh isolated packaging run used the existing orchestration:

```bash
/private/tmp/sba-task21-packaging-tools/bin/python tests/packaging_ci.py \
  --checkout /Users/levanchangelia/projects/strategy-backtest-agent \
  --work /private/tmp/sba-release-1.2.1.CdA84z/validation
```

It passed isolated wheel/sdist builds, `python -m twine check --strict`, archive
inspection and separate Python 3.12 clean installations. The sdist was built by pip
from the supplied source archive with cache disabled. Both installations report
`strategy-backtest-agent 1.2.1`, import from their own site-packages, and pass `pip check`.
Public API/CLI, init/doctor, offline demo, raw JSON, deterministic JSON/Markdown reports,
repeatability, malformed-input and no-overwrite checks passed. Wheel/sdist outputs
match; application network attempts were zero. No live OpenAI or Binance request was
made. Tooling: Python 3.12.3, build 1.6.1, Twine 7.0.0, poetry-core 2.5.0.

| Local candidate artifact | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.2.1-py3-none-any.whl` | `6e5c68f3c6a4863bd5843b5a679e2d29b00cf7edb77103107cf11774f22dec19` |
| `strategy_backtest_agent-1.2.1.tar.gz` | `c6069cd2828350f129069ee9bf9638d60059f510d8ef6c3abbe62a560af643b0` |

Artifacts, logs and receipts stay outside Git in the validation directory above.
These are local candidate results, not a remote CI run, OIDC test, tag or publication.
The known direct natural-language DSL defect remains unchanged and is not represented
as fixed by the passing existing suite or installed smoke checks.

## Official guidance

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [Creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish)

</details>
