# Optional AI Features

OpenAI is optional. Deterministic config-driven research, Python financial
calculations, `doctor`, synthetic `--demo` runs, and report generation without `--ai`
work without OpenAI credentials. OpenAI is used only to parse natural language into
validated configuration or to interpret already-generated report evidence. The Python
engines calculate indicators, trades, portfolio results, and report metrics.

## Configure an OpenAI API key

Create an API key in [OpenAI API keys](https://platform.openai.com/api-keys) and keep it
private. The CLI can read
normal environment variables or a local `.env` file. In a POSIX shell:

```bash
export OPENAI_API_KEY="your-key-here"
export OPENAI_MODEL="gpt-4.1-mini"  # optional; this is also the default
```

For CLI-only local use, create `.env` in the working directory or a parent directory:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4.1-mini
```

The CLI loads `.env` at startup using `override=False`: already-set shell variables
win. `PYTHON_DOTENV_DISABLED=1` disables CLI discovery/loading. Never commit `.env`,
put keys in configs, or include them in prompts.

Python clients do not automatically load `.env`. The resolution order for each setting
is: explicit non-`None` constructor value, process environment, values from an
explicitly supplied `dotenv_path`, then the shared default model (`gpt-4.1-mini`).
An explicitly empty string remains empty; `api_key=None` means “use normal fallbacks,”
not “disable AI.” Python dotenv parsing is opt-in and does not mutate `os.environ`:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient(
    api_key="your-key-here",  # optional if OPENAI_API_KEY is set
    model="gpt-4.1-mini",     # optional if OPENAI_MODEL is set
    dotenv_path=".env",       # optional; Python does not search for .env by default
)
```

The client captures its settings at construction and passes them per request; it does
not temporarily change global environment variables. Do not print or store credentials
with research results.

## Parse, inspect, then execute

Natural-language parsing is a paid OpenAI request. `parse()` returns a validated model
without fetching market data or executing a backtest, so inspect the rules first:

```python
from strategy_backtest_agent import AIStrategyConfig, BacktestClient

client = BacktestClient()
config = client.parse(
    "Backtest BTCUSDT on 1h for 30 days. Buy when RSI(14) < 30 and sell when RSI(14) > 70."
)
assert isinstance(config, AIStrategyConfig)
print(config.model_dump_json(indent=2))
```

Expected: a validated config showing BTCUSDT, timeframe, period, cost assumptions and
RSI conditions. Next, inspect the conditions, then call `client.run(config=config,
demo=True)` for a separate offline synthetic run, or omit demo mode when you intend a
Binance data request.

To run the parsed strategy on fixed synthetic candles, pass the validated config to
`run(config=..., demo=True)`. That run itself is offline, but the preceding parse still
used OpenAI. Without `demo=True`, execution also fetches public Binance market data.
`demo=True` does not make parsing offline and is not a backtest quality or profitability
claim.

AI parsing exists for backtest, comparison, validation, sensitivity, and Walk-Forward.
Cost-scenario research is config-only. The CLI `ai` command performs both a paid parse
and a Binance data fetch; it has no demo option.

## Optional report interpretation

Reports are generated from existing validated results; deterministic report generation
does not call OpenAI. To request an optional interpretation:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
existing_result = client.run(config=client.template("backtest"), days=3, demo=True)
report = client.report(existing_result, format="markdown", ai=True)
```

Expected: a report generated from the in-memory synthetic result with a separate AI
interpretation status. The demo run itself is offline; the final line may call paid
OpenAI. Next, compare the explanation with the linked evidence and deterministic
metrics.

Or use `strategy-backtest report --input result.json --ai --format markdown`. AI sees
normalized evidence and its deterministic observations, not raw OHLCV candles. It
cannot replace numerical evidence. If credentials are missing, the request fails, or
structured interpretation is rejected, the deterministic report remains available and
the status explains that interpretation was unavailable or rejected.

## Errors, limits, and diagnostics

- `strategy-backtest doctor` checks whether a nonempty key is configured, not whether
  it is valid, funded, authorized, or usable. It makes no network requests.
- A configured model name does not prove OpenAI service availability.
- Unsupported or ambiguous rules are rejected; a level comparison is not treated as a
  crossover event.
- API errors are sanitized; credentials and raw provider diagnostics are not included.
- OpenAI requests require network access and may incur charges. Binance market-data
  requests also require network access and may be affected by availability, regional
  access, or rate limits.

For exact command flags, see [CLI Reference](CLI.md). For credential option signatures
and isolated client examples, see [Python API](PYTHON_API.md).
