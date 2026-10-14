# Strategy Backtest Agent

**Describe a trading strategy in plain English. Backtest it against real historical market data.**

Strategy Backtest Agent turns single-symbol, long-only trading rules into validated
strategies and tests them on Binance historical candles. OpenAI interprets your
request; Python calculates indicators, signals, trades, fees, and performance metrics.
Use the CLI to explore a strategy or export JSON for your own research tools.

Development milestone: **v0.5.0 — Out-of-Sample Validation** (unreleased).
Latest release tag and package version: **v0.4.0**.

## Quick Start

Requires Python 3.12+, Poetry 2.x, an OpenAI API key for AI mode, and network access
to OpenAI and Binance public market data.

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
export OPENAI_API_KEY="your_openai_api_key_here"

poetry run strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 90 days. Buy when RSI 14 < 30 and price > EMA 200. Sell when RSI 14 > 70 or price < EMA 50. Start with $10,000.'
```

The command displays the parsed strategy and backtest results. Review the parsed
rules: natural-language interpretation can be wrong even when validation succeeds.
AI requests send your text to OpenAI and incur API usage charges. `OPENAI_MODEL`
can override the configured model; it must support Responses and Structured Outputs.
Credentials come from environment variables. `.env` is ignored and is **not loaded
automatically**. Never include secrets in strategy requests.

Try the deterministic offline demo without credentials or network access:

```bash
poetry run strategy-backtest --demo --days 30
```

## Example Output

Actual output from the 30-day offline demo above. The prices are **synthetic**, not
historical BTCUSDT data; these results are not evidence of real-market performance.

```text
Strategy Backtest
────────────────────────────────
Symbol: BTCUSDT
Timeframe: 1h
Period: 30 days
Data: synthetic offline demo (720 candles)
Range (candle opens, UTC): 2024-06-01 00:00:00+00:00 → 2024-06-30 23:00:00+00:00

Strategy: RSI
RSI Period: 14
Entry RSI: < 30
Exit RSI: > 70
Fee per side: 0.1%

Results (quote currency)
Initial Balance: 10,000.00
Final Balance: 4,725.85
Total Return: -52.74%
Buy & Hold: +1.00%
Trades: 8
Winning Trades: 0
Losing Trades: 8
Win Rate: +0.00%
Max Drawdown: -52.87%
Profit Factor: 0.00
```

## Compare Strategies

Compare 2–5 strategies on the same symbol, timeframe, historical window, initial
balance, and fee. Each strategy runs its own independent portfolio.

```bash
poetry run strategy-backtest compare \
  'Compare RSI 25/70, RSI 30/70 and SMA 20/50 on BTCUSDT over 90 days'
```

Or use a validated JSON config without an OpenAI key (Binance access required):

```bash
poetry run strategy-backtest compare --config examples/comparison.json
poetry run strategy-backtest compare --config examples/comparison.json --json
poetry run strategy-backtest compare --config examples/comparison.json --sort max_drawdown
```

The [example config](examples/comparison.json) sets a fixed UTC end time. Data is
fetched once, and shared indicators are calculated once. All comparison strategies,
including legacy RSI configurations, use the same prior-history warm-up. This can
produce different results from single-strategy legacy RSI runs.

The table shows returns, excess return, drawdown, trades, win rate, and profit factor.
**Excess return** is strategy return minus buy-and-hold return, in percentage points.
Sort by `total_return` (default), `excess_return`, `max_drawdown`, or `profit_factor`.
Less negative drawdown ranks higher; undefined metrics rank last, with ties broken
by strategy ID. A null profit factor is not infinity. Rankings describe historical
results and do not predict which strategy will perform best in the future.

Comparison JSON contains `configuration`, `shared_data`, `buy_and_hold_return_percent`,
`results`, `ranking_criterion`, and ranked strategy IDs in `ranking`. It records the
resolved UTC window, warm-up policy, definitions, and a candle-history digest. A fixed
end makes the requested window repeatable; exact reproduction requires the same data.
Multi-symbol comparisons and per-strategy overrides of shared trading settings are rejected.

## Train/Test Validation

Validate 1–5 fixed strategies on chronological Train and Test segments:

```bash
poetry run strategy-backtest validate \
  'Validate RSI 30/70 and SMA 20/50 on BTCUSDT over 180 days using a 70/30 train/test split'
poetry run strategy-backtest validate --config examples/validation.json
poetry run strategy-backtest validate --config examples/validation.json --json
```

Config mode needs no OpenAI credentials. The [example](examples/validation.json)
sets a fixed UTC end. One shared fetch includes the maximum indicator warm-up.
Train receives the first `floor(completed evaluation candles × train_ratio)` candles;
Test receives all remaining candles. Default ratio is 0.70, allowed range 0.50–0.90.
Each segment needs at least two candles; insufficient history is rejected.

Each segment starts flat with its own initial cash. Prior candles initialize causal
indicators only. The first signal uses the first completed segment candle and executes
at the next segment open. Final-candle signals never cross the split; open positions
liquidate at their own segment's final close. No trades or equity carry into Test.
Exact UTC boundaries, candle counts, warm-up and a full-history SHA256 are recorded.

**Test is Held-out evaluation.** Select and freeze strategies before examining Test;
repeated inspection or choosing strategies using Test contaminates the holdout.
The return gap is `Test return − Train return`, in percentage points. It is descriptive:
durations differ and total returns are not normalized. No winner or robustness score
is assigned. A single holdout cannot establish robustness or future profitability.
Parameter optimization is unsupported; walk-forward validation is future work.

JSON contains `configuration`, `shared_data`, `split`, per-strategy `results` with
independent Train/Test metrics and trades, `return_gap_pp`, and `methodology_warnings`.
Undefined metrics are `null`; JSON stdout contains no progress messages.
Fixed boundaries make the window repeatable; exact replay requires unchanged candles,
including warm-up. See [ARCHITECTURE.md](ARCHITECTURE.md#chronological-out-of-sample-validation)
for boundary policy and initialization limitations.

## Supported Strategies

- Wilder RSI, SMA, EMA, completed candle close (`price`), and finite numeric constants
- Level comparisons: `<`, `<=`, `>`, `>=`, including indicator-to-indicator comparisons
- AND/OR conditions and clearly specified nested groups
- One symbol, one long position at a time, full available cash allocation
- Next-candle-open execution, entry/exit fees, and final-close liquidation
- Return, buy-and-hold comparison, trade PnL, win rate, drawdown, and profit factor
- Paginated Binance historical data, terminal summaries, JSON, and an offline demo
- Single-symbol strategy comparisons and chronological Train/Test validation

DSL periods: RSI 2–500; SMA/EMA 2–1000. Rules are limited to 20 comparisons and depth 5.
RSI defaults to period 14 when omitted; specify SMA/EMA periods. Use an explicit
market symbol such as `BTCUSDT`. AI mode defaults to 1h, 30 days, $10,000 initial
cash, and a 0.1% fee per side. Simple RSI requests default to buy below 30 and sell
above 70. The explicit-options CLI retains its 180-day default.

A moving-average level strategy:

```bash
poetry run strategy-backtest ai \
  'Backtest ETHUSDT on 4h for 90 days. Buy when SMA 20 > SMA 50. Sell when SMA 20 < SMA 50.'
```

`SMA 20 > SMA 50` is supported. `SMA 20 crosses above SMA 50` is a transition event
and is rejected. MACD, Bollinger Bands, NOT, stop loss/take profit, short selling,
leverage, multiple symbols, live trading, and predictions are unsupported.

## AI Parsing and Deterministic Execution

```text
Plain English → OpenAI parser → Validated Strategy DSL
                                      ↓
Historical candles → Cached indicators → Rule Engine → Backtester → Results
```

AI extracts configuration only. It does not calculate prices, indicators, trading
signals, or financial results. Python validates the DSL and executes fixed rules;
no AI-generated code or arbitrary expressions are executed. Given the same validated
strategy and candles, the financial results are deterministic.

Rules use completed candle N and execute at **candle N+1 open**. Open positions
check exit rules; flat portfolios check entry rules. Unavailable indicator operands
make a comparison false. A final-candle signal cannot execute; any remaining
position is liquidated at the final close.

Rule strategies fetch prior candles for indicator warm-up: RSI `p+1`, SMA `p`, and
EMA `5p`, using the largest requirement. Warm-up candles are excluded from trading,
equity, and buy-and-hold results. Incomplete history or gaps cause an error rather
than a shortened evaluation period. EMA uses a finite approximation to historical
initialization; its seed can still affect signals near thresholds. Legacy RSI CLI,
demo, and simple AI RSI requests retain their original in-range initialization.
All boundaries use UTC and exclude unfinished candles.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the DSL schema, validation limits,
indicator initialization, execution accounting, metric definitions, and parser defaults.

## CLI and JSON

Run an RSI backtest with explicit options and no OpenAI key (Binance access required):

```bash
poetry run strategy-backtest \
  --symbol BTCUSDT --timeframe 1h --days 30 --balance 10000
```

Export an AI-parsed rule strategy:

```bash
poetry run strategy-backtest ai \
  'Backtest BTCUSDT. Buy when RSI < 30 and price > EMA 200. Sell when RSI > 70.' \
  --json > backtest.json
```

AI JSON includes `input`, `parsed_strategy`, and `backtest_result`, with metrics,
trades, indicator configuration, and evaluation-period metadata for rule strategies.
Explicit CLI JSON contains results and configuration directly. JSON stdout contains
no progress messages; errors go to stderr with exit code 2. Undefined metrics are
`null`. Credentials, prompts, and raw OpenAI responses are excluded.

For all CLI options and a network-free JSON example:

```bash
poetry run strategy-backtest --help
poetry run strategy-backtest ai --help
poetry run strategy-backtest --demo --days 30 --json
```

## Limitations

Backtests assume full fills, fractional quantities, and unlimited liquidity. They
exclude slippage, spreads, funding, taxes, and exchange lot-size constraints.
Drawdown samples candle opens and closes, not intrabar highs and lows. Binance data
availability depends on history, network access, rate limits, and regional restrictions.
Legacy/direct candle runs can span missing intervals; the rule-history fetch rejects gaps.
The application does not place orders or connect to private trading endpoints.

## Roadmap: Strategy Research Agent

Strategy comparison and chronological holdout validation are implemented. Planned next
research capabilities:

- **Parameter sensitivity:** explore how results change across periods and thresholds.
- **Walk-forward validation:** evaluate strategies across multiple chronological windows.
- **Research reports:** summarize configurations, evidence, risks, and limitations in reproducible reports.

## Development

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

Tests use mocked provider and OpenAI responses and require no API keys or network.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance.

## Financial Disclaimer

This is educational/research software, not financial advice. Historical backtests do
not predict future profitability. Natural-language parsing does not make this a
trading recommendation system. Do not use simulated results as the sole basis for
investment decisions.

## License

[MIT](LICENSE).
