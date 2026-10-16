"""Independent numerical oracles for finite, causal advanced indicator conventions."""

import math
from collections.abc import Sequence

import pandas as pd
import pytest
from conftest import make_candles
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent.indicators import atr, bollinger, macd
from strategy_backtest_agent.rules.evaluator import (
    dependencies,
    evaluate_rule,
    prepare_context,
)
from strategy_backtest_agent.rules.indicator_specs import (
    INDICATOR_ADAPTER,
    indicator_from_key,
    indicator_key,
    prior_candles,
)
from strategy_backtest_agent.rules.models import (
    ATRIndicator,
    BollingerIndicator,
    MACDIndicator,
    RuleStrategy,
    TechnicalIndicator,
)


def recursive_ema(values: Sequence[float], period: int) -> list[float]:
    # Independent scalar recurrence; no pandas or production EMA implementation.
    result = []
    alpha = 2 / (period + 1)
    previous = values[0]
    for value in values:
        previous += alpha * (value - previous)
        result.append(previous)
    return result


def test_macd_against_scalar_reference_and_first_signal_seed() -> None:
    prices = [10.0, 12.0, 8.0, 15.0, 14.0, 9.0, 11.0, 20.0, 13.0]
    fast, slow = recursive_ema(prices, 2), recursive_ema(prices, 4)
    line = [a - b for a, b in zip(fast, slow, strict=True)]
    signal = recursive_ema(line[3:], 3)
    parts = macd(pd.Series(prices), 2, 4, 3)
    assert parts["macd"].iloc[:3].isna().all()
    assert parts["signal"].iloc[:5].isna().all()
    assert parts["histogram"].iloc[:5].isna().all()
    assert parts["macd"].iloc[3:].tolist() == pytest.approx(line[3:])
    assert parts["signal"].iloc[5:].tolist() == pytest.approx(signal[2:])
    assert parts["histogram"].iloc[5:].tolist() == pytest.approx(
        [line[i] - signal[i - 3] for i in range(5, len(prices))]
    )
    # Index labels cannot affect the nested signal alignment.
    indexed = macd(pd.Series(prices, index=range(100, 109)), 2, 4, 3)
    for name in parts:
        assert indexed[name].tolist() == pytest.approx(parts[name].tolist(), nan_ok=True)


def test_bollinger_population_std_scalar_windows() -> None:
    prices = [1.0, 2.0, 3.0, 7.0, 4.0]
    parts = bollinger(pd.Series(prices), 3, 2)
    assert parts["middle"].iloc[:2].isna().all()
    for i in range(2, len(prices)):
        window = prices[i - 2 : i + 1]
        middle = sum(window) / 3
        std = math.sqrt(sum((v - middle) ** 2 for v in window) / 3)
        assert parts["middle"].iloc[i] == pytest.approx(middle)
        assert parts["upper"].iloc[i] == pytest.approx(middle + 2 * std)
        assert parts["lower"].iloc[i] == pytest.approx(middle - 2 * std)
    assert parts["upper"].iloc[2] == pytest.approx(2 + 2 * math.sqrt(2 / 3))


def test_atr_true_range_gap_up_gap_down_and_wilder_seed() -> None:
    candles = make_candles([10, 15, 7, 9], [10, 14, 8, 8])
    # TR = [2, 6, 9, 3]: second includes gap up, third includes gap down.
    highs, lows = [11, 16, 9, 10], [9, 14, 6, 7]
    candles = [
        c.model_copy(update={"high": h, "low": low})
        for c, h, low in zip(candles, highs, lows, strict=True)
    ]
    values = atr(candles, 2)
    assert math.isnan(values.iloc[0])
    assert values.iloc[1:].tolist() == pytest.approx([4, 6.5, 4.75])
    assert atr(candles, 1).tolist() == [2, 6, 9, 3]
    assert atr(candles[:1], 1).tolist() == [2]


@pytest.mark.parametrize("kind", ["macd", "bollinger", "atr"])
def test_flat_history_and_insufficient_input(kind: str) -> None:
    prices = pd.Series([10.0] * 50)
    if kind == "macd":
        parts = macd(prices, 2, 4, 3)
        assert all(part.dropna().eq(0).all() for part in parts.values())
        assert all(part.isna().all() for part in macd(prices[:1], 2, 4, 3).values())
    elif kind == "bollinger":
        parts = bollinger(prices, 3, 2)
        assert all(part.dropna().eq(10).all() for part in parts.values())
        assert all(part.isna().all() for part in bollinger(prices[:1], 3, 2).values())
        assert bollinger(prices, 1, 2)["upper"].eq(10).all()
    else:
        assert atr(make_candles(prices.tolist()), 3).dropna().eq(0).all()
        assert atr(make_candles([10]), 3).isna().all()
        assert atr([], 3).empty


@pytest.mark.parametrize("period", [0, -1, True, 1.5, "2"])
@pytest.mark.parametrize("kind", ["macd", "bollinger", "atr"])
def test_invalid_periods(period: object, kind: str) -> None:
    # Runtime invalid inputs deliberately bypass static annotations.
    function = {"macd": macd, "bollinger": bollinger, "atr": atr}[kind]
    with pytest.raises((ValueError, TypeError)):
        function(pd.Series([10.0] * 8) if kind != "atr" else make_candles([10.0] * 8), period)  # type: ignore[operator]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_series_rejected(value: float) -> None:
    for function in (macd, bollinger):
        with pytest.raises(ValueError):
            function(pd.Series([10.0, value, 11.0]))
    with pytest.raises(ValueError):
        atr([make_candles([10])[0].model_copy(update={"high": value})])


@pytest.mark.parametrize("multiplier", [0, -1, float("nan"), float("inf"), True])
def test_invalid_bollinger_multiplier(multiplier: float) -> None:
    with pytest.raises(ValueError):
        bollinger(pd.Series([1.0, 2.0, 3.0]), 2, multiplier)


def test_invalid_macd_order_and_atr_ohlc() -> None:
    for fast, slow in [(3, 3), (4, 2)]:
        with pytest.raises(ValueError):
            macd(pd.Series([10.0] * 8), fast, slow, 2)
    candle = make_candles([10])[0]
    with pytest.raises(ValueError):
        atr([candle.model_copy(update={"high": 9})])
    with pytest.raises(ValueError):
        atr([candle, candle])


@pytest.mark.parametrize(
    "definition",
    [
        {"name": "macd", "component": "upper"},
        {"name": "macd", "fast_period": 26},
        {"name": "macd", "slow_period": 0},
        {"name": "macd", "signal_period": True},
        {"name": "macd", "period": 14},
        {"name": "bollinger", "component": "signal"},
        {"name": "bollinger"},
        {"name": "bollinger", "component": "lower", "multiplier": 0},
        {"name": "atr", "component": "atr"},
        {"name": "atr", "period": 0},
        {"name": "rsi", "period": 14, "component": "signal"},
    ],
)
def test_invalid_dsl_parameters(definition: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        INDICATOR_ADAPTER.validate_python(definition)


def test_complete_keys_and_roundtrip_defaults() -> None:
    specs: list[TechnicalIndicator] = [
        MACDIndicator(
            name="macd",
        ),
        MACDIndicator(name="macd", component="signal"),
        MACDIndicator(name="macd", fast_period=10),
        MACDIndicator(name="macd", slow_period=30),
        MACDIndicator(name="macd", signal_period=8),
        BollingerIndicator(name="bollinger", component="upper"),
        BollingerIndicator(name="bollinger", component="lower"),
        BollingerIndicator(name="bollinger", component="upper", multiplier=3),
        BollingerIndicator(name="bollinger", component="upper", period=21),
        ATRIndicator(
            name="atr",
        ),
        ATRIndicator(name="atr", period=15),
    ]
    assert len({indicator_key(s) for s in specs}) == len(specs)
    for spec in specs:
        assert indicator_from_key(*indicator_key(spec)) == spec
    assert (
        prior_candles(
            MACDIndicator(
                name="macd",
            )
        )
        == 350
    )
    assert (
        prior_candles(
            ATRIndicator(
                name="atr",
            )
        )
        == 280
    )
    assert prior_candles(BollingerIndicator(name="bollinger", component="lower")) == 20
    assert indicator_key(INDICATOR_ADAPTER.validate_python(indicator("rsi", 14))) == ("rsi", 14)


def test_component_comparison_nested_mixed_rules() -> None:
    line = MACDIndicator(name="macd", fast_period=2, slow_period=4, signal_period=2)
    signal = line.model_copy(update={"component": "signal"})
    rules = RuleStrategy.model_validate(
        {
            "type": "rules",
            "entry": {
                "type": "and",
                "conditions": [
                    comparison(line, ">", signal),
                    {
                        "type": "or",
                        "conditions": [
                            comparison(indicator("sma", 2), ">", {"type": "value", "value": 0}),
                            comparison(
                                ATRIndicator(name="atr", period=2),
                                ">",
                                {"type": "value", "value": 100},
                            ),
                        ],
                    },
                ],
            },
            "exit": comparison(line, "<", signal),
        }
    )
    candles = make_candles([10, 10, 10, 11, 12, 13, 20, 30])
    context = prepare_context(candles, dependencies(rules))
    assert len(context.indicators) == 4
    assert evaluate_rule(rules.entry, 7, context)
    assert not evaluate_rule(rules.exit, 7, context)
    # A state can stay true on consecutive candles; no transition operator exists.
    assert evaluate_rule(rules.entry, 6, context)
    with pytest.raises(ValueError):
        strategy(comparison(line, "crosses_above", signal))


def test_nonfinite_available_bollinger_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        bollinger(pd.Series([1e308, 1e-308, 1e308]), 2, 2)


@pytest.mark.parametrize(
    "definition",
    [{}, {"type": "indicator"}, {"period": 14}, {"component": "signal"}, {"multiplier": 2}],
)
def test_indicator_family_must_be_explicit(definition: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        INDICATOR_ADAPTER.validate_python(definition)
