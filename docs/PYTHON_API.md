# Python API

`BacktestClient` is the supported in-process interface to the same deterministic research engines used by the CLI. It does not start subprocesses, print output, or access the network on import or construction. Calls that fetch Binance history require network access; `demo=True` uses only the bundled synthetic candle generator. AI parsing and report interpretation are separate optional paid API requests.

## Installation and configuration

The client requires the package runtime dependencies. Configure AI explicitly on one client or through the environment:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient(api_key="YOUR_OPENAI_API_KEY", model="gpt-4.1-mini")
```

Values resolve as explicit client setting, then `OPENAI_API_KEY` / `OPENAI_MODEL`, then an explicitly selected `dotenv_path`, and finally the default model (`gpt-4.1-mini`). An explicitly empty value remains empty. `dotenv_path` is opt-in and is read without modifying `os.environ`; shell variables take precedence. No credential value is included in result or diagnostic objects. Do not commit keys. Missing credentials do not affect structured offline runs or deterministic reports.

## Structured offline backtest

Use `config=` for a validated model, mapping or JSON file path. A positional string is always a natural-language request and is never treated as a path. Conflicting positional text and `config=` are rejected.

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
config = client.template("backtest")  # BacktestConfig
result = client.run(config=config, days=90, demo=True)
print(result.summary())
print(result.total_return_percent)
```

`run()` accepts the existing `BacktestConfig` and AI-parser `AIStrategyConfig` schemas. For a typed DSL strategy, pass an `AIStrategyConfig` with its `RuleStrategy`. Indicator and rule constructors are available from the package root: `RuleStrategy`, `Comparison`, `Group`, `Price`, `Value`, `Indicator`, `MACDIndicator`, `BollingerIndicator`, and `ATRIndicator`.

The client returns `ClientResult`. The complete mode-specific Pydantic result is available as `.data` and its fields are proxied for convenience. For strict serialization, use `.model_dump()` or `.model_dump_json()`. `to_json()` returns source research JSON accepted by the report adapter; normal report generation can use the result directly and does not require this serialization step.

## Existing research workflows

These methods use their existing validated configurations and engines. `demo=True` is supported for each and uses synthetic data.

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
comparison_config = client.template("compare")
validation_config = client.template("validate")
walk_forward_config = client.template("walk-forward")

comparison = client.compare(config=comparison_config, demo=True)
validation = client.validate(config=validation_config, demo=True)
walk_forward = client.walk_forward(config=walk_forward_config, demo=True)

# Supply the existing SensitivityConfig and CostScenarioConfig models:
sensitivity = client.sensitivity(config=sensitivity_config, demo=True)
cost_scenarios = client.costs(config=cost_scenario_config, demo=True)
```

`compare`, `validate`, `sensitivity`, and `walk_forward` also accept natural-language text, which invokes the existing structured OpenAI parser. `costs` is config-only because the current CLI has no cost-scenario parser. `template()` provides the four existing templates (`backtest`, `compare`, `validate`, `walk-forward`) as in-memory validated models; optional `output=` saves a new file and refuses to overwrite. It does not invent templates for sensitivity or costs.

Each workflow retains its own result model and methodology: independent strategy results, Train/Test segments, sensitivity variants, cost scenarios, or Walk-Forward folds are not flattened. Existing indicator initialization, execution costs, benchmark rules, and segment-local portfolio resets remain in force. The client adds no optimization or strategy selection.

## Parse before execution

Parsing is explicit and returns an existing validated config model. It does not fetch market data or execute a backtest.

```python
config = client.parse(
    "Backtest BTCUSDT on 1h for 90 days. Buy when RSI(14) is below 30 and sell above 70."
)
print(config.model_dump_json(indent=2))
result = client.run(config=config, demo=True)
```

Supported parser workflows are `backtest`, `compare`, `validate`, `sensitivity`, and `walk-forward`. Existing unsupported constructs and crossover semantics remain rejected. Natural-language parsing requires a configured key and can incur provider charges; deterministic calculations are Python operations.

## Reports from results

Report generation validates existing evidence and never reruns research or fetches candles. It is deterministic by default; AI interpretation requires `ai=True`.

```python
report_json = client.report(result, format="json")
report_markdown = result.save_report("research-report.md")

# Saving through report() is also explicit and no-overwrite:
client.report(result, format="json", output="research-report.json")

# Optional evidence-constrained AI interpretation:
interpreted = client.report(result, format="markdown", ai=True)
```

`report()` accepts a `ClientResult`, supported typed result/report, mapping, or existing JSON path. Formats are `markdown` and `json`. File output uses the existing atomic no-overwrite writer; choose a fresh destination for each run. For existing async loops use `await client.areport(...)` for AI-enabled reporting.

## Async applications

Synchronous network-backed methods use `asyncio.run` only when no event loop is active. In an async application, use the corresponding awaitable method; synchronous methods fail clearly instead of nesting event loops.

```python
import asyncio
from strategy_backtest_agent import BacktestClient

async def research() -> None:
    client = BacktestClient()
    config = client.template("backtest")
    result = await client.arun(config=config, days=90, demo=True)
    report = await client.areport(result, format="json")
    print(result.summary())

asyncio.run(research())
```

Async counterparts are `aparse`, `arun`, `acompare`, `avalidate`, `asensitivity`, `acosts`, `awalk_forward`, and `areport`. They call the same parsers and research engines as their synchronous counterparts.

## Diagnostics and errors

`client.doctor()` returns `DoctorDiagnostics` without printing, exiting, validating unspecified files, or making network requests. Pass both `workflow=` and `config=` to validate one explicitly supplied config. A present key only means a nonempty value was configured; it does not prove provider validity or availability.

Invalid client input and safe-output failures raise `BacktestClientError`; model errors raised by explicit parsing retain `StrategyParseError`, and unsupported Pydantic input can be inspected through the exported `ValidationError`. Provider and parser errors retain their existing sanitized behavior. Key values are omitted from `repr(client)`, summaries, reports, and doctor output.

## Limits

This is historical research software, not live trading, investment advice, or a forecast. `demo=True` is synthetic and is not a profitability example. Historical results do not establish future performance. API parsing and optional interpretation are not deterministic financial calculations, and provider behavior is not tested by offline examples. The package preserves the current workflows and their limits; it does not add indicators, data providers, optimization, crossover rules, or new report schemas.
