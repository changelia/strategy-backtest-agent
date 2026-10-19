# Command-Line Reference

The installed executable is `strategy-backtest`. Run `strategy-backtest --help` or
`strategy-backtest COMMAND --help` for options from the installed version. Config files
are validated against strict Pydantic models. Most errors print a concise message to
stderr and exit with status 2; doctor uses the special status codes below.

## Root backtest

```text
strategy-backtest [--config FILE] [options]
```

Without `--config`, this runs the legacy RSI strategy. It fetches Binance history unless
`--demo` is supplied. `--config` accepts `BacktestConfig` JSON; `--days` remains the
evaluation duration. A config cannot be combined with the legacy strategy/account
flags.

| Option | Default / values | Meaning |
| --- | --- | --- |
| `--config FILE` | none | Validated backtest config JSON. |
| `--symbol SYMBOL` | `BTCUSDT` | Uppercase symbol, e.g. `ETHUSDT`. |
| `--timeframe VALUE` | `1h` | One of `1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d`. |
| `--days N` | `180` | Positive duration in calendar days. |
| `--balance AMOUNT` | `10000` | Positive starting quote-currency cash. |
| `--fee` / `--trading-fee FRACTION` | `0.001` | Per-side fee fraction; `0.001` is 0.1%; `0 <= fee < 1`. |
| `--rsi-period N` | `14` | Positive Wilder RSI period. |
| `--entry-rsi VALUE` | `30` | Buy when RSI is below this value, 0–100. |
| `--exit-rsi VALUE` | `70` | Exit when RSI is above this value, 0–100. |
| `--spread-bps VALUE` | `0` | Full modeled bid/ask spread in basis points. |
| `--slippage-bps VALUE` | `0` | Adverse slippage in basis points per side. |
| `--demo` | off | Use fixed synthetic candles ending at 2024-07-01 UTC; no data request. |
| `--json` | off | Print one raw JSON result; undefined metrics are `null`. |

Example: `strategy-backtest --symbol BTCUSDT --timeframe 1h --days 90 --demo`.
This runs the legacy RSI strategy. Configured DSL rules can be used with `--config`.

## `ai`

```text
strategy-backtest ai TEXT [--json] [--spread-bps BPS] [--slippage-bps BPS]
```

`TEXT` is one quoted natural-language backtest request. OpenAI parses it (paid API
request), then the command fetches Binance candles and executes the validated result.
There is no `--demo` flag; AI parsing does not become offline when synthetic execution
is requested elsewhere. `--json` prints `input`, `parsed_strategy`, and
`backtest_result`. Cost options use full spread bps and per-side slippage bps.

```bash
strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 90 days. Buy when RSI(14) < 30 and sell when RSI(14) > 70.' \
  --json
```

Unsupported rules, ambiguous requests, provider errors, or Binance errors exit 2 with
a sanitized error. See [AI Guide](AI.md).

## `init`

```text
strategy-backtest init --type {backtest,compare,validate,walk-forward} --output FILE
```

Writes a validated template without prompts, API credentials, or network access. It
requires a new destination and refuses existing files, directories, symlinks, and
unsafe paths. The backtest template is consumed by the root command; each other type
is consumed by the command with the same name. Sensitivity and costs templates are
not supported.

```bash
strategy-backtest init --type walk-forward --output walk-forward.json
strategy-backtest walk-forward --config walk-forward.json --demo --json
```

`init` errors exit 2. See `strategy-backtest init --help` for its explanatory epilog.

## `doctor`

```text
strategy-backtest doctor [--type {backtest,compare,validate,walk-forward} --config FILE]
```

Offline, read-only environment checks. `--type` and `--config` must be supplied
together. Config validation is supported only for those four types. Without them,
doctor does not discover or validate research files. Doctor performs no requests and
does not repair files.

- Exit 0: checked offline capabilities are available; AI remains optional.
- Exit 1: a required environment or explicitly supplied config needs attention.
- Exit 2: invalid arguments.

Key presence is not key validation; model configuration is not provider availability.

## `report`

```text
strategy-backtest report --input RESULT.json [--format {markdown,json}] [--output FILE] [--ai]
```

Validates an existing result for one of six research types and renders it without
fetching data or rerunning a backtest. Default format is Markdown; JSON contains the
normalized evidence and provenance. Output files are created without overwrite. With
`--ai`, the optional constrained interpretation may call OpenAI and may cost money;
deterministic reporting remains available if AI is missing or rejected. AI status
warnings go to stderr; the report remains the output. Errors exit 2.

```bash
set -C
strategy-backtest --demo --days 3 --json > result.json
strategy-backtest report --input result.json --format json --output report.json
strategy-backtest report --input result.json --format markdown --output report.md
```

## Shared research command pattern

`compare`, `validate`, `sensitivity`, and `walk-forward` accept either one quoted
natural-language request or `--config FILE`, but not both. A config file is validated
without OpenAI. Natural-language mode parses through OpenAI and may incur charges.
Each supports `--json` and `--spread-bps` / `--slippage-bps` overrides. An explicit
`--demo` requires `--config`, preventing accidental AI calls in an ostensibly offline
run. Demo candles are synthetic and end at 2024-07-01 UTC.

| Command | Additional options | Demo support | Data by default |
| --- | --- | --- | --- |
| `compare` | `--sort {total_return,excess_return,max_drawdown,profit_factor}`; default is config `sort_by` (`total_return`) | yes, config only | Binance |
| `validate` | none | yes, config only | Binance |
| `sensitivity` | none | no | Binance |
| `costs` | required `--config FILE`; optional `--json` | no | Binance |
| `walk-forward` | none | yes, config only | Binance |

`--spread-bps` is the full spread; `--slippage-bps` is per-side adverse slippage.
They are overrides to declared execution assumptions. For `costs`, costs live inside
the scenario definitions, and natural-language parsing is unsupported.

### Comparison

Compares 2–5 fixed strategies using the same market-data window and account settings.
Each strategy has a fresh independent portfolio. The optional sort criterion changes
the displayed/ranking criterion only.

```bash
strategy-backtest init --type compare --output comparison.json
strategy-backtest compare --config comparison.json --demo --sort max_drawdown --json
```

### Validation

Evaluates 1–5 fixed strategies on chronological Train then Test. `train_ratio` defaults
to 0.70 and is constrained to 0.50–0.90. The segments use separate cash and positions.

```bash
strategy-backtest init --type validate --output validation.json
strategy-backtest validate --config validation.json --demo --json
```

### Sensitivity

Evaluates a bounded parameter grid on Train only. CLI has no `--demo`; running it
fetches Binance data. Grid limits and paths are described in [Research Guide](RESEARCH_GUIDE.md).

```bash
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/sensitivity.json > sensitivity.json
strategy-backtest sensitivity --config sensitivity.json --json
```

### Cost scenarios

Config-only: no positional text, no `--demo`, and no shared spread/slippage flags.
Scenarios contain cost assumptions; first scenario must be zero-spread/zero-slippage
baseline. CLI fetches Binance data.

```bash
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/execution-scenarios.json > costs.json
strategy-backtest costs --config costs.json --json
```

### Walk-Forward

Evaluates 1–5 fixed strategies on rolling or expanding windows. Complete windows are
placed by candle counts; Test windows cannot overlap; at least two folds are required.
Train is diagnostic. Test portfolios reset each fold.

```bash
strategy-backtest init --type walk-forward --output walk-forward.json
strategy-backtest walk-forward --config walk-forward.json --demo --json
```

## Output and errors

Without `--json`, the command prints a human-readable summary. Research JSON is the raw
engine output; report JSON is a normalized evidence document. JSON is written to stdout
without progress output; send it to a new file with shell noclobber (`set -C`) or use a
safe `--output` report destination. Config and report files are never silently
overwritten. Most invalid configs, unsupported inputs, insufficient history, and
provider failures print an error to stderr and exit 2. See [Troubleshooting](TROUBLESHOOTING.md).
