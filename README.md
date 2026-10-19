# Strategy Backtest Agent

Research fixed, single-symbol trading strategies on historical or synthetic candles.
The Python application calculates indicators, signals, trades, execution costs,
benchmarks, and metrics deterministically. Optional OpenAI features parse natural
language into validated rules or explain existing research evidence. This is a
historical research tool; it does not place orders or predict future returns.

## Table of contents

- [Installation and release status](#installation-and-release-status)
- [Python API quick start](#python-api-quick-start)
- [CLI quick start](#cli-quick-start)
- [Research workflows and configurations](#research-workflows-and-configurations)
- [Strategies and indicators](#strategies-and-indicators)
- [Execution assumptions and limitations](#execution-assumptions-and-limitations)
- [Reports](#reports)
- [AI configuration](#ai-configuration)
- [Development](#development)

## Installation and release status

The **v1.1.0** release provides the command-line interface. The v1.2.0 update adds
the public Python API while preserving the CLI. **v1.2.0 publication is pending**;
verify the PyPI upload before installing it. After publication, install the release with:

```bash
python -m pip install strategy-backtest-agent==1.2.0
```

The documented and CI-tested environment is POSIX with Python 3.12 or newer
(project requirement `>=3.12,<4.0`). Safe config and report file creation uses POSIX
filesystem operations; Windows file-output support is unavailable. For development,
clone the repository and run `poetry install`, then prefix CLI commands with
`poetry run`. A pip installation runs the installed CLI from its environment.

After the reviewed release change is merged, and until its v1.2.0 upload is verified,
the API can be run from the main source checkout with Poetry:

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
```

The [CLI Quick Start and Research Tutorial](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md)
has a complete installed-source workflow. The [Python API reference](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md)
documents every client operation and runnable example. These absolute GitHub links
also work from the PyPI project page and remain valid after the release branch is removed.

## Python API quick start

This example uses synthetic data, so the research and deterministic report
need no credentials or network access:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("backtest")
result = client.run(config=config, days=3, demo=True)

print(result.summary())
print(f"Return: {result.total_return_percent:.2f}%")
report_markdown = client.report(result, format="markdown")
report_json = client.report(result, format="json")
```

The result remains typed and exposes the source metrics; reports are generated from
the in-memory result without rerunning the backtest. See the [complete Python API
guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md)
for comparisons, validation, sensitivity, costs, Walk-Forward, parsing, async calls,
safe saving, templates, and diagnostics. The v1.2.0 pip command above becomes usable
after publication is verified.

## CLI quick start

The following commands use the released CLI, fixed synthetic candles, and no OpenAI
credentials. Start in a new directory; config and report outputs refuse to overwrite,
and `set -C` protects the shell-created raw result file:

```bash
mkdir research-run
cd research-run
strategy-backtest doctor
strategy-backtest init --type backtest --output backtest-config.json
set -C
strategy-backtest --config backtest-config.json --days 3 --demo --json > backtest-result.json
strategy-backtest report --input backtest-result.json --format json --output research-report.json
strategy-backtest report --input backtest-result.json --format markdown --output research-report.md
```

The config, raw backtest result, evidence-grounded report JSON, and readable Markdown
are separate files. To rerun, use a new directory and new output names. See the
[Quick Start and Research Tutorial](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md)
for comparison, chronological validation, and Walk-Forward commands, output
interpretation, and a complete reproducible sequence.

## Research workflows and configurations

All six workflows use validated configurations and the existing deterministic
backtester. Config-file workflows do not need an OpenAI key. Example configurations
are available in the [repository examples](https://github.com/changelia/strategy-backtest-agent/tree/main/examples).
For commands below, run from a source checkout and use `poetry run` when using its
development environment. `--demo` selects fixed synthetic candles; omit it to fetch
historical Binance candles, which requires network access.

| Workflow | What it evaluates | Key interpretation |
| --- | --- | --- |
| Backtest | One fixed strategy over one historical window | One portfolio; benchmark and costs use the declared assumptions |
| Comparison | 2–5 fixed strategies on shared candles | Each strategy has an independent portfolio; common data and settings |
| Validation | Fixed strategies on chronological Train then Test | Test is held out only if it was not used to choose or tune the rules |
| Sensitivity | A declared parameter grid on Train | Descriptive Train-only results; no automatic selection or optimization |
| Cost scenarios | One strategy under declared cost assumptions on Train | Scenario assumptions are modeled inputs, not measured execution costs |
| Walk-Forward | Fixed strategies across chronological Train/Test folds | Test folds have fresh portfolios; aggregate metrics use Test results only |

From a checkout, these are the config consumers and matching example files:

```bash
poetry run strategy-backtest compare --config examples/comparison.json --demo --json
poetry run strategy-backtest validate --config examples/validation.json --demo --json
poetry run strategy-backtest sensitivity --config examples/sensitivity.json --json
poetry run strategy-backtest costs --config examples/execution-scenarios.json --json
poetry run strategy-backtest walk-forward --config examples/walk-forward.json --demo --json
```

`strategy-backtest init --type` creates complete backtest, compare, validate, or
walk-forward configs; sensitivity and costs use their existing schemas and examples.
The [detailed CLI tutorial](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/QUICK_START.md)
explains configuration fields, fixed evaluation boundaries, offline execution, and
the distinction between raw result JSON and report JSON.

Comparison, validation, and Walk-Forward config commands above use synthetic offline
data. The current sensitivity and cost-scenario CLI commands fetch Binance candles
and require network access; they do not have a `--demo` option. Their deterministic
calculations can still be exercised offline through `BacktestClient` using
`demo=True` as shown in the [Python API guide](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md).

Comparison fetches data once and keeps each strategy's portfolio separate. Its excess
return is strategy return minus net Buy & Hold return, in percentage points. Validation
uses chronological segments, fresh initial capital, and segment-local liquidation;
Train positions and signals do not carry into Test. A Test period repeatedly inspected
to change a strategy is no longer an independent holdout.

Sensitivity evaluates only its declared Train grid. It does not rank, select, or
recommend a variant. Walk-Forward evaluates the same predeclared strategies on each
fold; Train is diagnostic and does not trigger parameter optimization. Fold Test
results are independent. An optional stitched OOS index compounds normalized returns
only for supported contiguous Test windows; it does not represent carried positions
or a continuous account drawdown. Repeatedly examining the same history can still
overfit, regardless of the number of folds.

## Strategies and indicators

The Strategy DSL supports RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed-candle
price, constants, `<`, `<=`, `>`, `>=` comparisons, and nested AND/OR rules. Indicator
components may be compared to each other. A comparison such as `MACD line > signal`
is a state condition; it does not mean that a crossover just occurred. Crossover
operators are unsupported. AI parsing validates supported rules; it does not calculate
indicators, trades, prices, or financial metrics.

| Indicator | Components and convention |
| --- | --- |
| RSI | Wilder RSI; default period 14 |
| SMA / EMA | Close-based simple and exponential moving averages |
| MACD | Fast EMA minus slow EMA, signal EMA, and histogram; defaults 12/26/9 |
| Bollinger Bands | SMA middle and population standard deviation (`ddof=0`); defaults 20 and 2.0 |
| ATR | True Range from high, low, and previous close; SMA seed then Wilder smoothing; default 14 |

Indicators use causal historical initialization and the framework records warm-up and
initialization boundaries in research metadata. Finite EMA, MACD, and ATR seed histories
can still influence values near a threshold. Insufficient required history is rejected
rather than silently shortening the requested evaluation. See
[ARCHITECTURE.md](https://github.com/changelia/strategy-backtest-agent/blob/main/ARCHITECTURE.md)
for exact formulas and initialization policies.

The portfolio model is single-symbol, long-only, one position at a time, and uses the
available cash allocation. Short selling, leverage, stop-loss/take-profit orders,
multi-symbol portfolios, and live trading are outside the supported model.

## Execution assumptions and limitations

A signal is evaluated on a completed candle and executes at the next candle's open.
Fees apply per executed side. Spread input is the **full bid/ask spread** in basis
points, with half applied on each side; slippage is adverse basis points per side.
Buy & Hold uses the same cost assumptions. Open positions are valued using reference
prices and liquidated at their segment's final close. These are deterministic modeled
costs, not measured fills or liquidity forecasts.

The simulator assumes full fills, fractional quantities, and unlimited liquidity. It
does not model funding, taxes, or exchange lot-size constraints. Drawdown samples
candle opens and closes, not intrabar highs and lows. Historical data availability
depends on Binance, network access, rate limits, and region. Synthetic demo candles are
fixed test data, not evidence of strategy performance. Historical returns do not prove
predictive value, future profitability, or robustness.

## Reports

`strategy-backtest report` accepts existing result JSON for all six research types:
standard backtest (including the AI wrapper), comparison, validation, sensitivity,
cost scenarios, and Walk-Forward. It validates the source and produces deterministic
Markdown or JSON without fetching data or rerunning research:

```bash
strategy-backtest report --input backtest-result.json --format markdown --output report.md
strategy-backtest report --input backtest-result.json --format json --output report.json
```

The JSON report preserves normalized evidence identifiers, source paths, units,
observations, warnings, and provenance hashes. Markdown renders strategy rules and
folds in readable form. A source candle hash is provenance metadata, not proof that
the supplied data or result is authentic. Existing output paths are never overwritten.
See the [synthetic report example](https://github.com/changelia/strategy-backtest-agent/blob/main/examples/research-report.md).

AI interpretation is optional and explicitly requested with `--ai`; deterministic
reporting remains available without credentials if interpretation is unavailable or
rejected. The constrained AI layer cannot change financial evidence. Evidence references
and structured output reduce risk, but do not prove every arbitrary natural-language
claim true.

## AI configuration

The CLI loads `.env` at startup when present, with shell variables taking precedence.
For example, use placeholders in a local ignored `.env` file:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

The default model is `gpt-4.1-mini`; `OPENAI_MODEL` can override it. Natural-language
CLI parsing and optional report interpretation make OpenAI API requests and may incur
charges. The `ai` strategy command also fetches Binance history. Structured CLI configs,
`--demo`, deterministic reports, templates, and `doctor` work without OpenAI credentials.
Doctor checks only whether a nonempty key is configured; it does not verify the key or
provider availability. Never commit credentials. Python clients do not load `.env`
automatically; use `dotenv_path=` to opt in.

## Development

Install the development environment with Poetry, then run the project's checks:

```bash
poetry install
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry run strategy-backtest --demo
```

Automated tests use synthetic data and mocked OpenAI/provider boundaries; they do not
need real credentials or network calls. See
[CONTRIBUTING.md](https://github.com/changelia/strategy-backtest-agent/blob/main/CONTRIBUTING.md)
for development guidance and
[CHANGELOG.md](https://github.com/changelia/strategy-backtest-agent/blob/main/CHANGELOG.md)
for release history.

## License

[MIT](https://github.com/changelia/strategy-backtest-agent/blob/main/LICENSE).
