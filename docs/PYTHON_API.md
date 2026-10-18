# Python API

`BacktestClient` calls the same validated research engines as the CLI. It does not
start subprocesses, print output, or access the network on import or construction.
Use `demo=True` for synthetic candles and offline research. Without demo mode, research
fetches historical candles from Binance. Natural-language parsing and AI report
interpretation call OpenAI and may incur charges.

## Installation and client configuration

The released v1.1.0 CLI is installed with pip:

```bash
python -m pip install strategy-backtest-agent==1.1.0
```

That release does not include the `BacktestClient` API described here. The API is an
unreleased preview on `feat/public-python-api`. To install the preview from source,
use Python 3.12 or newer, Poetry, and the documented POSIX platform:

```bash
git clone --branch feat/public-python-api https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
poetry run python -c 'from strategy_backtest_agent import BacktestClient; print(BacktestClient())'
```

`BacktestClient()` uses the preview source environment. To configure an AI-enabled
client explicitly, supply `api_key="<your OpenAI API key>"` and optionally
`model="gpt-4.1-mini"`. No real credentials belong in examples or source control.

For each setting, precedence is explicit client value, environment (`OPENAI_API_KEY`
or `OPENAI_MODEL`), explicitly selected dotenv file, then the model default
(`gpt-4.1-mini`). Pass `dotenv_path=".env"` to opt in; its values are read without
modifying `os.environ`. The CLI's automatic `.env` loading does not apply to Python
clients. Explicit empty settings remain empty. Never commit real keys. Neither a key's
presence nor a model name establishes provider validity or availability.
`api_key=None` means “unspecified” and therefore allows environment or dotenv fallback;
it does not disable AI configuration. A plain `BacktestClient()` still performs no AI
request unless parsing or `ai=True` interpretation is explicitly requested.

## Structured offline backtest

`config=` accepts an existing validated model, mapping, or JSON file path. A positional
string is natural-language text only; the client never guesses whether it is a filename.
Do not supply both forms.

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("backtest")  # BacktestConfig
result = client.run(config=config, days=3, demo=True)

print(result.summary())
print(result.total_return_percent)
result_json = result.model_dump_json()
```

`run(request, ...)` accepts a natural-language request and parses it before research.
`run(config=...)` accepts the existing `BacktestConfig` or `AIStrategyConfig` model.
Both may also receive mappings or JSON paths. Use `days=` only for a backtest template;
parsed and `AIStrategyConfig` durations must agree with their configuration. `demo=True`
uses the fixed synthetic series and its 2024-07-01 UTC end.

`ClientResult.data` is the complete mode-specific Pydantic result; fields are also
proxied on `ClientResult`. `summary()` provides a concise text view, `model_dump()`
returns the typed result data, and `model_dump_json()` serializes it strictly. `to_json()`
returns the CLI-compatible source result accepted by the report adapter.

## All six research modes

The client methods are `run`, `compare`, `validate`, `sensitivity`, `costs`, and
`walk_forward`. Their async equivalents are `arun`, `acompare`, `avalidate`,
`asensitivity`, `acosts`, and `awalk_forward`. The four shipped templates are
`backtest`, `compare`, `validate`, and `walk-forward`. Sensitivity and cost scenarios
use their existing exported config models. This complete offline example constructs
those two configs explicitly and uses templates for the other modes:

```python
from datetime import UTC, datetime

from strategy_backtest_agent import (
    BacktestClient,
    Comparison,
    CostScenario,
    CostScenarioConfig,
    Indicator,
    ParameterSpec,
    Price,
    RuleStrategy,
    SensitivityConfig,
    Value,
)

client = BacktestClient()
comparison = client.compare(config=client.template("compare"), demo=True)
validation = client.validate(config=client.template("validate"), demo=True)
walk_forward = client.walk_forward(
    config=client.template("walk-forward"), demo=True
)

strategy = RuleStrategy(
    entry=Comparison(
        left=Indicator(name="rsi", period=14), operator="<", right=Value(value=30.0)
    ),
    exit=Comparison(
        left=Indicator(name="rsi", period=14), operator=">", right=Value(value=70.0)
    ),
)
sensitivity_config = SensitivityConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    period_days=3,
    initial_balance=10000,
    fee=0.001,
    evaluation_end=datetime(2024, 7, 1, tzinfo=UTC),
    base_strategy=strategy,
    parameters=[ParameterSpec(path="entry.right.value", values=[25.0, 30.0])],
)
sensitivity = client.sensitivity(config=sensitivity_config, demo=True)

cost_config = CostScenarioConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    period_days=3,
    initial_balance=10000,
    fee=0.001,
    evaluation_end=datetime(2024, 7, 1, tzinfo=UTC),
    strategy=strategy,
    scenarios=[
        CostScenario(id="baseline", name="Baseline"),
        CostScenario(
            id="modeled-costs", name="Illustrative costs", spread_bps=10, slippage_bps=5
        ),
    ],
)
costs = client.costs(config=cost_config, demo=True)

print(comparison.research_type, validation.research_type, sensitivity.research_type)
print(costs.research_type, walk_forward.research_type)
```

`compare`, `validate`, `sensitivity`, and `walk_forward` accept natural-language text
through their existing parsers; that parse is a paid OpenAI request. `costs` is
config-only. Each result retains its mode-specific structures: comparison strategies,
Train/Test segments, sensitivity variants, cost scenarios, or Walk-Forward folds.
Results are not flattened into one common financial report model.

## Parse, inspect, then execute

Parsing is separate from execution. It returns a validated existing configuration and
does not fetch candles. This example requires OpenAI credentials and may incur charges;
execution itself uses synthetic candles because `demo=True`.

```python
from strategy_backtest_agent import BacktestClient, AIStrategyConfig

client = BacktestClient()  # Reads OPENAI_API_KEY / OPENAI_MODEL when present
config = client.parse(
    "Backtest BTCUSDT on 1h for 3 days. Buy when RSI(14) is below 30 "
    "and sell when RSI(14) is above 70."
)
assert isinstance(config, AIStrategyConfig)
print(config.model_dump_json(indent=2))
result = client.run(config=config, demo=True)
```

The parser validates supported rule structures and rejects unsupported crossover
semantics. It does not calculate indicators, trades, or financial metrics.

## Reports directly from results

`report()` accepts a `ClientResult` or an existing supported typed result/report,
mapping, or JSON path. It validates and renders existing evidence; it never reruns a
backtest or fetches market data. Default Markdown and JSON reports are deterministic
and offline. Optional AI interpretation is a separate paid OpenAI request and must be
explicitly enabled with `ai=True`.

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
result = client.run(config=client.template("backtest"), days=3, demo=True)
markdown = client.report(result, format="markdown")
json_report = result.save_report("research-report.json", format="json")

# Optional AI interpretation: OpenAI credentials required; may incur charges.
interpreted = client.report(result, format="markdown", ai=True)
```

Both `report(..., output=...)` and `result.save_report(path, ...)` create a new file
and refuse to overwrite. `report()` returns the rendered string, including when it also
writes to `output=`. JSON reports preserve normalized evidence, source and evidence
hashes, provenance, warnings, and optional interpretation. AI interpretation uses the
existing constrained structured response and falls back to deterministic output when
unavailable or rejected. It does not change financial evidence.

## Templates and diagnostics

`template(kind)` returns a validated in-memory model. `output=` optionally saves it to
a new path without overwriting. Supported kinds are `backtest`, `compare`, `validate`,
and `walk-forward`; it does not create sensitivity or cost configs.

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
template = client.template("backtest")
diagnostics = client.doctor()
print(diagnostics.offline_ready, diagnostics.api_key_present)
```

`doctor()` returns structured, offline diagnostics and does not print, exit, repair
files, or validate an unspecified config. A configured key means only that a nonempty
value exists; no provider check is made. Pass both `workflow=` and `config=` to
validate one explicit configuration.

## Async applications

Use async methods inside an existing event loop. They share the same implementation
as synchronous calls; synchronous methods report an error rather than nesting
`asyncio.run()` when called from an active loop.

```python
import asyncio
from strategy_backtest_agent import BacktestClient

async def research() -> None:
    client = BacktestClient()
    result = await client.arun(config=client.template("backtest"), days=3, demo=True)
    markdown = await client.areport(result, format="markdown")
    print(result.summary(), len(markdown))

asyncio.run(research())
```

The async methods are `aparse`, `arun`, `acompare`, `avalidate`, `asensitivity`,
`acosts`, `awalk_forward`, and `areport`. AI-enabled `areport(..., ai=True)` and
`aparse()` may make paid OpenAI requests. Demo research is synthetic and offline.

## Equivalent CLI usage

The Python client is optional; the installed CLI supports the same research engines.
Config mode and the demo require no OpenAI credentials or network access:

```bash
mkdir research-run
cd research-run
strategy-backtest init --type backtest --output config.json
set -C
strategy-backtest --config config.json --days 3 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest doctor
```

Without `--demo`, research fetches Binance history. `strategy-backtest ai "..."`
uses OpenAI to parse a natural-language strategy and may incur charges. In a Poetry
checkout, prefix commands with `poetry run`. This CLI example describes the released
v1.1.0 command line; the API preview is separately installed from its feature branch.

## Supported rules, execution, and limitations

Rule strategies support RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed-candle
price, constants, level comparisons (`<`, `<=`, `>`, `>=`), and nested AND/OR groups.
MACD state comparisons are not crossover events; crossover operators are unsupported.
Rule complexity and indicator period limits are validated by the existing DSL.

Signals use a completed candle and execute at the next candle open. Fees are charged
per executed side; spread input is the full spread, with half applied to each side;
slippage is adverse per side. Buy & Hold uses the same declared costs. Positions are
liquidated at the final close of their segment. Validation and Walk-Forward segments
use independent portfolios. Modeled costs are assumptions, not measured fills.

Sensitivity evaluates only its declared Train grid and does not select parameters.
Walk-Forward aggregates independent Test folds; a stitched index compounds normalized
fold returns and does not represent carried positions. Repeatedly inspecting Test
periods contaminates their held-out role. Historical results and synthetic demo data
do not establish future profitability or statistical robustness. The client adds no
indicators, providers, optimization, live trading, or investment advice.
