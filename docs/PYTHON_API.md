# Python API

`BacktestClient` calls the same validated research engines as the CLI. It does not
start subprocesses, print output, or access the network on import or construction.
Use `demo=True` for synthetic candles and offline research. Without demo mode, research
fetches historical candles from Binance. Natural-language parsing and AI report
interpretation call OpenAI and may incur charges.

Requirements and platform constraints are the same as the installed package:
Python `>=3.12,<4.0`, with POSIX filesystem output for safe new-file creation.

## Contents

- [Installation and client configuration](#installation-and-client-configuration)
- [Start with your own strategy](#start-with-your-own-strategy)
- [Structured offline backtest](#structured-offline-backtest)
- [All six research modes](#all-six-research-modes)
- [Parse, inspect, then execute](#parse-inspect-then-execute)
- [Results, serialization and reports](#results-serialization-and-reports)
- [Templates and diagnostics](#templates-and-diagnostics)
- [Async applications](#async-applications)
- [Custom market-data providers](#custom-market-data-providers)
- [Result types and metric access](#result-types-and-metric-access)
- [Public operation reference](#public-operation-reference)
- [Input, error and diagnostics reference](#input-error-and-diagnostics-reference)

## Installation and client configuration

Version 1.2.0 is published and includes both the CLI and public Python API:

```bash
python -m pip install strategy-backtest-agent
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

## Start with your own strategy

Follow the [first-script tutorial](QUICK_START.md#2-create-and-run-your-first-python-script)
for an editable `BacktestConfig`. To describe your strategy in English, follow the
[complete parse-inspect-run journey](AI.md#parse-inspect-and-execute-in-python).
Both can produce reports directly from in-memory results. Choose explicit structured
inputs when you want no paid AI parsing.

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

An optional template is a starting point, not an automatically selected strategy.
The backtest template uses BTCUSDT/1h, RSI(14) entry below 30 / exit above 70, initial
cash 10000, fee 0.001, spread 10 bps and slippage 5 bps. You can edit a dumped mapping
and revalidate it; frozen Pydantic models cannot be assigned to directly:

```python
from strategy_backtest_agent import BacktestClient, BacktestConfig

client = BacktestClient()
values = client.template("backtest").model_dump()
values["entry_rsi"] = 25.0
config = BacktestConfig.model_validate(values)
result = client.run(config=config, days=30, demo=True)
print(result.summary())
```

`run(request, ...)` accepts a natural-language request and parses it before research.
Its direct DSL output path currently has a [known strict timestamp validation defect](AI.md#direct-natural-language-execution);
use separate `parse()` then `run(config=...)` for single-strategy DSL research.
`run(config=...)` accepts the existing `BacktestConfig` or `AIStrategyConfig` model.
Both may also receive mappings or JSON paths. Use `days=` only for a backtest template;
parsed and `AIStrategyConfig` durations must agree with their configuration. `demo=True`
uses the fixed synthetic series and its 2024-07-01 UTC end.

For complete individual Python/CLI workflows and all configuration fields, see
[Research Guide](RESEARCH_GUIDE.md#six-complete-research-workflows).

`ClientResult.data` is the complete mode-specific Pydantic result; fields are also
proxied on `ClientResult`. `summary()` provides a concise text view, `model_dump()`
returns a dictionary of the typed result data, and `model_dump_json()` serializes it strictly. `to_json()`
returns the CLI-compatible source result accepted by the report adapter.

### Models, mappings and JSON paths

Prerequisites: installed package, fresh writable working directory. This complete
example is offline and creates one **configuration**, not a raw result. All three
input forms run the same validated legacy RSI settings:

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, BacktestConfig

client = BacktestClient()
config = BacktestConfig(entry_rsi=25.0, exit_rsi=70.0)
with Path("settings.json").open("x", encoding="utf-8") as stream:
    stream.write(config.model_dump_json(indent=2))
from_model = client.run(config=config, days=30, demo=True)
from_mapping = client.run(config=config.model_dump(), days=30, demo=True)
from_path = client.run(config=Path("settings.json"), days=30, demo=True)
assert from_model.to_json() == from_mapping.to_json() == from_path.to_json()
print(from_path.summary())
```

Expected: identical raw source JSON and one printed summary. A positional
`client.run("settings.json")` would ask AI to parse that text; it is not file loading.

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
backtest = client.run(config=client.template("backtest"), days=3, demo=True)
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

for result in (backtest, comparison, validation, sensitivity, costs, walk_forward):
    print(result.research_type)
    print(result.summary())
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

## Results, serialization and reports

`report()` accepts a `ClientResult` or an existing supported typed result/report,
JSON-compatible mapping, or JSON path. Use `model_dump(mode="json")` for mappings
containing timestamps. It validates and renders existing evidence; it never reruns a
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

To save a template and diagnose it explicitly (offline, fresh directory):

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("compare", output="comparison-config.json")
diagnostics = client.doctor(workflow="compare", config=config)
print(diagnostics.config_valid)  # True
print(diagnostics.offline_ready)  # True when the local synthetic check passes.
```

The config file is created without overwriting. Diagnostics are structured; nothing
is printed until your `print` calls. CLI doctor is limited to the four template model
types; Python doctor additionally supports sensitivity/cost configs.

## Async applications

Use async methods inside an existing event loop. They share the same implementation
as synchronous calls. `parse`, `run`, `compare`, `validate`, `sensitivity`, `costs`
and `walk_forward` use the synchronous wrapper and reject an active loop. `template`,
`doctor` and `report(ai=False)` remain callable there; use `areport(ai=True)` for AI
interpretation inside that loop.

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

For optional AI in async applications, configure a key before constructing the client,
then await parsing and interpretation. Complete example (paid OpenAI, synthetic run):

```python
import asyncio
from strategy_backtest_agent import BacktestClient

async def ai_research() -> None:
    client = BacktestClient()  # OPENAI_API_KEY supplied through the environment.
    config = await client.aparse(
        "Backtest BTCUSDT on 1h for 30 days using RSI(14) below 30 and above 70."
    )
    print(config.model_dump_json(indent=2))
    result = await client.arun(config=config, demo=True)
    text = await client.areport(result, ai=True, output="async-ai.md")
    print(result.summary(), len(text))

asyncio.run(ai_research())
```

Expected: config, summary and report character count; a new `async-ai.md` report with
AI status/fallback. Two OpenAI operations are requested (parse and interpretation),
no Binance request. In a notebook use `await ai_research()` instead of the final line.

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

Prerequisite: installed package; run this complete script from a fresh directory.
It generates all requested hourly candles, including prior warm-up, with no network.
The fixed UTC boundary makes the example repeatable. Returned candles must be sorted,
unique, complete and valid OHLCV for `[start, end)`. Do not return only evaluation
candles when the caller asks for earlier initialization data.

```python
"""Complete local OHLCV provider; no Binance or OpenAI calls.

The provider generates every requested hourly candle, including any requested prior
warm-up history. This is artificial data, not another built-in market-data service.
"""

from datetime import UTC, datetime, timedelta

from strategy_backtest_agent import (
    AIStrategyConfig,
    BacktestClient,
    Candle,
    Comparison,
    Indicator,
    RuleStrategy,
    Value,
)


class LocalHourlyProvider:
    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        if symbol != "BTCUSDT" or timeframe != "1h":
            raise ValueError("This example supports BTCUSDT 1h only")
        epoch = datetime(2020, 1, 1, tzinfo=UTC)
        cursor = start
        candles = []
        while cursor < end:
            hour = int((cursor - epoch).total_seconds() // 3600)
            close = 100.0 + (hour % 48) / 2
            candles.append(
                Candle(
                    timestamp=cursor,
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=10.0,
                )
            )
            cursor += timedelta(hours=1)
        return candles


client = BacktestClient(market_data_provider=LocalHourlyProvider())
config = AIStrategyConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    period_days=3,
    strategy=RuleStrategy(
        entry=Comparison(
            left=Indicator(name="rsi", period=14), operator="<", right=Value(value=30.0)
        ),
        exit=Comparison(
            left=Indicator(name="rsi", period=14), operator=">", right=Value(value=70.0)
        ),
    ),
)
result = client.run(config=config, evaluation_end=datetime(2024, 7, 1, tzinfo=UTC))
assert result.data_source == "custom"
print(result.summary())
print("Source:", result.data_source)
result.save_report("custom-report.md")
result.save_report("custom-report.json", format="json")
```

Expected: a backtest summary, `Source: custom`, and two deterministic report files.
This is artificial data; provenance identifies a custom provider, not verified market
history. For production research, supply your own validated source history for the
entire requested interval. No separate provider request is made for each indicator.

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
uses OpenAI to parse a natural-language strategy and may incur charges. For source/Poetry development, see [Contributing](../CONTRIBUTING.md). Version 1.2.0
is published and includes both the `BacktestClient` API and the CLI.

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

## Result types and metric access

`research_type` is `backtest`, `compare`, `validate`, `sensitivity`, `costs`, or
`walk-forward` (not the spelling of the CLI display title). The wrapper preserves
mode-specific types; no single continuous portfolio is implied.

| Operation | `result.data` model | Example access |
| --- | --- | --- |
| `run` | Validated CLI backtest model | `result.final_balance`, `result.total_return_percent`, `result.costs.fees` |
| `compare` | `ComparisonResult` | `result.results[0].result.total_return_percent`, `result.ranking`, `result.shared_data.source` |
| `validate` | `ValidationReport` | `result.results[0].test.result.total_trades`, `result.split.test_start` |
| `sensitivity` | `SensitivityReport` | `result.results[0].train.result.total_return_percent`, `result.summary()` (text), `result.data.summary.variant_count` |
| `costs` | `CostScenarioReport` | `result.results[0].return_difference_pp`, `result.results[0].execution.fee_rate` |
| `walk_forward` | `WalkForwardReport` | `result.folds[0].test_start`, `result.summaries[0].positive_test_folds` |

`summary()` is a wrapper method, so sensitivity's typed `summary` object is accessed
through `result.data.summary`. All nested `result` financial models have balance,
return, drawdown, completed trade, win-rate, profit-factor and cost fields. Returns,
win rate and signed drawdown are percentages; excess/difference fields ending in `_pp`
are percentage points. `positive_test_fraction` is a fraction (0–1), not a percentage.
Metrics that are undefined remain `None` / JSON `null`, including zero-trade win rate
or profit factor without a losing-trade denominator. They must not be replaced by zero.

## Public operation reference

The supported root import is `from strategy_backtest_agent import BacktestClient`.
Configuration/result models and exceptions are also exported from that package; import
them from the root rather than internal modules. Common types include
`BacktestConfig`, `AIStrategyConfig`, `ComparisonConfig`, `ValidationConfig`,
`SensitivityConfig`, `CostScenarioConfig`, `WalkForwardConfig`, their corresponding
result/report models, `RuleStrategy`, typed rule operands, `MarketDataProvider`,
`BacktestClientError`, `MarketDataError`, `StrategyParseError`, and Pydantic's
`ValidationError`.

```text
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

```text
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
client.doctor(*, workflow: str | None = None,
              config: ConfigValue | None = None) -> DoctorDiagnostics
client.report(source: ClientResult | BaseModel | ResearchReport |
              Mapping[str, Any] | str | Path, *,
              format: Literal["markdown", "json"] = "markdown",
              output: str | Path | None = None, ai: bool = False) -> str
```

Async equivalents are `aparse`, `arun`, `acompare`, `avalidate`, `asensitivity`,
`acosts`, `awalk_forward`, and `areport`. They accept the same inputs and return the
same model/result types. The synchronous execution/parsing methods listed above raise `BacktestClientError`
inside an active event loop; `template`, `doctor` and `report(ai=False)` do not. Invalid configs produce sanitized
`BacktestClientError`; parser rejections use `StrategyParseError`; provider failures
use `MarketDataError` or a sanitized client error. Template/report file conflicts fail
without replacing the destination.

`ClientResult.data` retains the full mode-specific Pydantic model. Its attributes are
proxied for convenient metric access. `summary()` returns formatted text;
`model_dump()` and `model_dump_json()` serialize the typed engine model; `to_json()`
returns CLI-compatible raw source JSON. `report()` instead returns normalized
deterministic report JSON or Markdown and may safely save it through `output=`.
`save_report(path, ...)` is available on the result object.

Serialization details:

- `model_dump(mode="python")` (default) is a dictionary which may contain `datetime`
  objects. Use `mode="json"` for JSON-compatible types.
- `model_dump_json()` returns strict JSON for `data` and accepts no formatting options
  on the wrapper. Use `result.data.model_dump_json(indent=2)` for pretty typed JSON.
- `to_json()` returns the original CLI-compatible source, including the AI request /
  parsed-config envelope when natural language was executed directly. Therefore it can
  differ from `model_dump_json()`. Prefer it when saving raw results for later reports.
- `report(..., format="json")` is a normalized evidence report, not raw result JSON.
  Source content SHA256 depends on the exact input bytes, so reformatting raw JSON can
  change provenance hashes even when financial values match.

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

## Input, error and diagnostics reference

`ConfigValue` is descriptive notation in this guide, not a promised root export.
`config=` accepts the appropriate validated model, a mapping, or a JSON file path.
`Path("input.json")` and `"input.json"` are paths only under `config=`; a positional
string is always a natural-language request. No stdin, subprocess or implicit file
exchange is required. Models are frozen and reject unknown fields/non-finite numbers.

| Input/setting | Default and constraints |
| --- | --- |
| `request` | `None`; exactly one of request/config is required. Costs accepts config only. |
| `demo` | `False`; default Binance (or injected provider). `True` bypasses providers, uses synthetic data. |
| `days` on `run` | `None`; resolves to 180 for `BacktestConfig`, or the config/parsed `period_days`. Positive integer; conflicts with explicit config duration fail. |
| `evaluation_end` on `run` | `None`; aware datetime; live uses current UTC, demo fixed 2024-07-01 UTC. An explicit different demo end fails. |
| `workflow` on parse | `"backtest"`; also `compare`, `validate`, `sensitivity`, `walk-forward`; returns the matching validated config. No costs parser. |
| `format` on reports | `"markdown"`; alternatively `"json"`; return type is always `str`. |
| `output` | `None`; no write. If supplied, create safely without overwrite or symlink traversal. |
| `ai` on reports | `False`; `True` requests optional paid interpretation with fallback. |

Constructor defaults are `None` for all four settings. An explicit key/model overrides
environment, then explicit dotenv values; the model finally defaults to `gpt-4.1-mini`.
An absent key is acceptable. `None` permits fallback; an explicit empty string blocks
fallback. Settings are captured at construction, so construct a new client to use a
subsequent environment change. Construction makes no provider/AI connection. See
[AI configuration](AI.md#setting-precedence-and-empty-values).

`BacktestClientError` covers conflicting inputs, sanitized config/file/report problems,
and synchronous calls in an active loop. `StrategyParseError` (a `ValueError`) covers
rejected natural language and sanitized AI failures. `ValidationError` is available
for direct Pydantic model construction; engine validation may raise `ValueError`.
`MarketDataError` covers data retrieval failures; caller-supplied providers can also
raise their own exceptions. Library calls do not print or raise `SystemExit` as an API
error policy. Catch only errors you can handle and do not print credentials:

```python
from strategy_backtest_agent import BacktestClient, BacktestClientError

client = BacktestClient()
try:
    client.run(config={"unknown": "field"}, demo=True)
except BacktestClientError as error:
    print(str(error))  # Sanitized invalid-configuration message.
```

### Templates and doctor workflow differences

`template` supports only four kinds. `compare` defaults to two independent RSI(14)
strategies (30/70 and 25/70), 30 days; `validate` to one RSI(14), 30 days and 70% Train;
`walk-forward` to one RSI(14), 60 days, rolling 30-day Train/10-day Test/10-day step,
max 10 folds and stitching enabled. All use BTCUSDT 1h, cash 10000, fee 0.001,
spread 10 bps, slippage 5 bps; research templates fix end at 2024-07-01 UTC. Backtest
has no duration/end in its model. Saving a template is explicit via `output=`.

Python `doctor(workflow=..., config=...)` accepts all six workflow model selectors:
`backtest`, `compare`, `validate`, `sensitivity`, `costs`, `walk-forward`. `backtest`
means `BacktestConfig`, not `AIStrategyConfig`. Both arguments are required together.
Invalid config returns `config_valid=False` and a warning; an unknown workflow raises
`BacktestClientError`. Without a config it returns `config_valid=None`.
CLI doctor supports only the four init types and uses `--type`, not `workflow=`.

Diagnostics expose Python compatibility, installed metadata/version, source checkout
version when known, an offline synthetic-data check, credential presence/source,
model configuration/source, config status and warnings. They reveal no key/model value
and make no requests. Installed metadata is not proof of source checkout version;
doctor distinguishes them. No config is scanned or repaired. Missing optional AI does
not mean offline research is unavailable.

### Public model families

Import supported models from `strategy_backtest_agent`, not internal module paths:

| Role | Public types |
| --- | --- |
| Account/data/execution | `BacktestConfig`, `BacktestResult`, `Candle`, `Trade`, `ExecutionConfig`, `ExecutionFill`, `ExecutionCostTotals` |
| Strategy operands/rules | `RSIStrategy`, `RuleStrategy`, `Rule`, `Comparison`, `Group`, `Price`, `Value`, `Indicator`, `MACDIndicator`, `BollingerIndicator`, `ATRIndicator`, `TechnicalIndicator`, `Operand`, `IndicatorInitialization` |
| Research configuration | `AIStrategyConfig`, `MarketConfig`, `SharedConfig`, `NamedStrategy`, `ComparisonConfig`, `ValidationConfig`, `SensitivityConfig`, `ParameterSpec`, `NumericRange`, `NearbyValues`, `CostScenarioConfig`, `CostScenario`, `WalkForwardConfig`, `WalkForwardWindowConfig` |
| Research results | `ComparisonResult`, `StrategyResult`, `SharedData`, `ValidationReport`, `StrategyValidationResult`, `ChronologicalSplit`, `SegmentResult`, `SensitivityReport`, `SensitivitySharedData`, `SensitivitySummary`, `ParameterDefinition`, `ParameterVariant`, `VariantResult`, `NeighborComparison`, `SeriesPoint`, `ReturnMatrix`, `CostScenarioReport`, `CostScenarioResult`, `WalkForwardReport`, `WalkForwardFold`, `FoldStrategyResult`, `WalkForwardSummary`, `IndexPoint` |
| Reporting | `ResearchReport`, `ResearchSource`, `ResearchEvidence`, `EvidenceScope`, `EvidenceMetric`, `EvidenceObservation`, `EvidenceLimitation`, `AIInterpretation` |
| Client/support | `BacktestClient`, `ClientResult`, `DoctorDiagnostics`, `MarketDataProvider`, `Model`, `StrictModel`, `BacktestClientError`, `MarketDataError`, `StrategyParseError`, `ValidationError` |

Result types are produced by existing engines; users need not construct them to run
research. The standalone wrapper's validated `data` includes CLI metadata in addition
to financial `BacktestResult` fields; do not assume raw backtest/report JSON is just a
`BacktestResult`. Use `to_json()` for reusable raw source, and `report()` for evidence.

### ClientResult method signatures

Reference notation (not a script to execute):

```text
result.summary() -> str
result.model_dump(*, mode: str = "python") -> dict[str, Any]
result.model_dump_json() -> str
result.to_json() -> str
result.save_report(path: str | Path, *, format: Literal["markdown", "json"] = "markdown",
                   ai: bool = False) -> str
```

`save_report` delegates to the originating client's `report`, reusing its captured
AI settings if `ai=True`. It refuses overwrite and returns rendered content. For an
AI report from inside an active loop use `await client.areport(result, output=...,
ai=True)`; there is no separate async result-save method. Deterministic report saving
does not call a provider or rerun research.
