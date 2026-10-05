# Strategy Backtest Agent

## Overview

Strategy Backtest Agent is an early-stage open-source Python project for
backtesting rule-based trading strategies against historical market data.

Version 0.1.0 is a deterministic, long-only RSI MVP. The AI strategy parser is
planned but **not implemented**. No API keys or environment variables are required.

## Features

- Paginated, credential-free Binance historical OHLCV data
- Wilder RSI, SMA, and EMA calculated locally
- Configurable RSI strategy with next-candle-open execution
- Entry and exit fees, equity drawdown, and buy-and-hold comparison
- Terminal and machine-readable JSON results
- Deterministic offline demo and network-free unit tests

## Architecture

```text
Market Data
    ↓
Indicators
    ↓
Strategy
    ↓
Backtest Engine
    ↓
Metrics
    ↓
CLI / JSON
```

Modules under `src/strategy_backtest_agent/` correspond to these stages:
`market_data.py`, `indicators.py`, `strategy.py`, `backtester.py`, `metrics.py`,
`cli.py`. `models.py` validates inputs/results; `demo.py` generates synthetic candles.
The engine accepts candles directly and has no HTTP dependency. Only RSI is currently
an executable strategy; SMA and EMA are available as indicators.

**FUTURE WORK — not implemented:**

```text
Natural Language
    ↓
AI Strategy Parser
    ↓
Validated Strategy Config
    ↓
Backtest Engine
```

## Installation

Requires Python 3.12+ and Poetry 2.x (verified with Poetry 2.1.4).

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
poetry run strategy-backtest --help
```

## Quick Start

```bash
poetry run strategy-backtest --symbol BTCUSDT --timeframe 1h --days 180 --balance 10000
```

Public market data requires internet access and provider availability in your region.
Requests use a 20-second HTTP timeout, sequential pagination of up to 1,000 candles,
and a 0.2-second pause between pages. HTTP failures, malformed data, and insufficient
completed history produce readable errors and exit code 2. Rate-limit responses stop
the run without retries and report the provider's Retry-After header when available.
No private API credentials or trading endpoints are used.

## Offline Demo

```bash
poetry run strategy-backtest --demo
poetry run strategy-backtest --demo --days 30 --json
```

The demo generates a small synthetic price series in memory and executes the same
strategy, engine, and metrics as live historical runs. Results are calculated, never
hardcoded. The default produces 4,320 hourly candles ending at the fixed boundary
2024-07-01 00:00 UTC. Symbol is a label in demo mode; synthetic data is not BTC history.
Timeframe and days control candle count; requests above 300,000 demo candles are rejected.

## CLI Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--symbol` | BTCUSDT | Uppercase alphanumeric provider symbol |
| `--timeframe` | 1h | 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d |
| `--days` | 180 | Positive number of preceding calendar days |
| `--balance` | 10000 | Positive starting cash in the quote currency |
| `--entry-rsi` | 30 | Buy when RSI is strictly below this threshold |
| `--exit-rsi` | 70 | Sell when RSI is strictly above this threshold |
| `--rsi-period` | 14 | Positive Wilder smoothing period |
| `--fee` | 0.001 | Fraction charged on each side: 0.001 means 0.1% |
| `--json` | off | Print JSON only; undefined metrics become null |
| `--demo` | off | Use deterministic synthetic candles without HTTP |
| `--help` | | Explain every option |

`--trading-fee` remains an alias for `--fee`. RSI thresholds must be between 0 and
100 with entry below exit. Fee must be at least zero and below one. Nonfinite inputs
are rejected. A syntactically valid symbol may still be unsupported by the provider.

```bash
poetry run strategy-backtest --symbol BTCUSDT --timeframe 1h --days 30 --json
```

JSON contains symbol, timeframe, period_days, strategy settings, all summary metrics,
and detailed trades with ISO timestamps. Additional metadata identifies the source,
candle count, and first/last candle open timestamps. All internal candle/trade timestamps are normalized to UTC; JSON timestamps use
ISO-8601 `Z` consistently. Errors go to stderr, not JSON stdout.

## Example Output

Illustrative output structure (placeholders below are not performance claims):

```text
Strategy Backtest
────────────────────────────────
Symbol: BTCUSDT
Timeframe: 1h
Period: 180 days
Data: <source and actual candle count>
Range (candle opens, UTC): <first> → <last>

Strategy: RSI
RSI Period: 14
Entry RSI: < 30
Exit RSI: > 70
Fee per side: 0.1%

Results (quote currency)
Initial Balance: 10,000.00
Final Balance: <calculated>
Total Return: <calculated>%
Buy & Hold: <calculated>%
Trades: <calculated>
Winning Trades: <calculated>
Losing Trades: <calculated>
Win Rate: <calculated>%
Max Drawdown: <calculated>%
Profit Factor: <calculated or N/A>
```

## How Backtesting Works

For live runs the end is the current UTC time, and the start is exactly `--days`
calendar days earlier. Only candles whose open is in `[start, end)` and whose close
time precedes end are included. The current unfinished candle is excluded. Interval
alignment can make coverage slightly shorter than the requested days. For example,
a 30-day hourly request at 12:30 excludes the first partial hour (its open precedes
start) and the current unfinished hour, leaving 719 completed candles. At an exact
hour boundary, 720 may be returned. No valid fully contained hour is dropped. Pagination
continues beyond the provider's per-request maximum. Missing intervals are not filled.
No extra pre-range warm-up history is requested.

Wilder RSI uses the first period's average gains/losses as its seed; its first value
requires period + 1 candles. Flat windows give 50, only gains 100, only losses 0.
After the initial simple averages, each Wilder average is updated as
`(previous_average * (period - 1) + current_gain_or_loss) / period`;
RSI is `100 - 100 / (1 + average_gain / average_loss)`.
SMA requires period observations; EMA uses a first-value seed and hides the first
period - 1 outputs. Indicator inputs must be finite.

A signal using completed candle N executes at **candle N+1 open**, for both entry and
exit. Equality at thresholds means hold. A final-candle signal cannot execute.
One position uses all available cash, ignoring further buys while held and sells while
flat. Any remaining position is deliberately liquidated at the final close; this is a
simulation boundary, not an RSI signal. Trade timestamps identify candle opens, even
for the final liquidation; they are not exact intrabar fill times.

Entry quantity is `cash / (entry_price * (1 + fee))`. Exit proceeds are
`quantity * exit_price * (1 - fee)`. Net trade PnL subtracts the complete entry cost,
including entry fee. Initial balance plus all net trade PnLs equals final balance.

## Metrics

| Metric | Definition |
| --- | --- |
| Total return | `(final balance / initial balance - 1) * 100` |
| Buy & hold | Buy at first supplied candle open, hold to last close; includes both fees |
| Win rate | Positive net-PnL trades / all completed trades, as a percentage |
| Max drawdown | Largest peak-to-trough equity decline, as a nonpositive percentage |
| Profit factor | Sum of positive net PnL / absolute sum of negative net PnL |

Equity starts at initial cash and samples every candle open and close using
`cash + quantity * price`. Fees reduce equity when executed; hypothetical exit fees
are not deducted from open positions. Drawdown includes unrealized losses, but does
not sample intrabar highs/lows. The benchmark includes the RSI warm-up period, so it
measures passive exposure across the whole supplied range.

Break-even trades count as neither winners nor losers, but count in win rate's
denominator. Thus winners + losers can be less than total trades by the number of
exactly zero-PnL trades; zero is compared exactly, without rounding to displayed cents.
Financial arithmetic uses floats; reconciliation tests allow small rounding error.
No trades gives null win rate and profit factor. No losing trades gives
null profit factor; losses without wins give zero. The engine accepts empty history
with unchanged cash and null benchmark; the CLI rejects insufficient RSI history.

## Testing

```bash
poetry run pytest
```

All tests are deterministic and offline. Mocked HTTP tests cover pagination beyond
1,000 candles, incomplete candles, malformed/empty responses, timeouts and rate limits.
Engine tests cover indicators, signals, next-open execution, no look-ahead, both fees,
PnL reconciliation, forced closing, drawdown, benchmark, and metric edge cases.
CLI tests cover validation, JSON and the offline demo. Live runs are manual checks;
CI never depends on an exchange being online.

## Code Quality

```bash
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src
```

CI runs install, Ruff, formatting, strict mypy (including tests), and pytest on push
and pull_request with cached dependencies and no secrets. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- [x] Historical market data
- [x] RSI
- [x] SMA
- [x] EMA
- [x] Backtest engine
- [x] Trading fees
- [x] Performance metrics
- [x] CLI
- [x] JSON output
- [x] Tests
- [ ] Natural-language strategies
- [ ] AI strategy parser
- [ ] Multiple strategy conditions
- [ ] MACD
- [ ] Bollinger Bands
- [ ] Stop Loss / Take Profit
- [ ] Strategy comparison
- [ ] Parameter optimization
- [ ] Charts
- [ ] Additional data providers
- [ ] AI result analysis

## Limitations

- Long-only, one position at a time, full cash allocation
- Simplified full-fill execution with fractional quantities and unlimited liquidity
- No slippage, spread, leverage, funding, tax, or exchange lot-size model
- No frontend, database, live trading, or order execution
- Missing intervals use the next supplied candle; gaps may affect results
- Availability/history depend on Binance, network access, and regional restrictions
- Synthetic demo data is illustrative and not historical performance
- Historical results do not predict future performance

## Disclaimer

This is educational/research software, not financial advice. Do not use simulated
results as the sole basis for investment decisions.

## License

[MIT](LICENSE).
