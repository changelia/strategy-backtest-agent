# Historical Strategy Research Report

**Standard Backtest**

Report status: deterministic

## Executive Summary

- strategy.single&#58; historical net return was negative&#59; this is descriptive, not predictive evidence. Evidence: strategy.single.total&#95;return
- strategy.single&#58; fewer than five completed trades&#59; limited trade evidence is not proof of stability. Evidence: strategy.single.completed&#95;trades
- strategy.single&#58; sampled historical equity experienced a drawdown. Evidence: strategy.single.max&#95;drawdown

All observations describe supplied historical evidence; no future performance or live position is recommended.

## Research Configuration

| Setting | Validated value (schema defaults applied) |
| --- | --- |
| symbol | &#34;BTCUSDT&#34; |
| timeframe | &#34;12h&#34; |
| period&#95;days | 4 |
| strategy | &#123;&#34;entry&#34;&#58; &#123;&#34;left&#34;&#58; &#123;&#34;type&#34;&#58; &#34;price&#34;&#125;, &#34;operator&#34;&#58; &#34;&#62;&#34;, &#34;right&#34;&#58; &#123;&#34;type&#34;&#58; &#34;value&#34;, &#34;value&#34;&#58; 0.0&#125;, &#34;type&#34;&#58; &#34;comparison&#34;&#125;, &#34;exit&#34;&#58; &#123;&#34;left&#34;&#58; &#123;&#34;type&#34;&#58; &#34;price&#34;&#125;, &#34;operator&#34;&#58; &#34;&#60;&#34;, &#34;right&#34;&#58; &#123;&#34;type&#34;&#58; &#34;value&#34;, &#34;value&#34;&#58; 0.0&#125;, &#34;type&#34;&#58; &#34;comparison&#34;&#125;, &#34;type&#34;&#58; &#34;rules&#34;&#125; |
| evaluation&#95;period | null |

## Strategies and Rules

| Scope | Label | Validated definition |
| --- | --- | --- |
| strategy.single | Single strategy | &#123;&#34;entry&#34;&#58; &#123;&#34;left&#34;&#58; &#123;&#34;type&#34;&#58; &#34;price&#34;&#125;, &#34;operator&#34;&#58; &#34;&#62;&#34;, &#34;right&#34;&#58; &#123;&#34;type&#34;&#58; &#34;value&#34;, &#34;value&#34;&#58; 0.0&#125;, &#34;type&#34;&#58; &#34;comparison&#34;&#125;, &#34;exit&#34;&#58; &#123;&#34;left&#34;&#58; &#123;&#34;type&#34;&#58; &#34;price&#34;&#125;, &#34;operator&#34;&#58; &#34;&#60;&#34;, &#34;right&#34;&#58; &#123;&#34;type&#34;&#58; &#34;value&#34;, &#34;value&#34;&#58; 0.0&#125;, &#34;type&#34;&#58; &#34;comparison&#34;&#125;, &#34;type&#34;&#58; &#34;rules&#34;&#125; |

## Historical Data and Evaluation Period

- Source: synthetic offline fixture&#59; prices are not historical BTCUSDT
- Evaluation: 2024-01-01 00&#58;00&#58;00&#43;00&#58;00 to 2024-01-05 00&#58;00&#58;00&#43;00&#58;00
- Boundary interpretation: Actual completed candles&#58; CLI start/end are candle opens&#59; normalized end &#61; last open &#43; timeframe.

## Execution Assumptions

Fee is a per-side fraction; spread is the full bid/ask spread in bps; slippage is adverse per side in bps.
OHLC prices are reference proxies. Reported spread/slippage costs are illustrative adjustments, not measured fills.

| Scope | Fee per side | Full spread | Slippage per side |
| --- | --- | --- | --- |
| strategy.single | 0.01 fraction | 20 bps | 10 bps |

## Performance Results

Numbers are rounded for display; JSON evidence retains source precision. All scopes and negative results are shown.

| Scope | Role | Start UTC | End UTC |
| --- | --- | --- | --- |
| strategy.single | strategy | 2024-01-01 00&#58;00&#58;00&#43;00&#58;00 | 2024-01-05 00&#58;00&#58;00&#43;00&#58;00 |

## Financial Metrics

| Evidence ID | Value / unit | Source path | Context |
| --- | --- | --- | --- |
| strategy.single.initial&#95;balance | 1000.0000 quote_currency | /initial&#95;balance | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.final&#95;balance | 976.2851 quote_currency | /final&#95;balance | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.total&#95;return | -2.3715 % | /total&#95;return&#95;percent | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.completed&#95;trades | 1 count | /total&#95;trades | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.winning&#95;trades | 0 count | /winning&#95;trades | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.losing&#95;trades | 1 count | /losing&#95;trades | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.win&#95;rate | 0.0000 % | /win&#95;rate | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.profit&#95;factor | 0 ratio | /profit&#95;factor | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.net&#95;pnl | -23.7149 quote_currency | /final&#95;balance | Derived final&#95;balance minus initial&#95;balance&#59; verified against supplied trade PnL. |
| strategy.single.fees | 19.7625 quote_currency | /costs/fees | Fees charged or illustrative fill adjustments&#59; not observed market costs. |
| strategy.single.modeled&#95;spread&#95;cost | 1.9762 quote_currency | /costs/modeled&#95;spread&#95;cost | Fees charged or illustrative fill adjustments&#59; not observed market costs. |
| strategy.single.modeled&#95;slippage&#95;cost | 1.9762 quote_currency | /costs/modeled&#95;slippage&#95;cost | Fees charged or illustrative fill adjustments&#59; not observed market costs. |
| strategy.single.fee&#95;per&#95;side | 0.01 fraction | /execution/fee&#95;rate | Declared execution assumption. |
| strategy.single.full&#95;spread | 20 bps | /execution/spread&#95;bps | Declared execution assumption. |
| strategy.single.slippage&#95;per&#95;side | 10 bps | /execution/slippage&#95;bps | Declared execution assumption. |

## Benchmark Comparison

| Evidence ID | Value / unit | Source path | Context |
| --- | --- | --- | --- |
| strategy.single.net&#95;buy&#95;and&#95;hold | -2.3715 % | /buy&#95;and&#95;hold&#95;return&#95;percent | Supplied historical segment metric&#59; independent full-cash portfolio. |
| strategy.single.benchmark&#95;fees | 19.7625 quote_currency | /benchmark&#95;costs/fees | Benchmark attribution under the same declared execution model. |
| strategy.single.benchmark&#95;modeled&#95;spread&#95;cost | 1.9762 quote_currency | /benchmark&#95;costs/modeled&#95;spread&#95;cost | Benchmark attribution under the same declared execution model. |
| strategy.single.benchmark&#95;modeled&#95;slippage&#95;cost | 1.9762 quote_currency | /benchmark&#95;costs/modeled&#95;slippage&#95;cost | Benchmark attribution under the same declared execution model. |

## Drawdown and Risk Observations

| Evidence ID | Value / unit | Source path | Context |
| --- | --- | --- | --- |
| strategy.single.max&#95;drawdown | -75.0000 % | /max&#95;drawdown&#95;percent | Supplied historical segment metric&#59; independent full-cash portfolio. |

## Deterministic Observations

- observation.0001: strategy.single&#58; historical net return was negative&#59; this is descriptive, not predictive evidence. Evidence: strategy.single.total&#95;return
- observation.0002: strategy.single&#58; fewer than five completed trades&#59; limited trade evidence is not proof of stability. Evidence: strategy.single.completed&#95;trades
- observation.0003: strategy.single&#58; sampled historical equity experienced a drawdown. Evidence: strategy.single.max&#95;drawdown

## Methodology

- Only the supplied single research result is analyzed; no market-data fetch or backtest execution.
- Numbers are copied from validated results; derived net PnL is final minus initial balance.
- Benchmark is net first evaluation open to final close under the same execution assumptions.
- Undefined metrics remain null; no pooled win rate/profit factor or continuous OOS drawdown is invented.

## Limitations

- Historical results do not predict returns, establish safety, statistical significance or robustness.
- Structural and consistency validation does not authenticate data or results. A supplied candle hash is source metadata, not proof of truthful research.
- Spread/slippage are modeled assumptions&#59; full fills and unlimited liquidity are assumed. Drawdown samples opens/closes.
- Consistency checks cannot verify prices, indicators, signal correctness or drawdown paths without original candles/equity. No backtest is rerun.

Report warnings:

- Input has no candle SHA256&#59; candle provenance is unavailable, not inferred.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-backtest/1; source schema version: not provided &#40;unversioned&#41;
- Input bytes SHA256: d05916d663165b7fdb77c31554288c6fa09902db441e991da4aa9daa4175913b
- Canonical input SHA256: cc1f70b15f4ac4a3a2f31829807334c328f8c0474e60cc6b20acceb247f85edc
- Normalized evidence SHA256: b0ec00e3b994733db732a317d58eacb8bd46ebd8c631563eb672446d87b7cdab
- Source candle SHA256: Unavailable
- No wall-clock generation timestamp is added. AI interpretation is not guaranteed reproducible.

Source history/initialization metadata:

| Field | Supplied value |
| --- | --- |
| indicator&#95;configuration | &#91;&#93; |
| indicator&#95;initializations | null |
| evaluation&#95;period | null |
