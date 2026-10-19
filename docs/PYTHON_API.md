# Python API

`BacktestClient` calls the same validated research engines as the CLI. It does not
start subprocesses, print output, or access the network on import or construction.
Use `demo=True` for synthetic candles and offline research. Without demo mode, research
fetches historical candles from Binance. Natural-language parsing and AI report
interpretation call OpenAI and may incur charges.

Requirements and platform constraints are the same as the installed package:
Python `>=3.12,<4.0`, with POSIX filesystem output for safe new-file creation.

## Installation and client configuration

Version 1.2.0 is published and includes both the CLI and public Python API:

```bash
python -m pip install strategy-backtest-agent==1.2.0
```

For project development or unreleased source changes, follow
[Contributing](../CONTRIBUTING.md). Customer examples do not require a Git clone.

`BacktestClient()` captures environment configuration but makes no request. To
configure an AI-enabled client explicitly, supply `api_key="<your OpenAI API key>"` and optionally
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

Prerequisite: install the published package in an active Python 3.12+ virtual
environment as shown above. This example uses fixed synthetic candles, no key and no
network access.

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

Expected: a one-line summary, numeric return, and serialized raw result JSON. Next,
create a normalized report directly from `result` as shown under Reports.

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

Expected: a typed research mode and formatted summary for each result. Next, inspect
the mode-specific fields—folds, Train/Test segments, variants, scenarios, or strategy
results—rather than combining them into one portfolio.

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
The printed JSON is the parsed, validated config; no data request has occurred yet.
Next, execute that same config deliberately. `demo=True` keeps the subsequent run
offline, but parsing above remains a paid OpenAI operation.

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
json_report = client.report(result, format="json")

# Optional AI interpretation: OpenAI credentials required; may incur charges.
interpreted = client.report(result, format="markdown", ai=True)
```

Expected: Markdown and JSON strings from the same in-memory result. The optional final
call may request OpenAI. Next, save a new report file using `output=` or
`result.save_report(...)`; both refuse to overwrite.

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

Expected: a validated model and structured diagnostic object; no files are created and
nothing is printed by the client itself. Next, pass an explicit config and its workflow
to `doctor()` if you want schema validation.

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

Expected: a formatted backtest summary and Markdown character count. In a notebook or
service that already runs an event loop, call `await research()` from an async cell or
await the operation methods directly—do not call `asyncio.run()` there.

The async methods are `aparse`, `arun`, `acompare`, `avalidate`, `asensitivity`,
`acosts`, `awalk_forward`, and `areport`. AI-enabled `areport(..., ai=True)` and
`aparse()` may make paid OpenAI requests. Demo research is synthetic and offline.

## Custom market-data providers

`market_data_provider=` accepts the public `MarketDataProvider` protocol. Implement an
async `fetch_candles(symbol, timeframe, start, end) -> list[Candle]` method returning
validated candles for the requested timezone-aware UTC interval. A custom provider is
used for non-demo research and is identified as `custom` in provenance; it is not
mislabelled as Binance. `demo=True` uses the synthetic demo source and does not call the
provider. The application does not offer another built-in provider.

## Equivalent CLI usage

The Python client is optional; the installed CLI supports the same research engines.
Config mode and the demo require no OpenAI credentials or network access:

```bash
mkdir research-run  # use a new directory
cd research-run
strategy-backtest init --type backtest --output config.json
set -C
strategy-backtest --config config.json --days 3 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest doctor
```

Without `--demo`, research fetches Binance history. `strategy-backtest ai "..."`
uses OpenAI to parse a natural-language strategy and may incur charges. In a Poetry
checkout, prefix commands with `poetry run`. Version 1.2.0 is published and includes
both the `BacktestClient` API and the CLI.

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

## Public operation reference

The supported root import is `from strategy_backtest_agent import BacktestClient`.
Configuration/result models and exceptions are also exported from that package; import
them from the root rather than internal modules. Common types include
`BacktestConfig`, `AIStrategyConfig`, `ComparisonConfig`, `ValidationConfig`,
`SensitivityConfig`, `CostScenarioConfig`, `WalkForwardConfig`, their corresponding
result/report models, `RuleStrategy`, typed rule operands, `MarketDataProvider`,
`BacktestClientError`, `MarketDataError`, `StrategyParseError`, and Pydantic's
`ValidationError`.

```python
BacktestClient(
    *, api_key: str | None = None, model: str | None = None,
    dotenv_path: str | Path | None = None,
    market_data_provider: MarketDataProvider | None = None,
)
```

The `ConfigValue` input shown below means an existing Pydantic model, a mapping, or a
JSON path (`str` or `Path`). Positional `request` arguments are natural-language text
only. Supplying both
request and config, neither input, or a non-text positional input raises
`BacktestClientError`.

```python
client.parse(text: str, *, workflow: Literal[
    "backtest", "compare", "validate", "sensitivity", "walk-forward"
] = "backtest") -> BaseModel

client.run(request: str | None = None, *, config: ConfigValue | None = None,
           demo: bool = False, days: int | None = None,
           evaluation_end: datetime | None = None) -> ClientResult
client.compare(request: str | None = None, *, config: ConfigValue | None = None,
               demo: bool = False) -> ClientResult
client.validate(request: str | None = None, *, config: ConfigValue | None = None,
                demo: bool = False) -> ClientResult
client.sensitivity(request: str | None = None, *, config: ConfigValue | None = None,
                   demo: bool = False) -> ClientResult
client.costs(*, config: ConfigValue, demo: bool = False) -> ClientResult
client.walk_forward(request: str | None = None, *, config: ConfigValue | None = None,
                    demo: bool = False) -> ClientResult

client.template(workflow: Literal["backtest", "compare", "validate", "walk-forward"],
                *, output: str | Path | None = None) -> Model
client.doctor(*, workflow: Literal[
    "backtest", "compare", "validate", "sensitivity", "costs", "walk-forward"
] | None = None,
              config: ConfigValue | None = None) -> DoctorDiagnostics
client.report(source: ClientResult | BaseModel | ResearchReport |
              Mapping[str, Any] | str | Path, *,
              format: Literal["markdown", "json"] = "markdown",
              output: str | Path | None = None, ai: bool = False) -> str
```

Async equivalents are `aparse`, `arun`, `acompare`, `avalidate`, `asensitivity`,
`acosts`, `awalk_forward`, and `areport`. They accept the same inputs and return the
same model/result types. Synchronous methods raise `BacktestClientError` inside an
active event loop; use the async methods there. Invalid configs produce sanitized
`BacktestClientError`; parser rejections use `StrategyParseError`; provider failures
use `MarketDataError` or a sanitized client error. Template/report file conflicts fail
without replacing the destination.

`ClientResult.data` retains the full mode-specific Pydantic model. Its attributes are
proxied for convenient metric access. `summary()` returns formatted text;
`model_dump()` and `model_dump_json()` serialize the typed engine model; `to_json()`
returns CLI-compatible raw source JSON. `report()` instead returns normalized
deterministic report JSON or Markdown and may safely save it through `output=`.
`save_report(path, ...)` is available on the result object.

There is no separate client `save_result()` or typed result loader. Save raw result JSON
explicitly with exclusive-create mode, then pass that file to `report()`; it reads and
validates existing data without rerunning the engine:

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
result = client.run(config=client.template("backtest"), days=3, demo=True)
with Path("raw-result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
markdown = client.report("raw-result.json", format="markdown")
result.save_report("report.json", format="json")
```

Opening with mode `"x"` refuses to replace an existing result file. The report writer
also refuses to replace existing destinations.
