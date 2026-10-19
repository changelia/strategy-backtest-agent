# Quick Start and Research Tutorial

This tutorial uses the installed CLI, the validated configuration templates, and
fixed synthetic candles. It makes no OpenAI or market-data requests. It is a
reproducibility walkthrough, not a profitability example. This document lives in the
source repository and is not an installed package resource.

## Install from a source checkout

Use Python 3.12 or newer and pip in a POSIX shell. The project declares
`>=3.12,<4.0`; source installation and file-output commands were checked on macOS
with Python 3.12, and the repository CI baseline is Ubuntu with Python 3.12. Secure
file creation for configs and reports uses POSIX directory operations, so Windows
file-output support is unavailable.

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent

# Keep generated files and the environment outside the checkout.
REPO="$(pwd -P)"
TMP_ROOT="$(python3.12 -c 'from pathlib import Path; import tempfile; print(Path(tempfile.gettempdir()).resolve())')"
WORKDIR="$(mktemp -d "$TMP_ROOT/strategy-backtest.XXXXXX")"
python3.12 -m venv "$WORKDIR/venv"
"$WORKDIR/venv/bin/python" -m pip install "$REPO"
cd "$WORKDIR"
CLI="$WORKDIR/venv/bin/strategy-backtest"
```

`pip install "$REPO"` installs the checked-out source as a normal distribution;
the resulting CLI runs from the virtual environment's `bin` directory. For project
development, use `poetry install` in the checkout and prefix commands with
`poetry run`. The v1.1.0 CLI release is available on PyPI. Version 1.2.0 adds the
public Python API while preserving the CLI; its PyPI publication is pending
verification. After publication, install it with
`python -m pip install strategy-backtest-agent==1.2.0`.

## First offline backtest and report

The commands below create a new configuration, raw result JSON, report JSON and
Markdown report. `set -C` makes shell redirections fail if a result filename already
exists. The CLI also refuses to overwrite config and report destinations. Start
again in a new `WORKDIR` for a clean rerun; do not remove files as part of a rerun.

```bash
export PYTHON_DOTENV_DISABLED=1  # Keep this tutorial run independent of local .env files.
set -C
env -u OPENAI_API_KEY -u OPENAI_MODEL PYTHON_DOTENV_DISABLED=1 "$CLI" doctor
"$CLI" init --type backtest --output backtest-config.json
"$CLI" --config backtest-config.json --days 180 --demo --json > backtest-result.json
"$CLI" report --input backtest-result.json --format json --output research-report.json
"$CLI" report --input backtest-result.json --format markdown --output research-report.md
```

These outputs are distinct artifacts:

| File | Meaning |
| --- | --- |
| `backtest-config.json` | Validated inputs for a historical research run |
| `backtest-result.json` | Raw result emitted by the backtest CLI, including source metrics |
| `research-report.json` | Normalized evidence, observations, provenance and report status |
| `research-report.md` | Human-readable rendering of that report |

The template uses RSI(14), entry below 30 and exit above 70, with an initial
balance of 10,000, a 0.001 fee per side, 10 bps full spread and 5 bps adverse
slippage per side. `--demo` uses deterministic synthetic candles ending at the
fixed UTC boundary 2024-07-01. The standard RSI backtest retains its existing
in-range RSI initialization. The comparison, validation and walk-forward engines
include their required causal prior candles outside the evaluation window.

For byte-for-byte report verification, write the same format to another new name
and compare it:

```bash
"$CLI" report --input backtest-result.json --format json --output research-report-repeat.json
cmp research-report.json research-report-repeat.json
```

The JSON report includes evidence identifiers and hashes; the Markdown report is
intended for reading. Report generation validates the saved result and does not
fetch candles or run the backtest again. Determinism assumes identical input bytes
and the same report generator version.

## Compare, validate and walk forward

Each `init` type produces a complete configuration for its matching CLI consumer.
The following commands execute all three research modes against the same fixed
synthetic demo boundary:

```bash
"$CLI" init --type compare --output comparison-config.json
"$CLI" compare --config comparison-config.json --demo --json > comparison-result.json

"$CLI" init --type validate --output validation-config.json
"$CLI" validate --config validation-config.json --demo --json > validation-result.json

"$CLI" init --type walk-forward --output walk-forward-config.json
"$CLI" walk-forward --config walk-forward-config.json --demo --json > walk-forward-result.json
"$CLI" report --input walk-forward-result.json --format json --output walk-forward-report.json
"$CLI" report --input walk-forward-result.json --format markdown --output walk-forward-report.md
```

The templates use fixed RSI strategies. Comparison runs each strategy with its own
portfolio on shared candles and assumptions. Chronological validation places the
Train segment before the held-out Test segment; each starts with independent cash
and no carried position. Select and freeze rules before inspecting Test. Repeatedly
tuning against a Test period contaminates that holdout and weakens its value as
unseen evidence.

Walk-forward uses multiple chronological Train/Test folds with the same declared
strategies and fresh portfolios for every segment. Train results are diagnostic;
the tool does not optimize parameters or select a winner. Aggregate results use
Test folds only. The template's optional stitched OOS index compounds normalized
returns from independent, contiguous Test folds. It is a fold-endpoint research
index, not an account carrying positions across folds; it has no continuous
portfolio drawdown interpretation.

The configured fee is charged on each side. Spread is the full bid/ask spread in
basis points, applied as half the spread on each side; slippage is adverse basis
points per side. Strategy execution and the net Buy & Hold benchmark use the same
declared costs. In comparisons and validation, portfolios are independent; no
capital or open positions move from one strategy or segment to another.

## Read results carefully

The `--demo` source is synthetic and reproducible. It is useful for checking
configuration, output shape and command behavior; it is not historical Binance
data and says nothing about likely real-market performance. The fixed demo end and
warm-up rules make examples comparable. Warm-up candles initialize indicators
causally but are excluded from the research evaluation in the comparison,
validation and walk-forward engines.

To evaluate historical Binance candles instead, review the configuration first,
choose an intentional UTC `evaluation_end`, and omit `--demo`. For example:

```bash
"$CLI" compare --config comparison-config.json --json > binance-comparison-result.json
```

That command requires network access to Binance. Do not compare results from
different data windows or cost assumptions as if only the strategy had changed.
Repeated experiments on inspected history can overfit even when each calculation
is deterministic. Historical returns and positive Test folds do not establish
predictive value or future profitability.

Markdown reports summarize the validated source evidence. Check the configuration,
data range, costs, benchmark policy, warnings and negative folds before interpreting
any aggregate. A report is not an independent verification that the source market
data or backtest was truthful.

## Optional AI configuration

Deterministic config-driven backtests, the offline demo, doctor and report generation
do not need an OpenAI key. AI strategy parsing and optional report interpretation
use `OPENAI_API_KEY`; both default to `gpt-4.1-mini`, configurable with
`OPENAI_MODEL`. The selected model must support the project's Responses API and
structured outputs.

The CLI loads `.env` from the current directory or nearest parent at startup using
`override=False`, so shell variables take precedence. Example local `.env` entries
(use placeholders only):

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Keep real credentials in your local environment or ignored `.env`; never commit
them or place them in strategy prompts. `strategy-backtest doctor` checks only
whether a key is present and which model setting is configured. It does not validate
the key or contact the provider. Live AI requests require network access and can
incur API charges. Historical Binance requests also need network access.

## Further reference

- [README research sections](../README.md) cover supported research commands and
  output schemas.
- [Architecture](../ARCHITECTURE.md) documents execution accounting, indicators,
  initialization, and Train/Test boundaries.
- [Synthetic example report](../examples/research-report.md) shows the report
  presentation format.
- [Changelog](../CHANGELOG.md) records version history and known scope.
