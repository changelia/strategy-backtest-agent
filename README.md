# Strategy Backtest Agent

Strategy Backtest Agent is a historical research tool for testing fixed, single-symbol,
long-only trading rules on synthetic or Binance OHLCV candles. Python performs indicator
calculations, portfolio accounting, execution-cost modeling, benchmarks, and metrics.
Optional OpenAI features turn natural-language requests into validated rules or interpret
existing research evidence. The software does not place trades or predict future returns.

## Contents

- [Install](#install)
- [Python quick start](#python-quick-start)
- [Terminal quick start](#terminal-quick-start)
- [Research workflows](#research-workflows)
- [Strategies and execution](#strategies-and-execution)
- [Optional AI](#optional-ai)
- [Guides and examples](#guides-and-examples)

## Install

Install the published distribution in Python 3.12 or newer:

```bash
python -m pip install strategy-backtest-agent==1.2.0
```

The distribution is named `strategy-backtest-agent`, its import package is
`strategy_backtest_agent`, and its terminal command is `strategy-backtest`. The package
requires Python `>=3.12,<4.0`; CI and the clean-install customer checks use Python 3.12.
Customer file-writing workflows are tested on POSIX systems. Windows file output is not
supported because safe no-overwrite creation uses POSIX filesystem operations.

## Python quick start

This complete example uses fixed synthetic candles and needs no credentials or network:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("backtest")
result = client.run(config=config, days=3, demo=True)

print(result.summary())
print(f"Trades: {result.total_trades}")
markdown = client.report(result, format="markdown")
report_json = client.report(result, format="json")
```

The public client returns typed results and reports directly from those results without
rerunning research. See the [Python API guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md)
for all six modes, custom providers, async calls, and complete signatures.

## Terminal quick start

Run in a new directory. This uses the published CLI, validated config template, and
synthetic offline candles:

```bash
mkdir research-run && cd research-run
strategy-backtest doctor
strategy-backtest init --type backtest --output config.json
set -C
strategy-backtest --config config.json --days 3 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
```

`config.json` is input, `result.json` is raw backtest output, and `report.md` is a
readable evidence-grounded report. `set -C` prevents shell redirection from replacing
an existing result; config and report writers also refuse overwrites. For a repeat,
use a new directory and filenames. The [CLI guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/CLI.md)
lists every command and option.

## Research workflows

Six workflows reuse the same deterministic backtester:

| Workflow | Use |
| --- | --- |
| Backtest | Describe one fixed strategy over a historical window. |
| Comparison | Compare 2–5 fixed strategies with shared data and independent portfolios. |
| Validation | Evaluate predeclared strategies on chronological Train and held-out Test segments. |
| Sensitivity | Inspect a bounded parameter grid on Train only; no variant is selected. |
| Cost scenarios | Compare declared execution-cost assumptions for one fixed strategy on Train. |
| Walk-Forward | Evaluate fixed strategies over complete, chronological Train/Test folds. |

Config-driven CLI research does not require OpenAI credentials. `--demo` selects
synthetic data for backtest, comparison, validation, and Walk-Forward. Sensitivity and
cost-scenario CLI commands fetch Binance data and do not offer `--demo`; the Python
client can run those modes on demo candles. More details and complete config examples
are in the [research guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/RESEARCH_GUIDE.md).

## Strategies and execution

Rules support RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed-candle price,
numeric values, `<`, `<=`, `>`, `>=`, and nested AND/OR groups. A state comparison such
as `MACD line > signal` is not a crossover event. Crossover operators are unsupported.

Signals use a completed candle and execute at the next candle's open. Fees are a
fraction charged per side (for example, `0.001` means 0.1%). Spread is the full
bid/ask spread in basis points, half applied on each side; slippage is adverse basis
points per side. Buy & Hold uses the same costs. Segment portfolios start independently
and liquidate at their own final close. These are modeled assumptions, not measured
fills. Historical results do not establish future profitability or robustness.

## Optional AI

`OPENAI_API_KEY` and `OPENAI_MODEL` configure natural-language parsing and optional
report interpretation. The default model is `gpt-4.1-mini`. These OpenAI requests may
incur charges; AI extracts or explains validated information but does not calculate
trades or financial metrics. CLI dotenv loading and Python opt-in dotenv behavior are
covered in the [AI guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/AI.md).

## Guides and examples

- [Quick Start](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md): install, run offline, save and understand reports, then use Binance.
- [Python API](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md): methods, models, results, async, credentials, providers.
- [CLI reference](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/CLI.md): commands, flags, defaults, and errors.
- [AI configuration](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/AI.md): credentials, precedence, costs, and failure behavior.
- [Research guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/RESEARCH_GUIDE.md): modes, strategies, metrics, and methodology.
- [Troubleshooting](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/TROUBLESHOOTING.md): common errors and concrete resolutions.
- [Runnable examples](https://github.com/changelia/strategy-backtest-agent/tree/main/examples).

Maintainer setup is in [CONTRIBUTING.md](https://github.com/changelia/strategy-backtest-agent/blob/main/CONTRIBUTING.md); implementation details are in [ARCHITECTURE.md](https://github.com/changelia/strategy-backtest-agent/blob/main/ARCHITECTURE.md).
