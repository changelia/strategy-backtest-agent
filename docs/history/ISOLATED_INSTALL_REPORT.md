# Isolated installation verification — Task #16

**Status: BLOCKED** by installed Markdown reporting of legacy demo results.
Wheel installation, source installation, CLI demo, JSON reports and isolation pass.
Do not treat this as readiness for Task #17 or publication.

## Scope and repository

Checked on 2026-10-18, macOS / CPython **3.12.3**. Continued
`feat/pypi-packaging` from reviewed commit
`543b15e73a06de95b0e1d605189279798d8b7795`, containing Task #14 and Task #15.
No applicable `AGENTS.md` was found. Read
[the packaging audit](PYPI_PACKAGING_AUDIT.md) and
[the distribution report](DISTRIBUTION_BUILD_REPORT.md).
No tracked changes existed at the start. No production code, package metadata,
lock file, dependencies, calculation, version, credentials or Notion status changed.
The final commit is the Conventional Commit introducing this report and its harness.

Task-owned files:

- `tests/installed_smoke.py`: explicitly invoked, standard-library-only installed
  CLI checks; no builds or installs during pytest. It records failures and exits 1
  if an installed report format fails, rather than substituting fixtures.
- `tests/test_installed_smoke.py`: 14 offline cases covering credential/path
  isolation, baseline tolerances and financial regressions, source provenance,
  missing/incorrect evidence and safe working-directory requirements.
- This report records the observed blocker and successful checks.

All 17 existing untracked research JSON/Markdown files retain their original
SHA256 values. The real `.env` retains its inode, size and modification time;
its contents were not printed. No existing worktree was removed or changed.

## Reviewed artifacts

Both original files exist under `dist/task15/` and matched the expected SHA256
**before installation**; neither was rebuilt, replaced or changed:

| Artifact | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.0.0-py3-none-any.whl` | `a632e87bc80525876ae81f7d41ae7d50bb4d3fb371b8ccc0e2112222c4d11cc9` |
| `strategy_backtest_agent-1.0.0.tar.gz` | `fd3cb230a7db8105ff91429ebfeb1e5f74aabbe431033f1d41a6e51ae1e4707f` |

## Temporary environments and commands

Workspace: `/private/tmp/sba-task16-mqx029yn` (retained for review).
Separate environments: `wheel-env` and `sdist-env` beneath that workspace.
Final application working directories: `wheel-verified` and `sdist-verified`.
Both environments were created without system site packages. Before installation,
`importlib.util.find_spec('strategy_backtest_agent')` was `None` in each.

Exact setup commands (run from the checkout):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv /private/tmp/sba-task16-mqx029yn/wheel-env
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv /private/tmp/sba-task16-mqx029yn/sdist-env
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 /private/tmp/sba-task16-mqx029yn/install.py wheel
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 /private/tmp/sba-task16-mqx029yn/install.py sdist
```

The temporary `install.py` controller executes the following two commands from
`setup-work`, passing only `PATH=os.defpath`, `PYTHON_DOTENV_DISABLED=1`,
`PYTHONNOUSERSITE=1`, `PIP_CONFIG_FILE=/dev/null` and
`PIP_DISABLE_PIP_VERSION_CHECK=1` as the subprocess environment:

```bash
/private/tmp/sba-task16-mqx029yn/wheel-env/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir --use-pep517 --verbose --report /private/tmp/sba-task16-mqx029yn/wheel-install.json /Users/levanchangelia/projects/strategy-backtest-agent/dist/task15/strategy_backtest_agent-1.0.0-py3-none-any.whl
/private/tmp/sba-task16-mqx029yn/sdist-env/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir --use-pep517 --verbose --report /private/tmp/sba-task16-mqx029yn/sdist-install.json /Users/levanchangelia/projects/strategy-backtest-agent/dist/task15/strategy_backtest_agent-1.0.0.tar.gz
```

Both installations exit 0. The initial sandboxed wheel attempt could not resolve
PyPI DNS; the authorized network retries above succeeded. This was an installation
network restriction, not an application or dependency-resolution failure.

Both use pip **24.0**. The sdist log records an isolated build dependency install
of **poetry-core 2.5.0**, followed by `Building wheel for strategy-backtest-agent
(pyproject.toml): finished with status 'done'` and `Successfully built
strategy-backtest-agent`. `--no-cache-dir` prevents project-wheel cache reuse.
The pip installation report and installed `direct_url.json` identify the supplied
tarball and its expected hash, not a previously built wheel.

Exact final harness invocations (exit 1 intentionally records the Markdown blocker):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tests/installed_smoke.py --venv /private/tmp/sba-task16-mqx029yn/wheel-env --work /private/tmp/sba-task16-mqx029yn/wheel-verified --checkout /Users/levanchangelia/projects/strategy-backtest-agent > /private/tmp/sba-task16-mqx029yn/wheel-verified-receipt.json
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tests/installed_smoke.py --venv /private/tmp/sba-task16-mqx029yn/sdist-env --work /private/tmp/sba-task16-mqx029yn/sdist-verified --checkout /Users/levanchangelia/projects/strategy-backtest-agent > /private/tmp/sba-task16-mqx029yn/sdist-verified-receipt.json
```

The harness requires a fresh directory. Use new work-directory names for reruns;
it does not overwrite previous results. Base Python orchestrates subprocesses;
only each environment's explicit Python and console executable run the application.
No editable install, `--no-deps`, Poetry execution or development package is used.

## Isolation and installed commands

Both installed distributions are **strategy-backtest-agent 1.0.0**.
Import locations respectively:

```text
/private/tmp/sba-task16-mqx029yn/wheel-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
/private/tmp/sba-task16-mqx029yn/sdist-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
```

`python -I -c <PROBE>` (full probe in the harness) verifies `sys.prefix`, disabled
user/system site packages, no checkout paths in `sys.path` or `.pth` files,
archive-based non-editable provenance, and the loadable console target
`strategy_backtest_agent.cli:main`. Each executable is its own environment's
`bin/strategy-backtest`, with that environment's Python in its shebang.
The original archive URL in `direct_url.json` is provenance, not a source-tree
runtime dependency. Both `python -m pip check` commands print
`No broken requirements found.`; `python -m pip list --format=json` records versions.

The harness replaces rather than copies the inherited environment: no
`PYTHONPATH`, `PYTHONHOME`, OpenAI/Binance credentials, user pip configuration or
virtualenv markers are inherited. Dotenv is disabled; application cwd is outside
the checkout. No global shell configuration or real `.env` is changed.
A temporary venv-local `sitecustomize.py` denies DNS/connect/sendto audit events,
with a synthetic audit-event self-test before running the application. It records
**zero socket attempts** in either workflow and is removed afterward. No installed
application module is modified. Only dependency installation accesses PyPI.

With `CLI` set to each environment's explicit `bin/strategy-backtest`, the harness
runs these exact argument sequences from that environment's work directory:

```bash
"$CLI" --help
"$CLI" --demo
"$CLI" report --help
"$CLI" --demo --json
"$CLI" report --input "$WORK/demo.json" --format json --output "$WORK/report-first.json"
"$CLI" report --input "$WORK/demo.json" --format json --output "$WORK/report-repeat.json"
"$CLI" report --input "$WORK/demo.json" --format markdown --output "$WORK/report-first.markdown"
"$CLI" report --input "$WORK/demo.json" --format markdown --output "$WORK/report-repeat.markdown"
"$CLI" report --input "$WORK/demo.json" --format json
"$CLI" report --input "$WORK/malformed.json" --format json
```

Help, demo and report help exit 0. The demo JSON has initial balance **10000**,
final balance **123.09493440255116**, return **-98.76905065597448%**,
**45** trades and **0** winning trades in both installs. Assertions use numerical
tolerances, not formatted strings. This synthetic demonstration is not a
profitability example.

## Reports, determinism and blocker

JSON reports succeed without OpenAI credentials. They contain schema/version,
normalized evidence, source provenance and observations, with status
`deterministic` and null AI interpretation. Source-backed financial values match
the input exactly; derived net PnL equals final minus initial balance. Nulls are
preserved. The source-byte digest matches the untouched installed demo output.
Repeated JSON reports match byte-for-byte; wheel and sdist outputs also match.

| Output | SHA256 (both installations) |
| --- | --- |
| Demo JSON | `bf8fcaa95a48b3a153aa54a320e2b78e11fc1650c879b1b5e548a6706be692be` |
| Report JSON | `52173551a777f1e15b19bfba9688b14a662eef79c4a3d4c5915c4b16ff933ea3` |
| Normalized evidence | `bbfe64bc4e91ebb17942501c4b11ca13bdc5f02ea6c9ad150cbcf0925cc47c48` |

**Markdown fails twice in each installation**, exit 2, no output file:

```text
Error: Unsupported/corrupted research schema at entry, exit, name, rsi_period, entry_rsi, exit_rsi, fee. Supply complete v0.9 CLI --json output.
```

Cause: the demo serializes a valid legacy RSI strategy with `name`, `rsi_period`,
`entry_rsi`, `exit_rsi`, `fee`. `reports/inputs.py:32–37,56` explicitly accepts
this shape, and JSON evidence generation succeeds. However,
`reports/render.py:262` unconditionally calls `RuleStrategy.model_validate` on
each strategy definition, requiring DSL `entry` and `exit` while rejecting the
legacy keys. This code is already in the reviewed artifacts and predates Task #16;
no installed dependency or packaging-file change caused it.

Smallest proposed fix: add explicit legacy RSI presentation handling in the
Markdown strategy formatter, preserving normalized evidence and financial values,
and add a regression using untouched `--demo --json` output. Do not weaken input
validation or alter the input to hide the failure. This production fix and rebuilt
artifacts require a follow-up; none were substituted in this verification.
Markdown completeness/reproducibility therefore **cannot be certified** here.

Malformed JSON exits **2** with `Error: invalid UTF-8 JSON or excessive nesting`,
empty stdout, no traceback and no echo of the synthetic private input marker.
No real credentials are supplied or exposed. This negative case passes in both.

## Quality and next task

| Exact command | Result |
| --- | --- |
| `poetry run pytest -q` | **1283 passed** |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 109 files formatted |
| `poetry run mypy` | Passed; 108 source files |
| `poetry check --lock` | Passed; `All set!` |
| Both clean pip installations | Passed |
| Both installed help/demo/report-help workflows | Passed |
| Both installed deterministic JSON report workflows | Passed |
| Both installed Markdown report workflows | **Failed as described above** |

The ordinary pytest suite remains offline and does not rebuild/install environments;
its green result does not supersede the opt-in installed CLI failure.
Before Task #17 CI Packaging Validation, fix the formatter, rebuild/revalidate new
artifacts explicitly with new hashes, then rerun both installed workflows. Future
CI should retain the untouched demo-to-report check for both formats. No live AI,
Binance, other OS or additional Python version was tested. Dependency versions
below are a dated resolver outcome, not the Poetry lock or a supported-version
matrix. No CI, init/doctor, Quick Start or publication work was implemented.

## Resolved versions

Identical in both clean environments; runtime dependency choices were unchanged.
`pip` is installation tooling; poetry-core existed only in the isolated build.

| Installed distribution | Version |
| --- | --- |
| annotated-types | 0.8.0 |
| anyio | 4.15.1 |
| certifi | 2026.7.22 |
| h11 | 0.16.0 |
| httpcore | 1.0.9 |
| httpcore2 | 2.13.1 |
| httpx | 0.28.1 |
| httpx2 | 2.13.1 |
| idna | 3.20 |
| jiter | 0.17.0 |
| numpy | 2.5.4 |
| openai | 3.35.1 |
| pandas | 2.3.3 |
| pip | 24.0 |
| pydantic | 2.14.1 |
| pydantic_core | 2.50.1 |
| python-dateutil | 2.9.0.post0 |
| python-dotenv | 1.2.4 |
| pytz | 2026.5 |
| six | 1.17.0 |
| sniffio | 1.3.1 |
| strategy-backtest-agent | 1.0.0 |
| truststore | 0.10.5 |
| typing_extensions | 4.16.0 |
| typing-inspection | 0.4.4 |
| tzdata | 2026.5 |
