# Quick Start

[Home](../README.md) · [Python API](PYTHON_API.md) · [CLI](CLI.md) · [AI](AI.md) · [Research](RESEARCH_GUIDE.md)

Follow this guide to install the package, define an experiment, run it without network
access, and save readable reports. After the offline path works, you can deliberately
switch to Binance history or optional paid AI.

## 1. Install into a virtual environment

Use Python `>=3.12,<4.0`. Python 3.12 is the tested baseline on macOS and Ubuntu;
later allowed versions are not a separate compatibility guarantee. Configuration and
report file creation uses POSIX operations; Windows file output is unsupported.
On Windows, use a Linux environment such as WSL for the documented file workflows.

In a POSIX terminal, from a directory you own:

```bash
mkdir first-research && cd first-research
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install strategy-backtest-agent
python -m pip show strategy-backtest-agent
python -c 'from importlib.metadata import version; print(version("strategy-backtest-agent"))'
strategy-backtest --help
strategy-backtest doctor
```

Expected: an installed version, CLI help, and offline diagnostics. Missing optional
OpenAI credentials do not fail doctor. The distribution name is
`strategy-backtest-agent`, the import is `strategy_backtest_agent`, and the terminal
command is `strategy-backtest`. The published v1.2.0 includes the public client.
You do not need Git, Poetry or a clone. Contributor instructions are in
[CONTRIBUTING.md](../CONTRIBUTING.md).

To upgrade later, reactivate this environment and run:

```bash
python -m pip install --upgrade strategy-backtest-agent
```

## 2. Create and run your first Python script

Create a file named `my_research.py` in this new directory and copy the following
complete script. This is **offline synthetic research**: no key or application network
access is needed. The local `.env` is not loaded by Python automatically.

```python
from pathlib import Path

from strategy_backtest_agent import BacktestClient, BacktestConfig, ExecutionConfig

client = BacktestClient()
config = BacktestConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    initial_balance=10000.0,
    trading_fee=0.001,
    rsi_period=14,
    entry_rsi=30.0,
    exit_rsi=70.0,
    execution=ExecutionConfig(fee_rate=0.001, spread_bps=10.0, slippage_bps=5.0),
)
result = client.run(config=config, days=30, demo=True)
print(result.summary())
print(f"Net Buy & Hold: {result.buy_and_hold_return_percent:.2f}%")
with Path("backtest-result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("backtest-report.md")
result.save_report("backtest-report.json", format="json")
print("Saved backtest-result.json, backtest-report.md and backtest-report.json")
```

Run it with the environment's Python:

```bash
python my_research.py
```

Expected: a one-line backtest summary, net Buy & Hold percentage, and a list of the
three saved files. Negative results are valid; these artificial candles are a workflow
demonstration, not a profitable strategy example. The files appear in your terminal's
current working directory, not necessarily beside the script.

| File | What it contains | What to do next |
| --- | --- | --- |
| `backtest-result.json` | Complete raw research input/results | Retain for audit or report regeneration. |
| `backtest-report.json` | Normalized evidence, observations, provenance and status | Inspect units, evidence paths, hashes and warnings. |
| `backtest-report.md` | Human-readable Markdown report | Read configuration, results, benchmark and limitations together. |

`ClientResult.summary()` is a compact view. Full trades and costs remain in
`result.data`; convenient fields such as `result.total_trades` proxy that typed model.
`to_json()` preserves the raw report-compatible source. There is no `save_result()` or
typed result loader. Exclusive file mode `"x"` and report writers refuse overwrite.
For reruns, use a fresh directory or change **all** output names; a failure at a later
file does not remove an earlier file already saved.

## 3. Edit your declared inputs

In `my_research.py`, try `entry_rsi=25.0` instead of `30.0`, or change
`initial_balance=5000.0` and `days=60`. Change output filenames before running again.
These change your experiment; they are not automatically selected improvements.

- `BacktestConfig` is the legacy RSI input. It uses `trading_fee`; `days` is passed
  separately to `run()`. Keep `entry_rsi < exit_rsi`.
- A fee is a fraction per side: `0.001` = 0.1%, not 0.001%.
- Spread is the **full** spread in basis points (1 bp = 0.01%); half is modeled on
  each side. Slippage is adverse bps per side. If both `trading_fee` and
  `execution.fee_rate` are explicit, they must agree.
- For nested rules or advanced indicators, use `AIStrategyConfig` (it can be built
  manually, without AI), or a mode-specific research configuration. See the
  [complete schema and strategy guide](RESEARCH_GUIDE.md#configuration-contracts).

Do not repeatedly alter rules based on inspected Test outcomes and call the same
period an independent holdout.

## 4. Run the equivalent terminal workflow

Use another new directory, with the installed virtual environment still activated:

```bash
mkdir cli-research && cd cli-research
strategy-backtest init --type backtest --output config.json
strategy-backtest doctor --type backtest --config config.json
set -C
strategy-backtest --config config.json --days 30 --demo --json > result.json
strategy-backtest report --input result.json --format json --output report.json
strategy-backtest report --input result.json --format markdown --output report.md
```

Expected: init confirms the file it created, doctor validates it, and research/report
commands save valid JSON and nonempty Markdown. Open `config.json` in a text editor
before executing to review or edit its RSI fields, cash and execution costs. `init`
uses RSI(14) 30/70, cash 10000, fee 0.001, spread 10 bps and slippage 5 bps.
Root `--config` accepts `BacktestConfig`, not arbitrary DSL JSON.

`set -C` protects shell `>` redirection. Report and init writers also reject directories,
symlinks and parent traversal in output paths. On macOS, use a physical working path
(`pwd -P`); avoid spelling a report destination through `/tmp` or `/var` symlinks.
For temporary work, resolve the parent path first with Python's `Path.resolve()`.
Do not delete old research merely to rerun an example.

Omit `--json` and redirection for a terminal summary. With `--json`, stdout is exactly
one raw result object; errors go to stderr and normally exit 2. Reports have their own
`--output` option. A config is not a valid report input: report reads a **raw result**.

## 5. Read and reproduce your report

Read the strategy and execution assumptions before performance. Returns and drawdowns
are percentages, excess return is percentage points, and fees/cost totals are quote
currency. No completed trades can make win rate undefined; null is not zero. Profit
factor is also null when undefined, including when there are no losing trades.

Reports validate source structure and relationships. Source hashes and candle digests
record provenance; they cannot prove the supplied results or prices are authentic.
To regenerate without executing research:

```bash
strategy-backtest report --input result.json --format json --output report-repeat.json
cmp report.json report-repeat.json
```

Expected: `cmp` prints nothing and returns 0 for identical input and report generator
version. AI interpretation is not byte-for-byte reproducible. See
[results and reports](PYTHON_API.md#results-serialization-and-reports).

## 6. Try other research questions

The [Research Guide](RESEARCH_GUIDE.md#six-complete-research-workflows) provides complete
Python, CLI and JSON inputs for comparison, Train/Test validation, sensitivity, costs
and Walk-Forward. `init` supports only `backtest`, `compare`, `validate`, `walk-forward`.
Python demo execution supports all six modes. CLI sensitivity/costs have no `--demo`.

## 7. Use your own natural-language strategy

The [AI Guide](AI.md#parse-inspect-and-execute-in-python) shows how to supply your own
OpenAI key, parse supported rules, inspect configuration, and execute exactly that
configuration. Parsing and optional report interpretation are paid OpenAI operations;
configuring a key alone is not. `demo=True` does not make the preceding parse offline.
The [README](../README.md#your-first-strategy-with-ai) has a complete first example.

## 8. Switch deliberately to historical Binance data

Python: remove `demo=True` from the script's `client.run(...)`. That run fetches
Binance candles. You can pin `evaluation_end` in Python, for example
`datetime(2024, 7, 1, tzinfo=UTC)` after importing `UTC, datetime` from `datetime`.

CLI: use a new filename and omit `--demo`:

```bash
strategy-backtest --config config.json --days 30 --json > binance-result.json
strategy-backtest report --input binance-result.json --format markdown --output binance-report.md
```

These commands require Binance network access but no OpenAI key. Root CLI uses the
current requested end; multi-strategy configs can declare `evaluation_end`. Binance
availability depends on network, region, rate limits and available history. A fixed end
is not a frozen data snapshot. Synthetic data ends at 2024-07-01 UTC; it is unrelated
to today's Binance market. Market requests also retrieve necessary prior warm-up.

Next: [Python API](PYTHON_API.md), [CLI](CLI.md), [AI](AI.md),
[Research](RESEARCH_GUIDE.md), or [Troubleshooting](TROUBLESHOOTING.md).
