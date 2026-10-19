# Strategy Backtest Agent

Turn a trading-rule idea into a reproducible historical research result, using Python
or a terminal. Describe supported rules in plain English with optional OpenAI parsing,
or supply an explicit configuration with no AI. Python calculates indicators, trades,
fees, benchmarks and metrics; optional AI explains validated evidence.

This is for researchers and developers asking questions such as “How did these fixed
rules behave?”, “What changed on held-out data?” and “How much did modeled costs
matter?” It is a single-symbol, long-only historical research tool. It does not place
orders, recommend investments or predict future returns.

## Install

In a Python virtual environment:

```bash
python -m pip install strategy-backtest-agent
# Later, upgrade the installed package:
python -m pip install --upgrade strategy-backtest-agent
```

Requires Python `>=3.12,<4.0`. Python 3.12 is the CI and clean-install baseline on
Ubuntu/macOS. Safe configuration/report file creation requires POSIX filesystem
operations; Windows file output is unsupported. See the
[step-by-step installation guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md).

The distribution is `strategy-backtest-agent`, the Python import is
`strategy_backtest_agent`, and the terminal executable is `strategy-backtest`.
The published v1.2.0 package includes both the Python client and CLI.

## Your first strategy with AI

Prerequisites: install the package, obtain your own
[OpenAI API key](https://platform.openai.com/api-keys), and run in a new working
directory. Replace the placeholder locally; never commit a real key.

```python
from strategy_backtest_agent import AIStrategyConfig, BacktestClient

client = BacktestClient(api_key="YOUR_OPENAI_API_KEY", model="gpt-4.1-mini")
config = client.parse(
    "Backtest BTCUSDT on 1h candles for 30 days with initial balance 10000, "
    "fee 0.001 per side, full spread 10 bps and slippage 5 bps per side. "
    "Buy when RSI(14) < 30 and sell when RSI(14) > 70."
)  # Paid OpenAI request; no market-data request yet.
assert isinstance(config, AIStrategyConfig)
print(config.model_dump_json(indent=2))

# Inspect the symbol, period, entry/exit rules and costs above before executing.
result = client.run(config=config, demo=True)  # Synthetic data, no Binance request.
print(result.summary())
print(f"Return: {result.total_return_percent:.2f}%; trades: {result.total_trades}")
result.save_report("my-strategy.md")
result.save_report("my-strategy-report.json", format="json")
```

The output shows the validated configuration followed by historical synthetic metrics.
The two new reports appear in the directory where you run Python. Use a new directory
or new filenames when repeating: report writers refuse overwrites. Configuring a key
alone makes no request. `parse()` uses paid OpenAI; `demo=True` makes only the subsequent
execution offline. Omit `demo=True` to fetch Binance history instead. Direct natural-language convenience calls also use paid AI. The current single-run
DSL convenience path has a [known validation issue](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/AI.md#direct-natural-language-execution);
use the explicit parse-then-config path above for reliable DSL execution.

For environment variables, `.env`, inspection, and terminal AI workflows, see the
[AI guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/AI.md).

## Your first strategy without AI

This complete, editable example needs no key or network. Run it in its own new directory:

```python
from strategy_backtest_agent import BacktestClient, BacktestConfig, ExecutionConfig

client = BacktestClient()
config = BacktestConfig(
    symbol="BTCUSDT", timeframe="1h", initial_balance=10000.0,
    trading_fee=0.001, rsi_period=14, entry_rsi=30.0, exit_rsi=70.0,
    execution=ExecutionConfig(fee_rate=0.001, spread_bps=10.0, slippage_bps=5.0),
)
result = client.run(config=config, days=30, demo=True)
print(result.summary())
print(f"Net Buy & Hold: {result.buy_and_hold_return_percent:.2f}%")
result.save_report("offline-report.md")
result.save_report("offline-report.json", format="json")
```

Edit the RSI thresholds, balance and costs to declare your own experiment. The synthetic
series ends at 2024-07-01 UTC and demonstrates the workflow, not profitability.
For example, use `entry_rsi=25.0` to test a stricter entry threshold. DSL strategies
support more indicators through `AIStrategyConfig` and the multi-strategy configs.
`client.template("backtest")` is an optional convenience returning a validated RSI(14)
30/70 config with 10000 initial cash, fee 0.001, full spread 10 bps and slippage 5 bps;
it does not choose a strategy for you.

## Terminal quick start

After installation, use a fresh directory:

```bash
mkdir research-run && cd research-run
strategy-backtest doctor
strategy-backtest init --type backtest --output config.json
set -C  # Protect raw-result redirection from overwrite.
strategy-backtest --config config.json --days 30 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

This is offline and credential-free. `config.json` is the research input, `result.json`
is raw research output, `report.json` is normalized evidence and provenance, and
`report.md` is a readable report. Doctor checks local conditions, not whether an API
key works. Start again in a new directory for safe reruns. See
[Quick Start](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md)
and [CLI reference](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/CLI.md).

## Research capabilities

| Mode | Question | Python method |
| --- | --- | --- |
| Backtest | How did one fixed strategy behave? | `run` |
| Comparison | How did 2–5 strategies behave on the same data and costs? | `compare` |
| Validation | How did predeclared strategies behave on chronological Train and Test? | `validate` |
| Sensitivity | How did a declared parameter grid change Train-only results? | `sensitivity` |
| Cost scenarios | How did alternative execution assumptions change Train results? | `costs` |
| Walk-Forward | How did fixed strategies behave across independent Test folds? | `walk_forward` |

All modes have typed results, summaries, strict JSON and direct deterministic
Markdown/JSON reports. Reports never rerun research. AI interpretation is optional
and explicitly requested. Async methods, custom candle providers, templates and offline
diagnostics are available. Sensitivity and costs CLI commands fetch Binance and have
no `--demo`; their Python equivalents support synthetic demo data. Costs is config-only.

## Rules, execution and limitations

Supported operands: RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed-candle close and
numeric constants. Rules use `<`, `<=`, `>`, `>=` and nested AND/OR. State comparisons
such as MACD line above signal are not crossover events. Arbitrary Python strategies,
short selling, leverage, stop-loss/take-profit orders and multi-symbol portfolios are
unsupported.

Signals execute at the next candle open. Fees are fractions per executed side
(`0.001` = 0.1%); spread is the full bid/ask spread in bps, half applied each side;
slippage is adverse bps per side. Buy & Hold uses the same costs. Portfolios start
independently and close positions within their segment. Costs, full fills and unlimited
liquidity are modeled assumptions. Finite indicator seeds, limited trades, inspected
Test periods and repeated tuning limit conclusions. Historical returns do not establish
future profitability or robustness. There is no automatic optimization or selection.

## Guides and examples

- [Quick Start](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md): install, create a script, run Python/CLI, edit inputs, save and read results.
- [Python API](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md): complete signatures, all modes, metrics, async and providers.
- [CLI reference](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/CLI.md): every command, option, default and exit behavior.
- [AI guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/AI.md): your key, model, dotenv, paid operations and fallback.
- [Research guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/RESEARCH_GUIDE.md): complete configs, field ranges, rules and methodology.
- [Troubleshooting](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/TROUBLESHOOTING.md): observed errors and practical fixes.
- [Examples](https://github.com/changelia/strategy-backtest-agent/tree/main/examples): runnable scripts and validated JSON, downloaded separately from the package.

For maintainers: [Contributing](https://github.com/changelia/strategy-backtest-agent/blob/main/CONTRIBUTING.md),
[Architecture](https://github.com/changelia/strategy-backtest-agent/blob/main/ARCHITECTURE.md),
[Release procedure](https://github.com/changelia/strategy-backtest-agent/blob/main/RELEASE.md),
and [MIT license](https://github.com/changelia/strategy-backtest-agent/blob/main/LICENSE).
GitHub README edits do not update descriptions embedded in distributions already uploaded to PyPI.
