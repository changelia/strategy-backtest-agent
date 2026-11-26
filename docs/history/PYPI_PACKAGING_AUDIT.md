# PyPI namespace and package metadata audit — Task #14

Status: AUDIT COMPLETE. Configuration is coherent enough to proceed to Task #15;
no build-configuration blocker was confirmed. Distribution contents and clean
installation are not verified, so this is not approval to publish.

## Baseline and scope

- Audited main: `b6bb6e6d1197c7f68516347012ee3ca84840fe01`, including automatic
  dotenv loading. Local main, origin/main and a read-only remote main lookup agreed.
- Working branch: `feat/pypi-packaging`, newly created from that main. Initial
  tracked tree was clean; existing untracked research files and ignored dotenv
  files were left untouched. Existing worktrees were retained.
- No applicable `AGENTS.md` was found in the repository or ancestor directories.
  Root-level reports such as [WALK_FORWARD_AUDIT.md](WALK_FORWARD_AUDIT.md) establish
  the documentation convention used here. The linked Notion task was read only;
  its status was not updated. The explicit documentation-only scope supersedes
  its generic instruction to add implementation tests.
- Inspection only: no wheel/sdist, generated package metadata, clean installation,
  dependency updates, packaging CI, credential changes or publication performed.

## Current configuration and findings

| Area | Evidence and assessment |
| --- | --- |
| Names and layout | [pyproject.toml](pyproject.toml), lines 2, 11–12: distribution `strategy-backtest-agent`; import package `strategy_backtest_agent` under `src/`, with `__init__.py` and 57 tracked Python files. Explicit discovery selects that package and its subpackages for both formats. Hyphens in a distribution and underscores in an import are consistent. |
| Version | `pyproject.toml:3` declares `1.0.0`, matching README's released version. Task #14 belongs to planned v1.1.0 work; it does not authorize a version bump. No competing source `__version__` was found. |
| Summary and README | `pyproject.toml:4,7` supplies a short description and `README.md`. Markdown long-description configuration is appropriate. README accurately documents the `strategy-backtest` CLI, Poetry checkout workflow, dotenv precedence and historical-research limitations. Relative links/config examples assume a source checkout; do not imply those files will exist after a wheel installation. |
| License | `pyproject.toml:6` declares MIT; [LICENSE](LICENSE) contains MIT terms and the existing copyright attribution. No license choice is needed. The table form is accepted by current checks, although current Poetry documentation deprecates it in favor of an SPDX string. Any later modernization must check the minimum poetry-core version and preserve the existing license. |
| Authors and URLs | `pyproject.toml:5` is `authors = []`; project/maintainer URL metadata is absent. These are metadata-quality gaps, not a confirmed build failure. Obtain owner-approved attribution or omit optional author data; do not infer it from the copyright line. Repository/issues URLs can reference the existing GitHub project. |
| Python | `pyproject.toml:8,15`: `>=3.12,<4.0` and `^3.12` agree. Local checks use CPython 3.12.3 on macOS; CI covers Python 3.12 on Ubuntu only. This does not establish support for every later Python 3.x or OS. Report file output has documented POSIX requirements (`reports/cli.py:16–40`). |
| Build backend | `pyproject.toml:31–33`: PEP 517 `poetry.core.masonry.api`, requiring `poetry-core>=2.0.0,<3.0.0`. No custom build script or compiled project extension is declared. Backend requirements are separate from runtime dependencies and are not pinned by the application lock. |
| Runtime dependencies | `pyproject.toml:14–20`: pandas `^2.2`, httpx `^0.28`, pydantic `^2.10`, openai `^3.24.0`, python-dotenv `^1.2.4`. Dynamic project dependencies are supplied through Poetry's dependency section. No local-path/VCS dependency or custom package index is declared. |
| Development dependencies | `pyproject.toml:22–26` separately groups pytest, Ruff, mypy and pandas-stubs. They are development tools, not intended runtime requirements. Verify emitted `Requires-Dist` in Task #15; a consumer normally resolves declared ranges rather than inheriting this lock. |
| Optional AI behavior | The SDK is a mandatory installation dependency today, while using AI/credentials remains optional. Deterministic reports and demo work offline. Preserve this distinction and existing lazy request behavior; adding extras or changing dependencies is not required by this audit. |
| CLI | `pyproject.toml:28–29` points to the existing `strategy_backtest_agent.cli:main`. `cli.py:148–150` loads dotenv before dispatch. Checkout help/demo and the existing CLI regression suite pass; this does not prove a wheel-created executable works. |
| Lock consistency | `poetry check --lock` exits 0 with `All set!`. Lock version is 2.1, Python constraint `^3.12`, content hash `d5350bf5ff777c419bb4a77a1500ad085c1d4409e47c39c8c860f04507d96f00`. Runtime/dev groups agree with the project declarations. Neither file was changed. |
| Local environment mismatch | Read-only `importlib.metadata` inspection reports installed editable distribution version **0.7.0**, linked to this checkout, while source metadata declares **1.0.0**. This predates the documentation edit. It is stale installed metadata, not evidence that a newly built artifact would have the wrong version. Do not use this environment as proof of packaging/install correctness. No reinstall was performed. |
| CI and release checks | [.github/workflows/ci.yml](.github/workflows/ci.yml), lines 1–19: push/PR workflow, read-only repository permission, Poetry 2.1.4, Ubuntu/Python 3.12, install, Ruff, format, mypy and pytest. It has no build, archive inspection, clean install, metadata validation/upload or publishing job. Demo/help are manual checks here. Existing release notes do not replace distribution checks. |

## PyPI namespace evidence

Checked on **2026-10-18**, using unauthenticated HTTPS **GET** requests via curl,
with TLS verification and redirects enabled. The web-fetch tool initially could
not retrieve the JSON URL; the following direct HTTP results completed the check.

| UTC request timestamp | Exact official URL | Observed result |
| --- | --- | --- |
| 2026-10-18T05:51:41.350852Z | https://pypi.org/pypi/strategy-backtest-agent/json | HTTP 404; `{"message": "Not Found"}` |
| 2026-10-18T05:51:41.819042Z | https://pypi.org/pypi/strategy_backtest_agent/json | HTTP 404; same JSON response |
| 2026-10-18T05:51:42.012749Z | https://pypi.org/simple/strategy-backtest-agent/ | HTTP 404; `404 Not Found` |

Exact distribution name: **strategy-backtest-agent**. Its normalized name is
unchanged. `strategy_backtest_agent`, `strategy.backtest.agent` and case variants
map to the same namespace: lowercase and collapse runs of hyphen/underscore/dot,
as specified by [PyPA](https://packaging.python.org/en/latest/specifications/name-normalization/).
The JSON endpoint follows the [official PyPI API](https://docs.pypi.org/api/json/).

Conclusion: no public project was visible under the normalized name at that time;
no observed name conflict requires alternatives or renaming. **A missing project
does not guarantee registration**: name restrictions/reservations, account policy
and changes after this check remain possible. Nothing was reserved or published.
Recheck immediately before a separately authorized publication.

## Distribution content assessment

These are configuration-based expectations, not archive-content verification.
The installed Poetry 2.1.4 backend source (poetry-core 2.1.3) was read without
invoking build hooks. Its defaults add README/project/legal files to the sdist
and legal files/README-derived metadata to the wheel. The declared backend range
can resolve another 2.x release, so Task #15 must record the backend actually used.

- `pyproject.toml:11–12` selects only the source package; there are no explicit
  `include`/`exclude` lists or broad repository globs. Runtime files inspected are
  Python modules; no required bundled external data file was identified. Engines
  take caller-provided config/data paths, not repository-relative runtime assets.
- README is explicitly configured; root LICENSE matches backend legal-file
  defaults. A standalone README file in a wheel is not promised; its text should
  become package metadata. Verify both archive forms and license placement later.
- [.gitignore](.gitignore), lines 1–24, excludes `.env`, `.env.*`, caches,
  bytecode, virtualenv/build directories and egg-info. `.env.example` is the sole
  tracked dotenv template. No actual `.env` is tracked; credential contents were
  not inspected. Poetry uses VCS ignores when available, but Git ignore rules
  are not an independent security guarantee outside a Git checkout.
- Root untracked research JSON/Markdown outputs are outside the selected package
  and are not explicitly included. They are not generally ignored, however.
  An accidentally copied sensitive/non-runtime file **inside** the source package
  can be eligible, particularly without Git exclusions. Add deliberate packaging
  exclusions/manifest checks before distribution; do not blanket-exclude all JSON.
- `examples/`, tests/fixtures, audit docs, CHANGELOG and other repository artifacts
  are not explicitly selected. They are not runtime dependencies. Decide whether
  examples/tests should accompany the **sdist**; keep unrelated files out of the
  wheel. Do not broadly include the repository just to supply README links.
  Lock-file inclusion is not explicitly requested and would not constrain normal
  wheel dependency resolution in any event.

See [Poetry's packaging rules](https://python-poetry.org/docs/pyproject/#exclude-and-include)
for format-specific inclusion/exclusion. Actual contents, bytecode/secret absence,
README rendering and generated dependency/entry-point metadata remain unverified.

## Blockers and minimal next actions

**Packaging:** no confirmed configuration error blocks starting Task #15.
Acceptance of distributions is pending explicit content policy and actual archive
inspection; passing checkout tests or the stale editable install is insufficient.

**Publication:** not approved or ready to attest. Archive/metadata inspection and
subsequent clean-install validation are outstanding; namespace registration and
publisher/account authorization are unverified. Credentials were neither inspected
nor modified. PyPI authentication/publishing setup belongs to later authorized work.

Recommended minimal Task #15 work:

1. Keep distribution/import names, version, runtime behavior and dependency choices
   unchanged unless separately authorized. Define narrow format-specific content
   rules, independent exclusions for secrets/caches/local outputs, and an explicit
   decision about sdist examples/tests/license inclusion.
2. Add known repository/issues URLs; obtain author details from the owner if desired.
   Empty authors, short summary, classifiers/keywords and modern license notation
   are optional polish, not reasons to invent identity, change license or widen scope.
3. Build wheel and sdist in Task #15, record backend/version, and inspect paths plus
   generated name/version, README, license, Python/dependency requirements and
   console entry point. Verify no secret/local output/cache artifacts leaked.
4. Record clean installation, Python/OS coverage, packaging CI and final PyPI
   registration checks as later publication gates. Do not implement init/doctor,
   expand Quick Start, add optional-AI extras or publish during this audit.

## Quality evidence

All commands ran against the audited checkout using Poetry 2.1.4 / CPython 3.12.3.
No tests were added for this documentation-only task. No quality gate failed.

| Exact command | Result |
| --- | --- |
| `poetry run pytest` | Exit 0; **1198 passed in 7.55s** |
| `poetry run ruff check .` | Exit 0; `All checks passed!` |
| `poetry run ruff format --check .` | Exit 0; `105 files already formatted` |
| `poetry run mypy` | Exit 0; `Success: no issues found in 104 source files` |
| `poetry run strategy-backtest --demo` | Exit 0; synthetic 180-day demo: initial 10000, final 123.09, return -98.77%, 45 losing trades, net Buy & Hold +6.98%. Expected regression example, not profitability evidence. |
| `poetry run strategy-backtest --help` | Exit 0; `strategy-backtest` options and AI invocation shown. |
| `poetry check --lock` | Exit 0; `All set!` |

These checks exercise the source checkout, not built distributions. No real market
or OpenAI requests, installation tests or publishing actions were performed.
