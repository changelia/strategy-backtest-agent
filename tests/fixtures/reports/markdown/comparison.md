# Historical Strategy Research Report

**Strategy Comparison**

Report status: deterministic

## Executive Summary

- For RSI 14 (Strategy), historical net return was positive; this is descriptive, not predictive evidence.
- For RSI 14 (Strategy), historical return was above net Buy &amp; Hold.
- For RSI 14 (Strategy), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For RSI 14 (Strategy), sampled historical equity experienced a drawdown.
- For RSI 14 (Strategy), historical net return was positive; this is descriptive, not predictive evidence.
- For RSI 14 (Strategy), historical return was above net Buy &amp; Hold.

All observations describe supplied historical evidence; no future performance or live position is recommended.

## Research Configuration

| Setting | Validated value (schema defaults applied) |
| --- | --- |
| Symbol | BTCUSDT |
| Timeframe | 1h |
| Period days | 4 |
| Initial balance | 1000.0 |
| Fee | 0.001 |
| Evaluation end | 2024-01-05T00:00:00Z |
| Sort by | total\_return |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | RSI 14 | RSI(14) &lt; 30 | RSI(14) &gt; 70 |

## Historical Data and Evaluation Period

- Source: synthetic offline versioned fixture
- Evaluation (UTC): 2024-01-01 00:00:00 to 2024-01-05 00:00:00
- Boundary interpretation: Source requested UTC evaluation range; scopes contain actual half-open completed-candle segments.

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
| R1 | RSI 14 (Strategy) | 2024-01-01 00:00:00 | 2024-01-05 00:00:00 |
| R2 | RSI 14 (Strategy) | 2024-01-01 00:00:00 | 2024-01-05 00:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Excess return | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 2264.3400 quote | 1264.3400 quote | 126.4340 % | 2.5864 % | 123.8476 pp | -5.8295 % |
| R2 | 1000.0000 quote | 2264.3400 quote | 1264.3400 quote | 126.4340 % | 2.5864 % | 123.8476 pp | -5.8295 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 3 | 3 | 0 | 100.0000 % | N/A (undefined) |
| R2 | 3 | 3 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 9.7128 quote | 4.8570 quote | 4.8570 quote | 2.0259 quote | 1.0130 quote | 1.0130 quote |
| R2 | 9.7128 quote | 4.8570 quote | 4.8570 quote | 2.0259 quote | 1.0130 quote | 1.0130 quote |

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

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-comparison/1; source schema version: not provided (unversioned)
- Input bytes SHA256: d0d0dde947f979bb980645e4165ab8b0b00b58e2117a7ac9b272eeefb9a3befc
- Canonical input SHA256: e5f9bbcec229daa460fe3d31374fefee22a44c1473409ffbc6c5f1808db7698f
- Normalized evidence SHA256: 1985557734459a3a800ac98b3b2314e7de9d65cfe6251d8d3a2f6839fbf2e3dc
- Source candle SHA256: ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad
- No wall-clock generation timestamp is added. AI interpretation is not guaranteed reproducible.

Source history/initialization metadata:

| Field | Supplied value |
| --- | --- |
| Source | synthetic offline versioned fixture |
| Evaluation start | 2024-01-01T00:00:00Z |
| Evaluation end | 2024-01-05T00:00:00Z |
| First candle open | 2024-01-01T00:00:00Z |
| Last candle open | 2024-01-04T23:00:00Z |
| Candle count | 96 |
| History candle count | 111 |
| Warmup candles | 15 |
| Required warmup candles | 15 |
| Warmup policy | shared prior closes: RSI=p+1; SMA=p; EMA=5\*p (finite first-close seed) |
| Indicators 1 / Type | indicator |
| Indicators 1 / Name | rsi |
| Indicators 1 / Period | 14 |
| Indicator initializations | None |
| Candles sha256 | ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad |
