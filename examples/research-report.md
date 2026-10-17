# Historical Strategy Research Report

**Standard Backtest**

Report status: deterministic

## Executive Summary

- For Single strategy (Strategy), historical net return was negative; this is descriptive, not predictive evidence.
- For Single strategy (Strategy), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For Single strategy (Strategy), sampled historical equity experienced a drawdown.

All observations describe supplied historical evidence; no future performance or live position is recommended.

## Research Configuration

| Setting | Validated value (schema defaults applied) |
| --- | --- |
| Symbol | BTCUSDT |
| Timeframe | 12h |
| Period days | 4 |
| Evaluation period | Not provided |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | Single strategy | PRICE &gt; 0 | PRICE &lt; 0 |

## Historical Data and Evaluation Period

- Source: synthetic offline fixture; prices are not historical BTCUSDT
- Evaluation (UTC): 2024-01-01 00:00:00 to 2024-01-05 00:00:00
- Boundary interpretation: Actual completed candles: CLI start/end are candle opens; normalized end = last open + timeframe.

## Execution Assumptions

Fee is a per-side fraction; spread is the full bid/ask spread in bps; slippage is adverse per side in bps.
OHLC prices are reference proxies. Reported spread/slippage costs are illustrative adjustments, not measured fills.
Signals execute at the following candle open; forced liquidation uses the segment's final close.

| Applies to | Fee per side | Full spread | Slippage per side |
| --- | --- | --- | --- |
| All segments | 0.01 fraction | 20 bps | 10 bps |

## Performance Results

Numbers are rounded for display; JSON evidence retains source precision, full identifiers, source paths and contexts. All segments, negative results and undefined metrics are shown. R references identify rows below; boundaries are UTC and use the source boundary policy.

### Research results

| Reference | Segment | Start UTC | End UTC |
| --- | --- | --- | --- |
| R1 | Single strategy (Strategy) | 2024-01-01 00:00:00 | 2024-01-05 00:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 976.2851 quote | -23.7149 quote | -2.3715 % | -2.3715 % | -75.0000 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 1 | 0 | 1 | 0.0000 % | 0 ratio |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 19.7625 quote | 1.9762 quote | 1.9762 quote | 19.7625 quote | 1.9762 quote | 1.9762 quote |

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
- Input bytes SHA256: d05916d663165b7fdb77c31554288c6fa09902db441e991da4aa9daa4175913b
- Canonical input SHA256: cc1f70b15f4ac4a3a2f31829807334c328f8c0474e60cc6b20acceb247f85edc
- Normalized evidence SHA256: b0ec00e3b994733db732a317d58eacb8bd46ebd8c631563eb672446d87b7cdab
- Source candle SHA256: Unavailable
- No wall-clock generation timestamp is added. AI interpretation is not guaranteed reproducible.

Source history/initialization metadata:

| Field | Supplied value |
| --- | --- |
| Indicator configuration | None |
| Indicator initializations | Not provided |
| Evaluation period | Not provided |
