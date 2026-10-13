# Strategy Backtest Agent

**Describe a trading strategy in plain English. Backtest it against real historical market data.**

Strategy Backtest Agent turns single-symbol, long-only trading rules into validated
strategies and tests them on Binance historical candles. OpenAI interprets your
request; Python calculates indicators, signals, trades, fees, and performance metrics.
Use the CLI to explore a strategy or export JSON for your own research tools.

Current functionality: **v0.3.0 — AI Strategy Parser, Strategy DSL, and Rule Engine.**

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

## Supported Strategies

- Wilder RSI, SMA, EMA, completed candle close (`price`), and finite numeric constants
- Level comparisons: `<`, `<=`, `>`, `>=`, including indicator-to-indicator comparisons
- AND/OR conditions and clearly specified nested groups
- One symbol, one long position at a time, full available cash allocation
- Next-candle-open execution, entry/exit fees, and final-close liquidation
- Return, buy-and-hold comparison, trade PnL, win rate, drawdown, and profit factor
- Paginated Binance historical data, terminal summaries, JSON, and an offline demo

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

Planned research capabilities, not available in v0.3.0:

- **Strategy comparison:** evaluate multiple strategies on the same data and assumptions.
- **Parameter sensitivity:** explore how results change across periods and thresholds.
- **Out-of-sample validation:** separate development data from held-out evaluation periods.
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
