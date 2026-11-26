# Task #19 — CLI doctor and diagnostics

**STATUS: READY** — local source and installed-package verification passed.

## Baseline and interface

Started on verified `main`, local `origin/main` and public HTTPS remote main at
`b1ab625ce2af596454e89926c9941ed518be1e2b`; created `feat/cli-doctor`. Initial
tracked tree was clean; existing untracked research files, dotenv files and
worktrees were preserved. Read applicable ancestor/repository instructions (none
found) and the Notion task without changing its status. The baseline remote lookup
required authorized network access because sandbox DNS was restricted:

```bash
git ls-remote https://github.com/changelia/strategy-backtest-agent.git refs/heads/main
```

Final interface:

```bash
strategy-backtest doctor
strategy-backtest doctor --type compare --config comparison-config.json
strategy-backtest doctor --help
```

`--type` and `--config` must appear together. Types match init:
`backtest`, `compare`, `validate`, `walk-forward`. No schema guessing or research-file
scanning occurs. An explicit file is bounded to the existing 16 MiB input limit,
required to be a regular file, and validated using the existing corresponding
`BacktestConfig`, `ComparisonConfig`, `ValidationConfig` or `WalkForwardConfig`.
No new configuration schema, JSON-output mode, repairs or setup wizard is added.

## Diagnostic meanings and exit codes

- Python version and compatibility with the project's declared `>=3.12,<4.0`
  contract. This is not a general PEP 440 implementation: unfamiliar requirement
  metadata is reported as unverified and fails rather than being guessed.
  A regression test requires the code's contract to match pyproject.toml.
- Installed distribution metadata and checkout metadata are distinct. Source
  metadata comes only from this module's actual `src` checkout, not arbitrary cwd
  projects. Normal wheels have no source checkout metadata. Missing metadata is
  reported honestly; no version is invented. Mismatches warn about stale/editable
  metadata without relabeling the installed version as the source version.
- Dotenv discovery/loading reports missing, disabled, found/parsed, no assignments,
  malformed or unreadable states without paths or raw file contents.
- Key presence/source and model override/default state only. No key fragments,
  lengths, fingerprints or override values are printed. The public shared model
  default is imported from the existing AI parser, not duplicated.
- Explicit config checks validate the selected model only. Without a supplied file,
  doctor says no research configuration was checked. No dataset, execution or
  financial result is validated by this schema check.
- Bounded offline self-check verifies imports and generates 24 existing synthetic
  candles. It never executes research, calls OpenAI/Binance, lists models, verifies
  funds/authorization, or runs an automatic repair.

| Exit | Meaning |
| --- | --- |
| **0** | Checked offline capabilities available. Missing `.env`, missing/empty credentials and unavailable optional AI do not fail. Metadata absence/mismatch alone warns rather than blocking offline use. |
| **1** | Python compatibility unverified/incompatible, dotenv parsing/loading error, explicit config error or offline self-check failure. An available bounded offline check does not erase a separate configuration error. |
| **2** | Invalid arguments, including an unpaired `--type`/`--config` or unsupported type. |

Key presence does not establish validity, funding or authorization. A model
setting does not establish provider availability. Offline self-check success does
not certify every workflow, dependency installation, historical dataset or strategy.

## Files and behavior preservation

- `src/strategy_backtest_agent/doctor.py`: read-only diagnostics, safe argument
  errors, controlled dotenv logging, metadata handling and optional explicit
  schema checks. Reads config/provenance; never writes configuration files.
- `src/strategy_backtest_agent/cli.py`: doctor dispatch before the generic loader,
  so doctor can sanitize discovery/loading errors itself. Other commands retain
  the exact existing `find_dotenv(usecwd=True)` / `load_dotenv(override=False)` path.
- `tests/test_doctor.py`: 41 hermetic cases covering missing/disabled/empty dotenv,
  single load and ancestor discovery, shell precedence including empty values,
  credential/model redaction, parser/validation/metadata error sanitization,
  installed/source separation, Python checks, explicit configs, no implicit reads,
  no config modification, offline failure and blocked sockets. Synthetic markers
  are used; tests never depend on real credentials or editable metadata.
- `tests/installed_smoke.py`: bare doctor, valid explicit config and malformed
  config diagnostics in both clean environments. Diagnostic text is retained only
  in temporary logs and is **not compared byte-for-byte across installations**.
  Existing init and deterministic JSON/Markdown checks remain intact.
- `README.md`: concise syntax, scope, limitations and exit codes.
- This report records local verification and remaining limits.

Doctor's own loader uses standard python-dotenv discovery and `override=False`.
Already-set shell/process variables retain precedence independently for key/model,
including empty values. The same truthy values disable dotenv as in python-dotenv.
Disabled loading skips discovery and file access. Logging is temporarily contained
so untrusted parser messages cannot reach stdout/stderr or parent logging handlers;
previous logging state is restored. Exceptions/validation inputs are not formatted.
Loading can populate this process environment normally; no dotenv file or global
shell configuration is modified. No financial calculations, version (**1.0.0**),
dependency policy, source report evidence or historical metrics change.

## Commands and local quality

Local host: macOS arm64 / CPython 3.12.3. Exact commands:

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
env -u OPENAI_API_KEY -u OPENAI_MODEL PYTHON_DOTENV_DISABLED=1 poetry run strategy-backtest doctor
env -u OPENAI_API_KEY -u OPENAI_MODEL PYTHON_DOTENV_DISABLED=1 poetry run strategy-backtest doctor --help
```

Results: **1379 tests passed in 9.03s** (1338 baseline + 41 new); Ruff passed,
116 files already formatted, mypy passed for 115 source files, lock check
`All set!`. Existing dotenv precedence, init, AI mocks, JSON/evidence, legacy RSI
Markdown, financial and CLI regressions remain passing. Ordinary pytest performs
no downloads or installs.

The actual development installation reports **0.7.0 installed** versus **1.0.0
source**. Doctor labels both and warns about stale/editable metadata; it does not
change the installation or treat that old version as the checkout version.

Additional seven manual scenarios run via a temporary synthetic-only controller:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 /private/tmp/sba-task19-qqy_zk8h/manual_scenarios.py
```

It launches the explicit development CLI with stdin closed from seven separate
external working directories and a minimal environment. Missing dotenv, dotenv-only
key, shell-only key, conflicting shell/file keys, empty shell key and disabled
loading all exit 0; malformed dotenv exits 1. Synthetic markers are absent from
stdout/stderr and files remain unchanged. Outputs/results are under
`/private/tmp/sba-task19-qqy_zk8h/manual`. No real credentials are copied.

## Fresh distribution and installed verification

Exact sequence:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python tests/packaging_ci.py \
  --checkout /Users/levanchangelia/projects/strategy-backtest-agent \
  --work /private/tmp/sba-task19-qqy_zk8h/packaging
```

This builds new wheel/sdist in `packaging/artifacts`, runs strict Twine and the
existing archive inspector, then installs them into `packaging/wheel-env` and
`packaging/sdist-env` with separate external `wheel-work`/`sdist-work` directories.
Pip installs the supplied source archive with `--no-cache-dir --use-pep517` and
logs its isolated backend and fresh project-wheel build. Neither install is editable
or executes the application through Poetry/the original checkout.

Build/installation can download declared dependencies; installed application
checks run with credentials/Python overrides removed, dotenv disabled, stdin closed
and the temporary socket-denying startup guard. Bare doctor must exit 0 and report
its installed version, absent key and bounded offline availability; malformed
explicit config must exit 1, and a generated valid backtest config must pass.
All prior installed CLI/demo/init/report, reproducibility, provenance and negative
checks remain required by the orchestration.

Tools: Python 3.12.3, pip 24.0, build 1.6.1, Twine 7.0.0, packaging 26.3;
isolated build backend poetry-core 2.5.0. Artifacts, venvs, synthetic files and
logs stay outside Git; previous Task #15–18 artifacts are not replaced.

## Final installed results

The full orchestration exits **0**, with both receipts **READY**. Doctor exits **0**
without credentials, **1** for malformed explicit configuration, and **0** for a
valid generated backtest config. It reports the actual installed version **1.0.0**,
disabled dotenv loading, absent key and bounded offline availability. No source
checkout metadata is invented in a wheel. Import paths are respectively:

```text
/private/tmp/sba-task19-qqy_zk8h/packaging/wheel-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
/private/tmp/sba-task19-qqy_zk8h/packaging/sdist-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
```

Both `pip check` runs report `No broken requirements found.` Existing help, offline
demo, report-help, all four installed init workflows, overwrite refusal, deterministic
JSON/Markdown reports and malformed-input checks pass. Demo/config/report results
match across wheel/sdist and reports repeat byte-for-byte; doctor text is not used
in these comparisons. Both socket audit logs show **zero application network
attempts**. The normal demo's financial baseline and normalized evidence hash are
unchanged. No live OpenAI request was tested.

Strict metadata and archive inspection pass for both fresh artifacts: each contains
64 files, including 59 runtime files matching current checkout bytes. README-derived
metadata, license, dependency requirements and CLI entry point are correct. Actual
credentials, research files, caches, environments and unrelated artifacts are absent.
No packaging inclusion rules changed; the new doctor module is included by existing
runtime discovery. Isolated sdist installation logs a successful new wheel build.

| Artifact under `packaging/artifacts/` | SHA256 |
| --- | --- |
| strategy_backtest_agent-1.0.0-py3-none-any.whl | `4cfbba10d819dd75d3d32d3c1ac857f2842390d741b570fc9e938f45bd0f2132` |
| strategy_backtest_agent-1.0.0.tar.gz | `cd5c8781a9ec2d149704a2a315c2ba5de728b4686c610f620f0bda63e0c4f472` |

The 17 original research files retain their hashes; `.env` retains its inode, size
and modification time. Only task-owned source, tests and documentation are staged.

## Remaining concerns

No remote GitHub workflow was triggered; the extended installed checks will run
on a future authorized PR/main workflow. Local coverage is macOS/Python 3.12,
not a broader platform/version guarantee. Doctor assumes the CLI and its required
imports can start; it is not a substitute for `pip check` or full installed smoke
verification. Optional provider availability and real credentials remain untested.
Metadata strings are conservatively displayed or marked unrecognized; future
changes to Python requirements require corresponding doctor-contract review.
No push, PR, merge, tag, publication, credential-file modification, repair,
research capability or Notion-status update was performed.
