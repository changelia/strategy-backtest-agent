# v0.9 mathematical and causality audit

Verdict: RELEASE READY under the documented finite-history initialization and
legacy compatibility conventions. No confirmed mathematical or financial defect
was found; production code did not require changes. The ATR filter is evaluated
and can reject trades. Identical BTCUSDT results at threshold 100 are explained
by a nonrestrictive filter on the RSI-eligible candles, not an ignored condition.

## Independent mathematical evidence

`tests/test_advanced_audit.py` adds 16 offline regression cases:

- MACD(12,26,9) on a ramp C[n]=100+n: independent exact rational EMA closed form
  E_p[n]=C[n]-(p-1)/2*(1-((p-1)/(p+1))^n). The signal oracle uses an exact
  geometrically weighted sum of available MACD values rather than pandas or the
  production recurrence. Fast/slow EMAs, line, signal and histogram are asserted
  numerically. Price EMA seeds are the first close; line begins at zero-based
  index 25, signal/histogram at 33. Signal seeds at MACD[25]. Warm-up is 350 prior
  candles for all three components.
- Bollinger(20,2): windows 1..20, then sliding windows including 100 and 7, checked
  using rational sums and sums of squares. First mean=10.5, population variance
  =33.25; upper/lower=mean +/- 2*sqrt(variance). The first available index is 19.
  Rolling windows include the current completed close. Warm-up is 20 prior candles.
- ATR(14): first 14 true ranges equal 2, followed by gap-up TR=12, gap-down TR=15
  and TR=4. Exact expected ATRs are 2, 19/7, 176/49, 1242/343. First local TR is
  high-low; subsequent TR is max(high-low, abs(high-previous close),
  abs(low-previous close)). ATR seeds with the first 14 TR mean at index 13 and
  applies Wilder alpha=1/14 thereafter. Warm-up is 280 prior candles.

These checks supplement earlier scalar-reference, flat-price, unavailable-history,
parameter-validation and malformed-OHLC tests. They verify the declared conventions;
implementations using different EMA seeds need not agree at finite boundaries.

## ATR filter is restrictive when appropriate

A deterministic 96-hour fixture has two down/up price cycles and 280 prior candles.
The closes are identical across volatility cases. RSI(14) produces two baseline
trades with signal indices 0/33 and 64/94, executed at opens 1/34 and 65/95.

| Synthetic high/low policy | Baseline trades | Filtered trades |
| --- | --- | --- |
| Narrow ranges, ATR < 100 | 2 | 0 |
| Wide ranges, ATR = 400 | 2 | 2 |
| Initially wide, then narrow | 2 | 1 |
| Constant TR and ATR exactly 100 | 2 | 0 |

For the mixed case, after candle 23 ATR follows the independent formula
ATR[i]=5+395*(13/14)^(i-23). It is below 100 when the second RSI opportunity occurs.
The strict `>` comparison rejects equality. RSI values stay unchanged when only
high/low change, while ATR and AND entry eligibility change. This demonstrates
that the filter cannot silently become a no-op.

Exact rational RSI gains/losses verify threshold transitions. With 1000 starting
cash, 1% fees, 20 bps full spread and 10 bps per-side slippage, first final cash
is 1000*(980*0.998*0.99)/(992*1.002*1.01). The second baseline roundtrip multiplies
this by (984*0.998*0.99)/(976*1.002*1.01). Tests assert final balances, fees,
spread/slippage and the common net benchmark independently. No signal executes
on its own candle.

## BTCUSDT observation

A separate manual diagnostic re-fetched the fixed `atr-test.json` window without
OpenAI: BTCUSDT 1h, [2026-07-18T09:00:00Z, 2026-10-16T09:00:00Z), 2160 evaluation
candles and 280 warm-up candles. SHA256 of all retrieved OHLCV/warm-up data:

`43069d8c312ed242be71a73150dc040dbb4c234a63b39684be7d61ced7db18f7`

- 66 RSI<30 candidate signal candles with a following execution candle.
- ATR blocked zero of these candidates; candidate minimum ATR=184.23779882437313.
- Minimum ATR at the signal candles preceding the 12 actual baseline entries:
  186.89415826771193.
- ATR across the whole evaluation ranged from 61.2208140008832 to
  1041.487772159172. Values below 100 occurred outside RSI entry candidates.
- Both strategies had 12 identical completed trades and identical full financial
  reports; net return was 11.861827576597594%.

This confirms nonrestrictiveness at 100 on the re-fetched window. The original
manual test did not archive raw candles, so this audit does not claim byte-level
identity with its earlier provider response. Network access is used only in the
manual diagnostic, never in automated tests. No thresholds were optimized or
recommended and local research configurations were not changed.

## Causality, integration and compatibility

Default-period prefix and future-OHLC mutation tests cover all seven components:
MACD line/signal/histogram, Bollinger upper/middle/lower, ATR. Earlier values and
signals match truncated independent calculations; missing prior history raises
an explicit error. Existing integration regressions additionally verify complete
parameter/version keys, dependency-local new-indicator seeds, additional strategies,
sensitivity variants and later folds, same-close/high-low cache invalidation,
Train/Test portfolio isolation and segment-local liquidation.

The full suite runs comparison, validation, parameter sensitivity, rolling/expanding
walk-forward, execution-cost scenarios, mocked SDK parsing and config-only CLI.
Fees, fill adjustments, net benchmark, zero-trade handling and existing RSI/SMA/EMA
financial regressions pass. MACD/Bollinger components share underlying calculations
only when all calculation parameters and initialization semantics match.

Compatibility exception: comparison/validation retain their old common seed for
RSI/SMA/EMA. Adding a longer *legacy* indicator can move that common seed; this is
not a guarantee of legacy set-independent initialization. Adding advanced warm-up
cannot move it. Sensitivity/walk-forward retain individual legacy and advanced
anchors. Differences between these policies are documented in ARCHITECTURE.md.

## Quality and limitations

1006 tests pass, including 16 new audit cases. Ruff check, format check and full
mypy pass. Confirmed numerical behavior is limited to the tested finite floating-
point inputs and documented models; it is not a formal proof for all numeric
magnitudes. MACD/ATR warm-up lengths are deterministic finite approximations,
not evidence that residual seed effects cannot alter near-threshold signals.
Constant illustrative execution costs, full fills, unlimited liquidity and sampled
open/close drawdown remain modeling assumptions. Historical filter results do not
establish robustness or future profitability.

Audit performed on feat/advanced-indicators. Package version remains 0.8.0;
no push, merge, version bump or tag was performed.
