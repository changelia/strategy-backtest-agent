# Historical Strategy Research Report

**Standard Backtest**

Report status: deterministic

## Executive Summary

- For Single strategy (Strategy), historical net return was positive; this is descriptive, not predictive evidence.
- For Single strategy (Strategy), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For Single strategy (Strategy), sampled historical equity experienced a drawdown.

All observations describe supplied historical evidence; no future performance or live position is recommended.

## Research Configuration

| Setting | Validated value (schema defaults applied) |
| --- | --- |
| Symbol | BTCUSDT |
| Timeframe | 1h |
| Period days | 4 |
| Evaluation period | Not provided |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | Single strategy | RSI(14) &lt; 30 | RSI(14) &gt; 70 |

## Historical Data and Evaluation Period

- Source: synthetic offline versioned fixture
- Evaluation (UTC): 2024-01-01 00:00:00 to 2024-01-05 00:00:00
- Boundary interpretation: Actual completed candles: CLI start/end are candle opens; normalized end = last open + timeframe.

## Execution Assumptions

Fee is a per-side fraction; spread is the full bid/ask spread in bps; slippage is adverse per side in bps.
OHLC prices are reference proxies. Reported spread/slippage costs are illustrative adjustments, not measured fills.
Signals execute at the following candle open; forced liquidation uses the segment's final close.

| Applies to | Fee per side | Full spread | Slippage per side |
| --- | --- | --- | --- |
| All segments | 0.001 fraction | 10 bps | 5 bps |

## Performance Results

Numbers are rounded for display; JSON evidence retains source precision, full identifiers, source paths and contexts. All segments, negative results and undefined metrics are shown. R references identify rows below; boundaries are UTC and use the source boundary policy.

### Research results

| Reference | Segment | Start UTC | End UTC |
| --- | --- | --- | --- |
| R1 | Single strategy (Strategy) | 2024-01-01 00:00:00 | 2024-01-05 00:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 2264.3400 quote | 1264.3400 quote | 126.4340 % | 2.5864 % | -5.8295 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 3 | 3 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 9.7128 quote | 4.8570 quote | 4.8570 quote | 2.0259 quote | 1.0130 quote | 1.0130 quote |

## Methodology

- Only the supplied single research result is analyzed; no market-data fetch or backtest execution.
- Numbers are copied from validated results; derived net PnL is final minus initial balance.
- Benchmark is net first evaluation open to final close under the same execution assumptions.
- Undefined metrics remain null; no pooled win rate/profit factor or continuous OOS drawdown is invented.

## Limitations

- Historical results do not predict returns, establish safety, statistical significance or robustness.
- Structural and consistency validation does not authenticate data or results. A supplied candle hash is source metadata, not proof of truthful research.
- Spread/slippage are modeled assumptions; full fills and unlimited liquidity are assumed. Drawdown samples opens/closes.
- Consistency checks cannot verify prices, indicators, signal correctness or drawdown paths without original candles/equity. No backtest is rerun.

Report warnings:

- Input has no candle SHA256; candle provenance is unavailable, not inferred.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-backtest/1; source schema version: not provided (unversioned)
- Input bytes SHA256: 6605b8ac02ecd6fc7b14c8d92c5e2d5a1b58e234520564ecc25214f87ddf6c68
- Canonical input SHA256: cd5616045573dd504cae2b02427b662789f79f7a38c0a11613af143ecf9ad34b
- Normalized evidence SHA256: 098e5e87d1911abd2aac94fc78ec9806c762acfd9620d4c1e4ac73e531206c49
- Source candle SHA256: Unavailable
- No wall-clock generation timestamp is added. AI interpretation is not guaranteed reproducible.

Source history/initialization metadata:

| Field | Supplied value |
| --- | --- |
| Indicator configuration 1 / Type | indicator |
| Indicator configuration 1 / Name | rsi |
| Indicator configuration 1 / Period | 14 |
| Indicator initializations | Not provided |
| Evaluation period | Not provided |
