"""Default-period mathematical oracles and an actually restrictive RSI/ATR filter."""

import math
from datetime import timedelta
from fractions import Fraction

import pandas as pd
import pytest
from test_advanced_research import START, history, settings
from test_comparison_engine import named
from test_rules import comparison, strategy

from strategy_backtest_agent import indicators
from strategy_backtest_agent.comparison.engine import prepare_shared_history, run_comparison
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import dependencies, evaluate_rule, prepare_context
from strategy_backtest_agent.rules.indicator_specs import indicator_key, prior_candles
from strategy_backtest_agent.rules.models import (
    ATRIndicator,
    BollingerIndicator,
    Indicator,
    MACDIndicator,
    RuleStrategy,
    TechnicalIndicator,
)


def test_default_macd_price_emas_and_signal_against_closed_form_rational_oracle() -> None:
    # Ramp prices C[n]=100+n. Exact EMA is C[n] - (p-1)/2*(1-q**n), q=(p-1)/(p+1).
    # This oracle uses rational closed forms, not the production/pandas recurrence.
    prices = pd.Series([100.0 + i for i in range(75)])

    def ramp_ema(period: int, index: int) -> Fraction:
        q = Fraction(period - 1, period + 1)
        return Fraction(100 + index) - Fraction(period - 1, 2) * (1 - q**index)

    fast = [ramp_ema(12, i) for i in range(75)]
    slow = [ramp_ema(26, i) for i in range(75)]
    lines = [a - b for a, b in zip(fast, slow, strict=True)]
    parts = indicators.macd(prices)
    assert indicators.ema(prices, 12).iloc[:11].isna().all()
    assert indicators.ema(prices, 26).iloc[:25].isna().all()
    assert indicators.ema(prices, 12).iloc[11:].tolist() == pytest.approx(
        [float(v) for v in fast[11:]]
    )
    assert indicators.ema(prices, 26).iloc[25:].tolist() == pytest.approx(
        [float(v) for v in slow[25:]]
    )
    assert parts["macd"].iloc[:25].isna().all()
    assert parts["signal"].iloc[:33].isna().all()
    assert parts["histogram"].iloc[:33].isna().all()
    assert parts["macd"].iloc[25:].tolist() == pytest.approx([float(v) for v in lines[25:]])
    for index in range(33, 75):
        k = index - 25
        q = Fraction(4, 5)
        expected_signal = q**k * lines[25] + Fraction(1, 5) * sum(
            (q ** (k - j) * lines[25 + j] for j in range(1, k + 1)), start=Fraction(0)
        )
        assert parts["signal"].iloc[index] == pytest.approx(float(expected_signal), abs=1e-12)
        assert parts["histogram"].iloc[index] == pytest.approx(
            float(lines[index] - expected_signal), abs=1e-12
        )
    assert prior_candles(MACDIndicator(name="macd")) == 350


def test_default_bollinger_rolling_alignment_against_integer_window_sums() -> None:
    # Window 1..20: mean=10.5, population variance=(20**2-1)/12=33.25.
    # Next window 2..20 plus 100 tests alignment, rather than only a linear ramp.
    prices = [float(i) for i in range(1, 21)] + [100.0, 7.0]
    parts = indicators.bollinger(pd.Series(prices))
    for component in parts.values():
        assert component.iloc[:19].isna().all()
    for index in (19, 20, 21):
        window = [Fraction(str(v)) for v in prices[index - 19 : index + 1]]
        mean = sum(window) / 20
        variance = sum(v * v for v in window) / 20 - mean * mean
        assert parts["middle"].iloc[index] == pytest.approx(float(mean))
        assert parts["upper"].iloc[index] == pytest.approx(float(mean) + 2 * math.sqrt(variance))
        assert parts["lower"].iloc[index] == pytest.approx(float(mean) - 2 * math.sqrt(variance))
    assert parts["upper"].iloc[19] == pytest.approx(10.5 + 2 * math.sqrt(33.25))
    assert prior_candles(BollingerIndicator(name="bollinger", component="middle")) == 20


def test_default_atr_gap_oracle_and_wilder_initialization() -> None:
    # First 14 TRs=2; gap up TR=12, gap down TR=15, then TR=4.
    source = [
        Candle(
            timestamp=START + timedelta(hours=i), open=100, close=100, high=101, low=99, volume=1
        )
        for i in range(14)
    ]
    source += [
        Candle(
            timestamp=START + timedelta(hours=14 + i), open=o, close=c, high=h, low=low, volume=1
        )
        for i, (o, c, h, low) in enumerate(
            [(110, 111, 112, 110), (100, 99, 100, 96), (99, 99, 101, 97)]
        )
    ]
    actual = indicators.atr(source, 14)
    assert actual.iloc[:13].isna().all()
    assert actual.iloc[13:].tolist() == pytest.approx([2, 19 / 7, 176 / 49, 1242 / 343])
    assert prior_candles(ATRIndicator(name="atr")) == 280


def filtered_rules() -> tuple[RuleStrategy, RuleStrategy]:
    rsi = Indicator(name="rsi", period=14)
    entry = comparison(rsi, "<", {"type": "value", "value": 30})
    exit_rule = comparison(rsi, ">", {"type": "value", "value": 70})
    return RuleStrategy.model_validate(
        {
            "entry": {
                "type": "and",
                "conditions": [
                    entry,
                    comparison(
                        ATRIndicator(name="atr", period=14), ">", {"type": "value", "value": 100}
                    ),
                ],
            },
            "exit": exit_rule,
        }
    ), strategy(entry, exit_rule)


def filter_history(mode: str) -> list[Candle]:
    # Two down/up cycles yield exactly two independently calculable RSI opportunities.
    source = []
    for i in range(-280, 96):
        if i < 0:
            close = 1000
        elif i < 20:
            close = 1000 - 4 * (i + 1)
        elif i < 50:
            close = 920 + 4 * (i - 19)
        elif i < 80:
            close = 1040 - 4 * (i - 49)
        else:
            close = 920 + 4 * (i - 79)
        width = (
            200 if mode == "high" or mode == "mixed" and i < 24 else 50 if mode == "equal" else 1
        )
        source.append(
            Candle(
                timestamp=START + timedelta(hours=i),
                open=close,
                close=close,
                high=close + width,
                low=close - width,
                volume=1,
            )
        )
    return source


def config() -> ComparisonConfig:
    filtered, baseline = filtered_rules()
    return ComparisonConfig.model_validate(
        {
            **settings(filtered),
            "strategies": [named("filtered", filtered), named("baseline", baseline)],
        }
    )


@pytest.mark.parametrize("mode,expected_filtered", [("low", 0), ("high", 2), ("mixed", 1)])
def test_atr_filter_passes_blocks_and_changes_real_trades(
    mode: str, expected_filtered: int
) -> None:
    source = filter_history(mode)
    configuration = config()
    _, boundary, rules, cache, _ = prepare_shared_history(source, configuration)
    filtered, baseline = rules
    rsi_values = cache.indicators[("rsi", 14)]
    atr_values = cache.indicators[indicator_key(ATRIndicator(name="atr", period=14))]
    assert rsi_values[boundary] == 0  # Flat RSI seed followed by one negative close delta.
    assert evaluate_rule(baseline.entry, boundary, cache)
    assert evaluate_rule(filtered.entry, boundary, cache) == (mode != "low")
    if mode == "low":
        assert max(atr_values[boundary:]) < 5.0000001
    elif mode == "high":
        assert atr_values[boundary:] == pytest.approx([400] * 96)
    else:
        assert atr_values[boundary : boundary + 24] == pytest.approx([400] * 24)
        for offset in range(24, 96):
            # All low-volatility TRs are 5: close moves by 4, plus wick of 1.
            assert atr_values[boundary + offset] == pytest.approx(
                5 + 395 * (13 / 14) ** (offset - 23)
            )
    report = run_comparison(source, configuration)
    filtered_result, baseline_result = [r.result for r in report.results]
    assert baseline_result.total_trades == 2
    assert filtered_result.total_trades == expected_filtered
    assert (
        filtered_result.buy_and_hold_return_percent == baseline_result.buy_and_hold_return_percent
    )
    for result in (filtered_result, baseline_result):
        assert result.initial_balance == 1000
        assert result.final_balance == pytest.approx(1000 + sum(t.pnl for t in result.trades))
        for trade in result.trades:
            index = next(i for i, c in enumerate(source) if c.timestamp == trade.entry_time)
            assert evaluate_rule(
                filtered.entry if result is filtered_result else baseline.entry, index - 1, cache
            )
            assert trade.entry_execution is not None
            assert trade.entry_execution.reference_price == source[index].open
    if mode == "low":
        assert filtered_result.final_balance == 1000 and filtered_result.costs.fees == 0
    if mode == "high":
        assert filtered_result == baseline_result
    if mode == "mixed":
        second_entry = baseline_result.trades[1].entry_time
        signal = next(i for i, c in enumerate(source) if c.timestamp == second_entry) - 1
        assert rsi_values[signal] < 30 and atr_values[signal] < 100
        assert not evaluate_rule(filtered.entry, signal, cache)
        assert filtered_result.trades == baseline_result.trades[:1]


def test_same_closes_different_high_low_changes_only_atr_and_filter() -> None:
    low, high = filter_history("low"), filter_history("high")
    keys = dependencies(filtered_rules()[0])
    a = prepare_context(low, keys, evaluation_start=280)
    b = prepare_context(high, keys, evaluation_start=280)
    assert a.prices == b.prices
    assert a.indicators[("rsi", 14)] == pytest.approx(b.indicators[("rsi", 14)], nan_ok=True)
    atr_key = indicator_key(ATRIndicator(name="atr", period=14))
    assert max(a.indicators[atr_key][280:]) < 100
    assert min(b.indicators[atr_key][280:]) == 400
    assert not evaluate_rule(filtered_rules()[0].entry, 280, a)
    assert evaluate_rule(filtered_rules()[0].entry, 280, b)


def test_restrictive_filter_exact_rsi_transitions_next_open_pnl_and_benchmark() -> None:
    source = filter_history("mixed")
    report = run_comparison(source, config())
    filtered, baseline = [row.result for row in report.results]
    # RSI uses 15 flat prior closes. Each following move has magnitude 4.
    # Compute exact rational Wilder gains/losses, independent of production RSI.
    gain = loss = Fraction(0)
    reference = []
    for i in range(280, len(source)):
        change = Fraction(str(source[i].close)) - Fraction(str(source[i - 1].close))
        gain = (13 * gain + (change if change > 0 else Fraction(0))) / 14
        loss = (13 * loss + (-change if change < 0 else Fraction(0))) / 14
        reference.append(
            50 if gain == loss == 0 else 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
        )
    assert reference[0] == 0
    assert reference[32] < 70 < reference[33]
    assert reference[63] > 30 > reference[64]
    assert reference[93] < 70 < reference[94]
    assert [(t.entry_time, t.exit_time) for t in filtered.trades] == [
        (START + timedelta(hours=1), START + timedelta(hours=34))
    ]
    assert [(t.entry_time, t.exit_time) for t in baseline.trades] == [
        (START + timedelta(hours=1), START + timedelta(hours=34)),
        (START + timedelta(hours=65), START + timedelta(hours=95)),
    ]
    first_final = 1000 * (980 * 0.998 * 0.99) / (992 * 1.002 * 1.01)
    second_final = first_final * (984 * 0.998 * 0.99) / (976 * 1.002 * 1.01)
    assert filtered.final_balance == pytest.approx(first_final)
    assert baseline.final_balance == pytest.approx(second_final)
    first_q = 1000 / (992 * 1.002 * 1.01)
    second_q = first_final / (976 * 1.002 * 1.01)
    first_fees = first_q * (992 * 1.002 + 980 * 0.998) * 0.01
    second_fees = second_q * (976 * 1.002 + 984 * 0.998) * 0.01
    assert filtered.costs.fees == pytest.approx(first_fees)
    assert baseline.costs.fees == pytest.approx(first_fees + second_fees)
    assert filtered.costs.modeled_spread_cost == pytest.approx(first_q * (992 + 980) * 0.001)
    assert baseline.costs.modeled_slippage_cost == pytest.approx(
        (first_q * (992 + 980) + second_q * (976 + 984)) * 0.001
    )
    expected_benchmark = (984 * 0.998 * 0.99 / (996 * 1.002 * 1.01) - 1) * 100
    assert filtered.buy_and_hold_return_percent == pytest.approx(expected_benchmark)
    assert baseline.buy_and_hold_return_percent == pytest.approx(expected_benchmark)


COMPONENTS: list[TechnicalIndicator] = [
    *[
        MACDIndicator.model_validate({"name": "macd", "component": component})
        for component in ("macd", "signal", "histogram")
    ],
    *[
        BollingerIndicator.model_validate({"name": "bollinger", "component": component})
        for component in ("upper", "middle", "lower")
    ],
    ATRIndicator(name="atr"),
]


@pytest.mark.parametrize("spec", COMPONENTS)
def test_default_components_future_ohlc_cannot_change_values_or_signals(
    spec: TechnicalIndicator,
) -> None:
    required = prior_candles(spec)
    source = history(required)
    key = indicator_key(spec)
    rule = strategy(comparison(spec, ">", {"type": "value", "value": 0}))
    original = prepare_context(source, {key}, evaluation_start=required)
    stop = required + 48
    changed = [
        c
        if i < stop
        else c.model_copy(update={"open": 1000, "close": 1000, "high": 2000, "low": 1})
        for i, c in enumerate(source)
    ]
    altered = prepare_context(changed, {key}, evaluation_start=required)
    prefix = prepare_context(source[:stop], {key}, evaluation_start=required)
    assert altered.indicators[key][:stop] == pytest.approx(
        original.indicators[key][:stop], nan_ok=True
    )
    assert prefix.indicators[key] == pytest.approx(original.indicators[key][:stop], nan_ok=True)
    for index in range(required, stop):
        assert evaluate_rule(rule.entry, index, original) == evaluate_rule(
            rule.entry, index, altered
        )
        assert evaluate_rule(rule.entry, index, original) == evaluate_rule(
            rule.entry, index, prefix
        )
    with pytest.raises(ValueError, match="insufficient"):
        prepare_context(source[1:], {key}, evaluation_start=required - 1)


def test_atr_equal_to_threshold_is_rejected_by_strict_greater_than() -> None:
    source = filter_history("equal")
    configuration = config()
    _, boundary, rules, cache, _ = prepare_shared_history(source, configuration)
    key = indicator_key(ATRIndicator(name="atr", period=14))
    # Every TR is exactly 100; the SMA seed and Wilder recurrence remain exactly 100.
    assert cache.indicators[key][boundary:] == [100] * 96
    assert evaluate_rule(rules[1].entry, boundary, cache)
    assert not evaluate_rule(rules[0].entry, boundary, cache)
    filtered, baseline = [row.result for row in run_comparison(source, configuration).results]
    assert filtered.total_trades == 0 and baseline.total_trades == 2
