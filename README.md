# Strategy Backtest Agent

Strategy Backtest Agent is a Python research tool for reproducible historical strategy
backtests. It supports a Python client and command-line workflows for backtests,
strategy comparison, chronological validation, parameter sensitivity, execution-cost
scenarios, and Walk-Forward Analysis. It does not place orders or predict future
returns.

## Installation

Python 3.12 or newer and Poetry are required for the source installation below. The
documented and CI-tested installation platform is POSIX; safe report and template file
creation relies on POSIX filesystem operations.
The project is not yet confirmed as published on PyPI. After publication, the intended
install command will be `python -m pip install strategy-backtest-agent`.

For a working source installation, clone the repository and install its locked
dependencies with Poetry:

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
```

`poetry run strategy-backtest ...` uses the development environment. A normal pip
installation runs the installed `strategy-backtest` command without Poetry.

## Offline Python quick start

This example uses the bundled synthetic candles. It needs no OpenAI key, Binance
request, or network access after installation:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("backtest")
result = client.run(config=config, days=3, demo=True)

print(result.summary())
print(f"Return: {result.total_return_percent:.2f}%")
print(result.model_dump_json())
markdown = client.report(result, format="markdown")
json_report = client.report(result, format="json")
```

The result is typed and retains the fields for its research mode. `summary()` is a
human-readable view; `model_dump()` and `model_dump_json()` serialize the underlying
result. Reports are generated directly from the in-memory result without rerunning
research or fetching candles. Deterministic reports need no AI credentials. See the
[Python API reference](https://github.com/changelia/strategy-backtest-agent/blob/main/docs/PYTHON_API.md)
for complete examples of all six modes, async calls, and safe report saving.

## AI and market-data access

Natural-language parsing and optional AI report interpretation make paid OpenAI API
requests. Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL`, or pass `api_key=` and
`model=` to `BacktestClient`; explicit client settings take precedence over the
environment. The current default model is `gpt-4.1-mini`. Never put credentials in
source control. Doctor reports only whether a nonempty key is configured; it does not
test the key or provider availability.

Structured configuration, synthetic `demo=True` research, deterministic reports,
templates, and doctor diagnostics work offline. Research without `demo=True` fetches
historical OHLCV candles from Binance and requires network access. The CLI loads a
local `.env` automatically when present; shell environment variables take precedence.
Python clients read a dotenv file only when explicitly passed `dotenv_path=`.

## Research modes

All modes reuse the same validated strategy language and portfolio engine:

| Mode | Purpose | Important boundary |
| --- | --- | --- |
| Backtest | Evaluate one fixed strategy | Historical evaluation window |
| Comparison | Compare fixed strategies on shared candles | Independent portfolios and common assumptions |
| Validation | Chronological Train/Test evaluation | Test is held out only if not repeatedly inspected |
| Sensitivity | Evaluate a declared parameter grid | Train-only; no automatic selection |
| Cost scenarios | Compare declared fee/spread/slippage assumptions | Train-only; assumptions are illustrative |
| Walk-Forward | Evaluate fixed strategies across chronological windows | Independent Train/Test portfolios and Test-only aggregation |

`BacktestClient` provides `run`, `compare`, `validate`, `sensitivity`, `costs`, and
`walk_forward`. Research configs can be passed as validated models, mappings, or JSON
paths through `config=`. `template()` provides the existing backtest, comparison,
validation, and Walk-Forward templates; sensitivity and cost scenarios use their
existing configuration models.

## Strategies and execution

Supported rules use RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed-candle price,
and constants with `<`, `<=`, `>`, `>=` comparisons and nested AND/OR groups. A level
comparison such as `MACD > signal` is a state condition, not a crossover event;
crossover operators are unsupported. Short selling, leverage, stop-loss/take-profit
orders, multiple symbols in one portfolio, and live trading are outside the supported
model.

Signals use completed candles and execute at the next candle open. Fees are charged
per executed side; modeled spread is the full bid/ask spread, with half applied on each
side; slippage is adverse per side. Buy & Hold uses the same declared costs. Open
positions are liquidated at the end of their evaluation segment. Validation and
Walk-Forward segments start with independent capital. Synthetic demo prices are fixed
test data, not a performance example. Historical returns, even across multiple folds,
do not establish future profitability or statistical robustness.

## CLI quick reference

The CLI offers the same research workflows. Config-only and offline examples need no
OpenAI credentials; omit `--demo` to fetch Binance history.

```bash
strategy-backtest doctor
strategy-backtest init --type backtest --output research-config.json
set -C
strategy-backtest --config research-config.json --days 3 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
```

This sequence is offline. `set -C` makes the shell refuse to replace an existing
`result.json`; use a new working directory when rerunning it. Natural-language CLI
parsing uses OpenAI and may incur charges; its `ai` command then fetches Binance
history and has no synthetic-data option. `init` creates templates only for backtest,
comparison, validation, and Walk-Forward. All six workflows accept their existing
validated configuration JSON; sensitivity and cost scenario configs use their
documented schemas. Research result JSON is input to `report`; report JSON is a
separate evidence-grounded document. Init and report output refuse to overwrite
existing files. Full command help is available with `strategy-backtest --help`.

## License

[MIT](LICENSE).
