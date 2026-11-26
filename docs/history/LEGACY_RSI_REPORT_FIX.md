# Task #16 — Legacy RSI Markdown blocker resolution

**Status: READY — Task #16 blocker resolved for the corrected local candidates.**

## Confirmed cause and narrow fix

Continued `feat/pypi-packaging` from `05276df9d2a4ba168ead233b5998d91ce18edc63`.
Read the Task #16 Notion blocker without changing its status. The historical
[installation report](ISOLATED_INSTALL_REPORT.md) remains intact.

`reports/inputs.py` already accepts the legacy `LegacyCLISettings` shape emitted
by untouched `strategy-backtest --demo --json`. JSON report generation succeeds.
`reports/render.py` previously validated every strategy definition as a DSL
`RuleStrategy`, which rejects those legacy keys and requires `entry`/`exit`.

The fix changes only Markdown presentation: definitions with `name == "RSI"`
are validated with the existing `LegacyCLISettings` model and rendered as
`RSI(period) < entry_rsi` and `RSI(period) > exit_rsi`. All other definitions
follow the original DSL validation/formatting path. Existing Markdown escaping
still applies. There is no broad exception handler or conversion of source JSON
to DSL. Period 1 and other valid legacy periods are not constrained by DSL limits.

Input validation, evidence normalization, evidence hashes, JSON output, costs,
PnL, trading calculations, dependencies, version **1.0.0**, and package policy
are unchanged. No actual credentials or local research files were modified.
These candidates remain unpublished local artifacts, not a release.

## Regression coverage

`tests/test_legacy_demo_reports.py` adds six offline cases:

- End-to-end CLI demo JSON used verbatim as report input; both JSON and Markdown
  generated twice with identical output. Markdown accurately describes RSI(14)
  below 30 / above 70. Input bytes remain untouched.
- JSON byte SHA256 and normalized evidence SHA256 equal the historical Task #16
  baseline, proving this presentation fix does not change those outputs.
- Missing legacy fields, extra unsupported fields, unsupported strategy names and
  invalid periods remain rejected with exit 2 and no output or traceback.
- Existing DSL backtest Markdown snapshot remains byte-identical. The broader
  Markdown suite also verifies all six supported research types.

The existing opt-in `tests/installed_smoke.py` checks the actual installed CLI,
not reconstructed fixtures. Ordinary pytest performs no installation/download.

## Candidate builds and archive validation

Original Task #15 artifacts were preserved and rehashed:

| Original artifact under `dist/task15/` | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.0.0-py3-none-any.whl` | `a632e87bc80525876ae81f7d41ae7d50bb4d3fb371b8ccc0e2112222c4d11cc9` |
| `strategy_backtest_agent-1.0.0.tar.gz` | `fd3cb230a7db8105ff91429ebfeb1e5f74aabbe431033f1d41a6e51ae1e4707f` |

New candidates are in ignored `dist/task16-corrected/`:

| Corrected artifact | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.0.0-py3-none-any.whl` | `35610ab1d59bf853a4f40810e4fe7f2e69385967289f43fe07434ea1113c4a99` |
| `strategy_backtest_agent-1.0.0.tar.gz` | `8fa5cbc256b6acbd126295a710718b547fcb0c96ecd910137136462380554a9e` |

Tools: CPython **3.12.3**, build **1.6.1**, pip **24.0**, Twine **7.0.0**,
packaging **26.3**; isolated build backend **poetry-core 2.5.0** in both builds.
The temporary tools environment is independent of application environments.

Exact build/validation commands, from the checkout unless stated otherwise:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python -m build --sdist --wheel --verbose --outdir dist/task16-corrected
/private/tmp/sba-task15-2bjaudwn/tools/bin/python -m twine check --strict dist/task16-corrected/*
/private/tmp/sba-task15-2bjaudwn/tools/bin/python tests/distribution_check.py --project . dist/task16-corrected/*
```

All pass. Each archive contains 62 files and 57 runtime files, matching the
corrected checkout byte-for-byte. The existing inspector checks required legal,
README/metadata, entry points, dependencies and prohibited file paths. No actual
`.env`, research outputs, caches, bytecode, virtualenvs or nested artifacts occur.
The harmless `.env.example` remains sdist-only. Tests/examples are omitted under
the unchanged minimal distribution policy.

Extracted the corrected sdist using `tarfile.extractall(filter="data")` into
`/private/tmp/sba-task16-fixed-seg0t6if/source/strategy_backtest_agent-1.0.0`.
From that external directory, ran:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python -m build --wheel --verbose --outdir /private/tmp/sba-task16-fixed-seg0t6if/rebuilt
```

Validated the rebuilt wheel with:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python -m twine check --strict /private/tmp/sba-task16-fixed-seg0t6if/rebuilt/*.whl
/private/tmp/sba-task15-2bjaudwn/tools/bin/python tests/distribution_check.py --project . /private/tmp/sba-task16-fixed-seg0t6if/rebuilt/*.whl
```

Both pass. Its metadata, file inventory and runtime payload hashes match the direct
wheel. Full archive bytes also match in this run (SHA256 `35610ab1…13c4a99`);
this is not a guarantee across future builds or tool versions. Initial sandboxed
build attempts could not resolve the backend; authorized network retries succeeded.

## Fresh installed verification

Temporary workspace `/private/tmp/sba-task16-fixed-seg0t6if`; fresh `wheel-env`
and `sdist-env`, created with base Python 3.12 `-m venv`, no system site packages.
Each package was absent before installation. The temporary `install.py` controller
uses the same minimal credential-free environment as the historical verification,
with dotenv disabled, no inherited Python overrides and pip configuration disabled.
It invokes these exact commands from `setup-work`:

```bash
/private/tmp/sba-task16-fixed-seg0t6if/wheel-env/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir --use-pep517 --verbose --report /private/tmp/sba-task16-fixed-seg0t6if/wheel-install.json /Users/levanchangelia/projects/strategy-backtest-agent/dist/task16-corrected/strategy_backtest_agent-1.0.0-py3-none-any.whl
/private/tmp/sba-task16-fixed-seg0t6if/sdist-env/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir --use-pep517 --verbose --report /private/tmp/sba-task16-fixed-seg0t6if/sdist-install.json /Users/levanchangelia/projects/strategy-backtest-agent/dist/task16-corrected/strategy_backtest_agent-1.0.0.tar.gz
```

Both exit 0. Sdist logs show an isolated poetry-core 2.5.0 installation and a
successful project wheel build; pip's direct URL metadata records the corrected
source archive and hash. No editable installation or project-wheel cache is used.
Resolved dependency versions match the historical report's complete version table.

The installed smoke commands are:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tests/installed_smoke.py --venv /private/tmp/sba-task16-fixed-seg0t6if/wheel-env --work /private/tmp/sba-task16-fixed-seg0t6if/wheel-work --checkout /Users/levanchangelia/projects/strategy-backtest-agent > /private/tmp/sba-task16-fixed-seg0t6if/wheel-receipt.json
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tests/installed_smoke.py --venv /private/tmp/sba-task16-fixed-seg0t6if/sdist-env --work /private/tmp/sba-task16-fixed-seg0t6if/sdist-work --checkout /Users/levanchangelia/projects/strategy-backtest-agent > /private/tmp/sba-task16-fixed-seg0t6if/sdist-receipt.json
```

These run each environment's explicit executable from its fresh external working
directory: `--help`, `--demo`, `report --help`, `--demo --json`, repeated JSON and
Markdown reports using `--input`, `--format`, `--output`, JSON-only stdout and a
malformed-input negative case. No report `--demo` flag or checkout research inputs
are used. The harness verifies site-packages imports, console target/shebang,
non-editable provenance, no checkout in Python paths, and `pip check`.
It installs and removes its own temporary socket-denying startup guard;
application code is unmodified and credentials/dotenv remain unavailable.

## Installed results

Both harness runs exit **0**, status **READY**, no report failures. Both installed
versions are **strategy-backtest-agent 1.0.0**, with console target
`strategy_backtest_agent.cli:main`; `pip check` prints
`No broken requirements found.` Imports resolve respectively to:

```text
/private/tmp/sba-task16-fixed-seg0t6if/wheel-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
/private/tmp/sba-task16-fixed-seg0t6if/sdist-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
```

The demo still produces initial balance 10000, final balance
123.09493440255116, return -98.76905065597448%, 45 trades and zero winning trades.
Source-backed metrics retain their exact values; net PnL remains final minus
initial balance. This synthetic demonstration is not a profitability example.

Repeated JSON and Markdown outputs are byte-identical, including across the two
installations. Markdown is non-empty (**4614 bytes**) and describes RSI(14) entry
below 30 and exit above 70. JSON and normalized evidence retain historical hashes:

| Content | SHA256 (both installations) |
| --- | --- |
| JSON report (unchanged) | `52173551a777f1e15b19bfba9688b14a662eef79c4a3d4c5915c4b16ff933ea3` |
| Normalized evidence (unchanged) | `bbfe64bc4e91ebb17942501c4b11ca13bdc5f02ea6c9ad150cbcf0925cc47c48` |
| Markdown report | `7ac0c7bcb02f4f5dd22ec542f8f6267b4fc11a92ba3e4a6dd37a3b4820373743` |

Malformed JSON still exits 2 with `Error: invalid UTF-8 JSON or excessive nesting`,
empty stdout and no traceback or synthetic private-marker echo. Both socket audit
logs are empty after the guard self-test: **zero application network attempts**.
All 17 original local research files match their original hashes, and the real
`.env` retains its inode, size and modification time. Original Task #15 artifact
hashes match the recorded historical values. No real OpenAI request was tested.

## Quality checks

| Exact command | Result |
| --- | --- |
| `poetry run pytest -q` | **1289 passed in 7.99s** |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 110 files |
| `poetry run mypy` | Passed; 109 source files |
| `poetry check --lock` | Passed; `All set!` |

No push, merge, tag, publication, version change, Notion status update, CI
implementation, live OpenAI or market-data test is performed. Task #17 CI
Packaging Validation remains separate work; cross-platform/Python coverage and
existing POSIX output limitations remain unchanged.
