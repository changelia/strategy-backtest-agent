# Historical Strategy Research Report

**Execution Cost Scenarios (Train only)**

Report status: deterministic

## Executive Summary

- For base (Scenario Train), historical net return was equal to the declared baseline under these execution assumptions.
- For costs (Scenario Train), historical net return was lower than the declared baseline under these execution assumptions.
- For base (Scenario Train), historical net return was positive; this is descriptive, not predictive evidence.
- For base (Scenario Train), historical return was above net Buy &amp; Hold.
- For base (Scenario Train), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For base (Scenario Train), sampled historical equity experienced a drawdown.

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
| Train ratio | 0.7 |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | base, costs | RSI(14) &lt; 30 | RSI(14) &gt; 70 |

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
| R1 | 0.001 fraction | 0 bps | 0 bps |
| R2 | 0.001 fraction | 10 bps | 5 bps |

## Performance Results

Numbers are rounded for display; JSON evidence retains source precision, full identifiers, source paths and contexts. All segments, negative results and undefined metrics are shown. R references identify rows below; boundaries are UTC and use the source boundary policy.

### Research results

| Reference | Segment | Start UTC | End UTC |
| --- | --- | --- | --- |
| R1 | base (Scenario Train) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |
| R2 | costs (Scenario Train) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Excess return | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 1822.7776 quote | 822.7776 quote | 82.2778 % | 11.6180 % | 70.6597 pp | -5.7353 % |
| R2 | 1000.0000 quote | 1815.5010 quote | 815.5010 quote | 81.5501 % | 11.3950 % | 70.1551 pp | -5.8295 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 2 | 2 | 0 | 100.0000 % | N/A (undefined) |
| R2 | 2 | 2 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 5.5490 quote | 0.0000 quote | 0.0000 quote | 2.1163 quote | 0.0000 quote | 0.0000 quote |
| R2 | 5.5362 quote | 2.7685 quote | 2.7685 quote | 2.1141 quote | 1.0571 quote | 1.0571 quote |

#### Aggregate and additional metrics

| Segment | Metric | Value |
| --- | --- | --- |
| R1 | Return difference | 0.0000 pp |
| R2 | Return difference | -0.7277 pp |

## Cost Sensitivity

Train only. Test is reserved and not evaluated. These descriptive results neither select an optimal strategy nor establish independent OOS validation.

## Methodology

- Only the supplied single research result is analyzed; no market-data fetch or backtest execution.
- Numbers are copied from validated results; derived net PnL is final minus initial balance.
- Benchmark is net first evaluation open to final close under the same execution assumptions.
- Undefined metrics remain null; no pooled win rate/profit factor or continuous OOS drawdown is invented.
- Train only; no Test results are present.

## Limitations

- Historical results do not predict returns, establish safety, statistical significance or robustness.
- Structural and consistency validation does not authenticate data or results. A supplied candle hash is source metadata, not proof of truthful research.
- Spread/slippage are modeled assumptions; full fills and unlimited liquidity are assumed. Drawdown samples opens/closes.
- Consistency checks cannot verify prices, indicators, signal correctness or drawdown paths without original candles/equity. No backtest is rerun.
- Train-only research. Test is reserved and not evaluated by this workflow; no independent OOS claim is supported.

Source-provided notes (unverified wording, treated as data):

- Execution-cost scenarios are in-sample Train research on one frozen strategy. Test is reserved, not evaluated. No strategy or cost parameters are optimized or recommended.
- Scenario costs are illustrative assumptions, not measured Binance spreads or slippage. Fees inherit the shared rate unless a scenario explicitly supplies fee\_rate.
- OHLC prices are mid-price proxies; historical Binance candles do not provide bid/ask quotes.
- Spread and slippage are illustrative modeled adjustments, not separately observed historical costs.
- Open positions are marked at reference prices; costs apply only on actual fills. Full fills, fractional quantities and unlimited liquidity are assumed; no impact or partial fills.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-costs/1; source schema version: not provided (unversioned)
- Input bytes SHA256: 854d36412ab898531f28aaa1a9bd001f75f8145ca8bfad67c0f861a8d6b97a5b
- Canonical input SHA256: 516b86d4e03adf777e3b10d998aacc8a24424fc175214928017d150f1ae84804
- Normalized evidence SHA256: 6029726069a139176b92b4468df99bb2dc1ef136b1533dd381a720d344612bc7
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
| Warmup policy | indicator-local prior closes anchored at first Train open: RSI=p+1; SMA=p; EMA=5\*p; MACD=10\*(slow+signal); Bollinger=p (population std); ATR=20\*p; finite indicator-local seeds independent of other grid periods |
| Indicators 1 / Type | indicator |
| Indicators 1 / Name | rsi |
| Indicators 1 / Period | 14 |
| Indicator initializations 1 / Indicator / Type | indicator |
| Indicator initializations 1 / Indicator / Name | rsi |
| Indicator initializations 1 / Indicator / Period | 14 |
| Indicator initializations 1 / Prior candle count | 15 |
| Indicator initializations 1 / History start | 2023-12-31T09:00:00Z |
| Indicator initializations 1 / Input fields | close |
| Indicator initializations 1 / Seed policy | legacy: RSI SMA/Wilder; SMA rolling; EMA first-close; configured history anchor |
| Candles sha256 | ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad |
