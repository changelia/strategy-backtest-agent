# Troubleshooting

Start with `strategy-backtest doctor` for an offline environment check. It never
contacts OpenAI or Binance and does not validate an unspecified research config.

## Installation or command not found

Confirm the virtual environment is active and install the package into that same
interpreter:

```bash
python --version
python -m pip show strategy-backtest-agent
python -m pip install --upgrade strategy-backtest-agent
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

`parse`, `run`, `compare`, `validate`, `sensitivity`, `costs` and `walk_forward`
use a synchronous wrapper that rejects an active asyncio event loop.
In a notebook or async service, await the matching `a...` method such as
`await client.arun(...)` or `await client.areport(...)`; do not call `asyncio.run()`
inside an already running loop. `template()`, `doctor()` and `report(ai=False)`
remain callable inside a loop. For `report(ai=True)`, use `await client.areport(...,
ai=True)` instead.

## Report input errors

`strategy-backtest report` requires an existing complete result JSON from a supported
research workflow. It does not accept a configuration file and does not rerun research.
Pass raw engine JSON, not a normalized report JSON, as a new source input. If schema
validation fails, regenerate output using that workflow's `--json` flag and inspect
the original file without editing financial fields by hand.

For more details, see [CLI Reference](CLI.md), [AI Guide](AI.md), and
[Research Guide](RESEARCH_GUIDE.md).

## Error messages and practical fixes

These are messages or message families emitted by the current implementation; do
not include credentials when sharing an error report.

| Error / symptom | Likely cause | What to do |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'strategy_backtest_agent'` | Different interpreter/venv, or not installed | Activate your venv, run `python -m pip show strategy-backtest-agent`, install using that same Python. Use underscore in the import. |
| `command not found: strategy-backtest` | Environment's bin directory not active | Reactivate the venv; inspect `which python` and `which strategy-backtest`. Use `.venv/bin/strategy-backtest` on POSIX if needed. |
| `OPENAI_API_KEY is missing; export it before using ai` | Empty/missing key, Python dotenv not opted in, or environment set after client construction | Configure before creating a client, or use `BacktestClient(dotenv_path=".env")`. Inspect presence only with doctor; never print the key. |
| `OPENAI_MODEL must not be empty` / AI unavailable invalid model | Empty or syntactically invalid configured model | Unset an accidental empty environment value or set the intended model; create a new client. Model access is not tested by doctor. |
| OpenAI authentication / rate limit / timeout messages | Invalid key, quota/billing, unavailable model or network | Check private account settings/connectivity. A sanitized rate-limit error cannot distinguish all billing/quota causes. Do not retry by exposing keys in logs. |
| `Request rejected` / unsupported crossover | Rule not in the supported DSL, ambiguity or missing fields | Use completed-candle state comparisons, one symbol, supported indicator parameters. Do not replace a crossover with a level rule unless you intend that different strategy. |
| `CLIBacktest` / `evaluation_period.requested_start` says string should be datetime after direct Python natural-language run | Known v1.2.0 direct DSL wrapper defect | Use `config = client.parse(request)` then `client.run(config=config, demo=True)`; preserve source metrics. A runtime fix is outside the documentation task. |
| `Invalid BacktestConfig configuration` / extra forbidden field | Wrong schema, e.g. `period_days` or nested `strategy` in root backtest | Put duration in `days=`/`--days`; use `AIStrategyConfig` with Python for DSL, or the matching research config. |
| `days conflicts with config period_days` | Two different durations on an AI config/request | Omit `days=` or make it match the validated config. |
| `--config cannot be combined with legacy strategy/account flags` | Root CLI has config and `--symbol`, `--fee`, etc. | Put those values in the config; keep only compatible duration/demo/JSON/cost flags. |
| `--demo requires --config` | Natural-language comparison/validation/Walk-Forward with demo flag | Create/validate config first. This restriction does not apply to root backtest and is not an option for sensitivity/costs. |
| `unrecognized arguments: --demo` | Sensitivity/costs CLI has no demo mode | Use Python `sensitivity(..., demo=True)` / `costs(..., demo=True)` for synthetic execution. |
| `Unable to fetch valid historical candles` / `Provider rate limit` | Binance network/region/rate limit or invalid/incomplete data | Check symbol/timeframe/range, connectivity and provider Retry-After. The provider does not automatically retry. Use supported synthetic workflow to diagnose local execution. |
| Insufficient warm-up/history or incomplete candles | Evaluation plus prior seed history unavailable | Request enough history and a complete interval; inspect initialization metadata. Do not silently shorten evaluation or change periods merely to force a result. |
| `walk-forward requires at least two complete folds` | History too short for window protocol | Increase `period_days`, or deliberately choose smaller Train/Test/step. Step must be at least Test; max_folds must allow the complete count. |
| `demo data ends at 2024-07-01T00:00:00Z` | Explicit end conflicts with synthetic end | Use that fixed aware UTC end or omit end in demo. Omit demo only if you intend provider access. |
| `output already exists` / `Could not safely create report output` | Existing file, directory, symlink/parent traversal, or permissions | Use a new filename in a writable physical directory; do not overwrite preserved research. On macOS use `/private/tmp` instead of `/tmp` for safe-writer destinations. |
| `Use the corresponding async client method inside an event loop` | Sync execution/parse called in notebook/async server | Await matching `a...` method. Do not nest `asyncio.run`. |
| `Unsupported/corrupted research schema` | Report given config/normalized JSON, incomplete/edited source, or unsupported metadata | Use untouched raw `--json` output or `result.to_json()`. Keep all negative/null values and metadata. Report help's historical `v0.9` wording does not mean current raw output is unsupported. |
| `ai_unavailable` / `ai_rejected` in report | Optional interpretation unavailable or failed grounding | Read deterministic evidence and warnings; fix account/config only if you intend another paid attempt. This is not a failed deterministic report. |

For secret-free diagnosis, collect the installed version (`importlib.metadata.version`),
command with keys removed, config schema name, sanitized error and `doctor` output.
Do not share `.env`, raw environment dumps, credential-bearing provider headers or
account data. Doctor checks presence/configuration and local readiness, not whether
OpenAI is valid/funded, a model is available, or Binance is reachable. It does not
repair files. See [AI failure behavior](AI.md#failures-and-boundaries).
