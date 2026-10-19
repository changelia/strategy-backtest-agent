# Troubleshooting

Start with `strategy-backtest doctor` for an offline environment check. It never
contacts OpenAI or Binance and does not validate an unspecified research config.

## Installation or command not found

Confirm the virtual environment is active and install the package into that same
interpreter:

```bash
python --version
python -m pip show strategy-backtest-agent
python -m pip install --upgrade strategy-backtest-agent==1.2.0
```

Python must satisfy `>=3.12,<4.0`. If `strategy-backtest` is not found, use the
environment's `bin/strategy-backtest` executable (POSIX) or reactivate its virtual
environment. Check `python -m pip show` and `which strategy-backtest` to catch a
different Python installation. Import package name is `strategy_backtest_agent`.
File-output operations require POSIX filesystem behavior; Windows file output is not
supported.

## Missing OpenAI key or AI request failure

Config-only runs, synthetic demo, doctor, and deterministic reports do not need a key.
For AI parsing or report interpretation, set `OPENAI_API_KEY` or use the CLI's local
`.env` support. Python clients require explicit `dotenv_path=` to read a dotenv file.
An empty explicit Python key remains empty; `api_key=None` falls through to environment
and dotenv settings.

If parsing fails, shorten the request, state one symbol/timeframe/period, and describe
supported level conditions (for example, `RSI(14) < 30`). Crossovers, short sales,
leverage, stops, and predictions are unsupported. If OpenAI reports an error, verify
the key/model privately and check provider availability; `doctor` verifies presence
only. Do not paste keys into prompts or issue reports. API errors are sanitized.

## Binance or network failures

Historical market-data workflows need network access to Binance. Check connectivity,
symbol spelling, timeframe, requested date range, regional access, and rate limits.
Fixed UTC evaluation dates do not guarantee data availability. The provider may reject
missing candle history or gaps needed for rule warm-up. For offline capability checks,
use `--demo` with a supported CLI config workflow or `demo=True` with the Python API.
Sensitivity/cost CLI commands have no demo option.

## Invalid configuration or insufficient history

Configs are strict: misspelled or extra fields are rejected. Use the config model for
the selected command. `strategy-backtest init --type` supports only `backtest`,
`compare`, `validate`, and `walk-forward`. Sensitivity and cost configs are available
as complete JSON examples under `examples/` and in the research guide.

The root backtest command takes duration as `--days`; shared research configs use
`period_days`. For hourly data, whole-day periods align to candle counts. Increase
history or lower indicator periods only when that change is part of your declared
research plan. The engine intentionally rejects incomplete windows or unavailable
warm-up rather than silently shortening the evaluation.

`--demo` is allowed only with validated config mode for compare, validate and
walk-forward; it is not accepted for sensitivity or costs. It does not make AI parsing
offline. `costs` accepts only `--config` and optional `--json`, not natural-language
requests.

## Existing output path

Config and report writes refuse overwrites, including symlink destinations. Choose a
new output name or a fresh working directory. For JSON stdout redirected by the shell,
enable noclobber first (`set -C`) or redirect to a unique new path. Do not remove a
file that may contain research you want to preserve.

## Python event-loop errors

Synchronous `BacktestClient` methods cannot run inside an active asyncio event loop.
In a notebook or async service, await the matching `a...` method such as
`await client.arun(...)` or `await client.areport(...)`; do not call `asyncio.run()`
inside an already running loop.

## Report input errors

`strategy-backtest report` requires an existing complete result JSON from a supported
research workflow. It does not accept a configuration file and does not rerun research.
Pass raw engine JSON, not a normalized report JSON, as a new source input. If schema
validation fails, regenerate output using that workflow's `--json` flag and inspect
the original file without editing financial fields by hand.

For more details, see [CLI Reference](CLI.md), [AI Guide](AI.md), and
[Research Guide](RESEARCH_GUIDE.md).
