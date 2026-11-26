# Task #18 — CLI init and configuration templates

**STATUS: READY** — local source and installed-package verification passed.

## Baseline and scope

Started from verified `main`, local `origin/main` and public HTTPS remote main all
at `b6e8f42322aaca0fd51dcae27bd50855fbbda3e6`; created `feat/cli-init` without
resetting or cleaning. The configured SSH remote could not authenticate, so the
read-only remote check used:

```bash
git ls-remote https://github.com/changelia/strategy-backtest-agent.git refs/heads/main
```

No applicable `AGENTS.md` exists in this checkout or its ancestors. Read the Notion
task without changing its status. Existing research files, dotenv files and other
worktrees are preserved. Package version remains **1.0.0**; this is unreleased
v1.1 work. No dependency policy, financial calculations or engines changed.

## Interface, schemas and consumer gaps

```text
strategy-backtest init --type {backtest,compare,validate,walk-forward} --output PATH
```

Both arguments are required. There are no prompts, stdin reads, credentials,
interactive wizard, overwrite flag or reliance on checkout examples.

Inspection identified two consumer gaps before implementation:

- Standard backtests only accepted CLI flags, with no configuration-file reader.
  Added a narrow top-level `--config FILE` consumer for existing `BacktestConfig`.
  Duration remains the existing `--days` option (default 180), not an invented JSON
  field. Strategy/account flags cannot accompany `--config`; this includes argparse
  abbreviations. Existing spread/slippage override flags remain available and retain
  the declared fee, including configs using only the legacy `trading_fee` alias.
- Compare, validate and walk-forward accepted config files but their CLIs always
  fetched Binance data. Added `--demo` routing to existing `run_comparison`,
  `run_validation` and `run_walk_forward`, using the existing synthetic candle
  generator. No new schema, provider, parser architecture or research engine.
  `--demo` requires `--config`, preventing accidental AI requests.

| Template type | Validated model | Config consumer | Historical duration |
| --- | --- | --- | --- |
| `backtest` | `BacktestConfig` | Top-level `--config` | CLI `--days`, default 180 |
| `compare` | `ComparisonConfig` | `compare --config` | JSON `period_days: 30` |
| `validate` | `ValidationConfig` | `validate --config` | JSON 30 days; Train ratio 0.7 |
| `walk-forward` | `WalkForwardConfig` | `walk-forward --config` | JSON 60 days; rolling Train 30/Test 10/step 10; 3 folds |

Files are complete inputs for their documented consumer, not bare strategy DSL.
All templates explicitly serialize validated defaults, balance 10000, fee 0.001,
full spread 10 bps and slippage 5 bps per side. Fixed RSI(14) 30/70 is used; comparison
also declares RSI(14) 25/70. Walk-forward stitches independent contiguous OOS fold
returns using the existing methodology, without position carry or optimization.

Research demos end at **2024-07-01T00:00:00Z** and supply exactly the required
prior indicator warm-up plus the evaluation candles. Other configured evaluation
ends are rejected in demo mode; null is allowed. Synthetic OHLCV uses the original
bounded generator; the existing 300,000-candle limit applies. Legacy standard demo
semantics and financial baseline remain unchanged. Synthetic examples do not
establish profitability, predictive value or live execution behavior.

## Exact offline commands

From an installed package (prefix with `poetry run` in a development checkout):

```bash
strategy-backtest init --type backtest --output backtest-config.json
strategy-backtest --config backtest-config.json --days 180 --demo --json
strategy-backtest init --type compare --output comparison-config.json
strategy-backtest compare --config comparison-config.json --demo --json
strategy-backtest init --type validate --output validation-config.json
strategy-backtest validate --config validation-config.json --demo --json
strategy-backtest init --type walk-forward --output walk-forward-config.json
strategy-backtest walk-forward --config walk-forward-config.json --demo --json
```

All execute without OpenAI or network. Omitting `--demo` uses the existing Binance
history path and requires network. Edit the fixed historical end deliberately when
conducting real-data research. Help: `strategy-backtest init --help`.

## Implementation and file safety

- `src/strategy_backtest_agent/init_cli.py`: deterministic model-validated templates
  and init argument handling; no resource files or new archive inclusion rules.
- `cli.py`: init dispatch and the existing-model backtest config consumer.
- `demo.py`: exact warm-up/evaluation history preparation for research demo routes.
- `comparison/cli.py`, `validation/cli.py`, `walk_forward/cli.py`: offline routing
  using existing engines; original network/config/AI paths preserved.
- `execution_cli.py`: fee-alias fallback also recognizes `BacktestConfig.trading_fee`
  when explicit spread/slippage overrides are applied without an execution object.
- `README.md`: concise syntax, offline commands, assumptions and limitations.
- `tests/test_init_cli.py`: 34 offline cases using actual CLI-generated files and
  consumers, independent model validation, determinism, report evidence, argument
  errors, conflicting/symlink destinations, parent traversal, racing creators,
  injected write failures, malformed configs and conflicting evaluation ends.
- `tests/installed_smoke.py`: installed init for all four types, repeated-init refusal
  and actual offline execution, with stdin closed; existing report checks preserved.
- `tests/packaging_ci.py` and `tests/test_packaging_ci.py`: compare generated config
  and execution hashes across wheel/sdist, including a mismatch regression.
- This delivery report.

The existing `reports.cli.write_new` provides atomic no-overwrite publication.
Configurations validate before publication. Directory traversal uses directory file
handles and `O_NOFOLLOW`, rejecting symlink components and `..`. Missing real parent
directories are created with private permissions. Content is written to an exclusive
private temporary file, flushed/fsynced, then linked to the target only if absent.
Existing files, directories, live/dangling symlinks and concurrent creators cannot
be overwritten. Failed writes/publication remove the task's temporary file, not
pre-existing content. Errors exit 2 with a clear message; no destructive options.
As with report output, this requires POSIX directory operations. Use physical paths
rather than symlink aliases (for example `/private/tmp` on macOS).

## Quality checks

| Exact command | Result |
| --- | --- |
| `poetry run pytest -q` | **1338 passed in 8.06s** |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 114 files |
| `poetry run mypy` | Passed; 113 source files |
| `poetry check --lock` | Passed; `All set!` |
| `poetry run strategy-backtest init --help` | Passed |

The original 1303 cases remain passing, including legacy RSI Markdown, all six
report types, AI mocks, JSON/evidence baselines and existing CLI commands. Ordinary
pytest remains offline; it does not install dependencies or build distributions.

## Fresh artifacts and installed checks

Exact final orchestration command:

```bash
/private/tmp/sba-task15-2bjaudwn/tools/bin/python tests/packaging_ci.py \
  --checkout /Users/levanchangelia/projects/strategy-backtest-agent \
  --work /private/tmp/sba-task18-a_drfakc/final
```

The helper builds current sources with isolated PEP 517 tooling, runs strict Twine
metadata and existing archive checks, installs wheel and sdist in distinct clean
venvs outside the checkout, and executes explicit installed CLI paths from fresh
external work directories. Sdist pip uses `--no-cache-dir --use-pep517`; the logs
record its isolated backend and fresh project wheel build. Dependencies can download
from PyPI; application environments omit inherited credentials/Python overrides,
disable dotenv, and load the existing temporary socket-denying guard.

Tools: CPython 3.12.3, pip 24.0, build 1.6.1, Twine 7.0.0, packaging 26.3;
backend poetry-core 2.5.0. Generated configs, reports, logs, venvs and distributions
are external and untracked. Original Task #15/16 artifacts are preserved. An initial
sandboxed attempt failed backend DNS; an authorized retry allowed dependency access.
An earlier candidate run preceded the final abbreviated-flag regression; only the
`final` workspace is the verification evidence for the committed source.

## Final installed results and artifacts

The final orchestration exits **0** with both receipts **READY** and no report
failures. Both installed distributions are `strategy-backtest-agent 1.0.0`;
`pip check` reports `No broken requirements found.` Actual import paths:

```text
/private/tmp/sba-task18-a_drfakc/final/wheel-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
/private/tmp/sba-task18-a_drfakc/final/sdist-env/lib/python3.12/site-packages/strategy_backtest_agent/__init__.py
```

The installed CLI paths are each environment's `bin/strategy-backtest` with the
same venv's Python in the shebang. Working directories are respectively
`/private/tmp/sba-task18-a_drfakc/final/wheel-work` and `sdist-work`.
All four `init --type TYPE --output FILE` calls succeed with stdin closed; each
config executes through its documented `--config FILE --demo --json` consumer.
Every repeated init exits **2**, preserving the initial file bytes. Config and
execution-result hashes agree across wheel/sdist for all four types.

Existing installed help/demo/report-help, untouched demo-to-report JSON/Markdown,
repeatability and malformed-input checks all pass. JSON-only stdout is valid;
both report formats repeat byte-for-byte and match across installations. The
original zero-spread demo baseline remains 10000 initial, 123.09493440255116 final,
-98.76905065597448%, 45 trades and zero winners. Normalized evidence SHA256 remains
`bbfe64bc4e91ebb17942501c4b11ca13bdc5f02ea6c9ad150cbcf0925cc47c48`.
Both application socket logs record **zero network attempts**.

Fresh archives are external under `/private/tmp/sba-task18-a_drfakc/final/artifacts`.
Strict Twine validation and archive inspection pass on both. Each contains 63 files,
including all 58 runtime files with exact current-checkout contents. Required
license/README metadata, runtime dependencies and CLI entry point are correct;
actual dotenv/credentials, research outputs, caches and unrelated files are absent.
No archive inclusion rules changed; the single new runtime Python module is
included through existing discovery. Original Task #15/16 files retain their hashes.

| Artifact | SHA256 |
| --- | --- |
| strategy_backtest_agent-1.0.0-py3-none-any.whl | `c1f4ac84bc4e46b1875b8ce677c28149b48b022286ef397f7afabd122c6b17b6` |
| strategy_backtest_agent-1.0.0.tar.gz | `f030ebec92b4a07687f878fbc6fdc8028413e61c30e614c1e3bd147a3ec4f4dc` |

The 17 original research files retain their original hashes, and the real `.env`
retains its inode, size and modification time. No generated files are staged.

## Remaining limitations

No doctor, full tutorial, wizard, publication or release automation was added.
No real OpenAI or Binance request was used to verify application behavior. Local
installed verification is on macOS/Python 3.12; a future authorized GitHub run remains
necessary to verify this new functionality on Ubuntu. The existing CI packaging job
will invoke the extended smoke checks. No push, PR, merge, tag, publication,
credential change or Notion status update was performed.
