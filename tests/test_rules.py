"""Rule validation, causal evaluation, caching, and execution regression tests."""

import math

import pandas as pd
import pytest
from conftest import make_candles
from pydantic import ValidationError

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig
from strategy_backtest_agent.rules.evaluator import (
    Context,
    dependencies,
    evaluate_rule,
    prepare_indicators,
)
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.rules.models import Comparison, Indicator, RuleStrategy, Value
from strategy_backtest_agent.strategy import legacy_rules, rsi_signals


def comparison(left: object, operator: str = "<", right: object = None) -> dict[str, object]:
    return {
        "type": "comparison",
        "left": left,
        "operator": operator,
        "right": right if right is not None else {"type": "value", "value": 30},
    }


def indicator(name: str = "rsi", period: int = 14) -> dict[str, object]:
    return {"type": "indicator", "name": name, "period": period}


def strategy(entry: object, exit: object = None) -> RuleStrategy:
    return RuleStrategy.model_validate(
        {"type": "rules", "entry": entry, "exit": exit if exit is not None else entry}
    )


@pytest.mark.parametrize("name,period", [("rsi", 2), ("rsi", 500), ("sma", 1000), ("ema", 2)])
def test_indicator_limits(name: str, period: int) -> None:
    assert Indicator.model_validate(indicator(name, period)).period == period


@pytest.mark.parametrize(
    "name,period",
    [
        ("macd", 14),
        ("rsi", 501),
        ("rsi", 1),
        ("sma", 1001),
        ("ema", 0),
        ("ema", True),
        ("rsi", 2.5),
        ("sma", "20"),
    ],
)
def test_invalid_indicators(name: str, period: object) -> None:
    with pytest.raises(ValidationError):
        Indicator.model_validate({"type": "indicator", "name": name, "period": period})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_finite_constants(value: float) -> None:
    with pytest.raises(ValidationError):
        Value(value=value)


@pytest.mark.parametrize(
    "operator,expected", [("<", False), ("<=", True), (">", False), (">=", True)]
)
def test_operators_and_price(operator: str, expected: bool) -> None:
    rules = strategy(comparison({"type": "price"}, operator))
    assert evaluate_rule(rules.entry, 0, Context([30], {})) is expected
    assert RuleStrategy.model_validate_json(rules.model_dump_json()) == rules


@pytest.mark.parametrize(
    "invalid",
    [
        comparison({"type": "price"}, "=="),
        comparison({"type": "python", "code": "x"}),
        {"type": "not", "conditions": []},
        {"type": "and", "conditions": []},
        {"type": "or", "conditions": []},
    ],
)
def test_closed_language(invalid: object) -> None:
    with pytest.raises(ValidationError):
        strategy(invalid)


def test_depth_and_comparison_limits() -> None:
    leaf = comparison({"type": "price"})
    tree: object = leaf
    for _ in range(4):
        tree = {"type": "and", "conditions": [tree]}
    strategy(tree, leaf)  # depth 5 accepted
    with pytest.raises(ValidationError, match="depth"):
        strategy({"type": "or", "conditions": [tree]}, leaf)
    strategy({"type": "and", "conditions": [leaf] * 19}, leaf)
    with pytest.raises(ValidationError, match="comparisons"):
        strategy({"type": "and", "conditions": [leaf] * 20}, leaf)


@pytest.mark.parametrize("name,left,right", [("rsi", 20, 30), ("ema", 20, 30), ("sma", 20, 30)])
def test_indicator_comparison(name: str, left: float, right: float) -> None:
    rule = strategy(comparison(indicator(name, 2), "<", {"type": "value", "value": right}))
    assert evaluate_rule(rule.entry, 0, Context([50], {(name, 2): [left]}))


@pytest.mark.parametrize("left,right", [("sma", "sma"), ("ema", "sma")])
def test_dynamic_indicator_pairs(left: str, right: str) -> None:
    rule = strategy(comparison(indicator(left, 20), ">=", indicator(right, 50)))
    context = Context([10], {(left, 20): [30], (right, 50): [20]})
    assert evaluate_rule(rule.entry, 0, context)


@pytest.mark.parametrize(
    "kind,values,expected",
    [
        ("and", [True, True], True),
        ("and", [True, False], False),
        ("or", [False, True], True),
        ("or", [False, False], False),
    ],
)
def test_boolean_semantics(kind: str, values: list[bool], expected: bool) -> None:
    rules = strategy(
        {
            "type": kind,
            "conditions": [
                comparison({"type": "value", "value": 0 if value else 100}) for value in values
            ],
        }
    )
    assert evaluate_rule(rules.entry, 0, Context([10], {})) is expected


def test_nested_rules_and_formatting() -> None:
    rules = strategy(
        {
            "type": "and",
            "conditions": [
                comparison({"type": "price"}),
                {
                    "type": "or",
                    "conditions": [
                        comparison(indicator()),
                        comparison({"type": "price"}, ">", indicator("ema", 2)),
                    ],
                },
            ],
        }
    )
    assert evaluate_rule(rules.entry, 0, Context([20], {("rsi", 14): [math.nan], ("ema", 2): [10]}))
    assert format_rule(rules.entry) == "(PRICE < 30 AND (RSI(14) < 30 OR PRICE > EMA(2)))"


@pytest.mark.parametrize("missing", [math.nan, math.inf, -math.inf, None])
def test_missing_operands_never_signal(missing: float | None) -> None:
    rule = strategy(comparison(indicator("ema", 2), ">", {"type": "price"}))
    context = Context([10], {} if missing is None else {("ema", 2): [missing]})
    assert not evaluate_rule(rule.entry, 0, context)


def test_cached_unique_indicators(monkeypatch: pytest.MonkeyPatch) -> None:
    from strategy_backtest_agent import indicators

    original = indicators.rsi
    calls: list[int] = []

    def counted(series: pd.Series, period: int) -> pd.Series:
        calls.append(period)
        return original(series, period)

    monkeypatch.setattr(indicators, "rsi", counted)
    rule = strategy({"type": "and", "conditions": [comparison(indicator("rsi", 2))] * 3})
    context = prepare_indicators(make_candles([10, 9, 8, 7]), rule)
    assert dependencies(rule) == {("rsi", 2)}
    assert calls == [2]
    assert context.indicators[("rsi", 2)][2] == 0


def test_position_aware_simultaneous_signals() -> None:
    rule = strategy(comparison({"type": "price"}, ">", {"type": "value", "value": 0}))
    candles = make_candles([10] * 5)
    result = run_backtest(candles, BacktestConfig(trading_fee=0), rule)
    assert [(t.entry_time, t.exit_time) for t in result.trades] == [
        (candles[1].timestamp, candles[2].timestamp),
        (candles[3].timestamp, candles[4].timestamp),
    ]
    assert result.final_balance == 10000


@pytest.mark.parametrize("period", [2, 14, 500])
def test_legacy_signals_and_metrics_equivalence(
    period: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    candles = make_candles([10, 9, 8, 12, 13, 5, 4, 8, 9] * 100)
    config = BacktestConfig(rsi_period=period)
    rules = legacy_rules(config)
    assert rules is not None
    context = prepare_indicators(candles, rules)
    signals = [
        1
        if evaluate_rule(rules.entry, i, context)
        else -1
        if evaluate_rule(rules.exit, i, context)
        else 0
        for i in range(len(candles))
    ]
    assert signals == rsi_signals(candles, config)
    actual = run_backtest(candles, config, rules)
    # Force the v0.2.0 signal path as an independent metrics/trades oracle.
    monkeypatch.setattr("strategy_backtest_agent.backtester.legacy_rules", lambda _: None)
    assert actual == run_backtest(candles, config)


def test_no_lookahead_and_final_signal() -> None:
    rule = strategy(
        comparison({"type": "price"}, "<", {"type": "value", "value": 9}),
        comparison({"type": "price"}, ">", {"type": "value", "value": 11}),
    )
    first = make_candles([10, 8, 12, 13], [10, 8, 7, 15])
    changed = make_candles([10, 8, 100, 200], [10, 8, 7, 150])
    config = BacktestConfig(initial_balance=1000, trading_fee=0.01)
    a = run_backtest(first, config, rule)
    b = run_backtest(changed, config, rule)
    assert a.trades[0].entry_price == b.trades[0].entry_price == 7
    assert a.trades[0].quantity == pytest.approx(1000 / (7 * 1.01))
    assert a.final_balance == pytest.approx(1000 + a.trades[0].pnl)
    assert run_backtest(first[:2], config, rule).total_trades == 0


def test_constructed_and_mutated_rules_revalidated() -> None:
    rule = strategy(comparison({"type": "price"}))
    assert isinstance(rule.entry, Comparison)
    bad = Comparison.model_construct(left=rule.entry.left, operator="==", right=Value(value=1))
    with pytest.raises(ValidationError):
        run_backtest(
            make_candles([10]), BacktestConfig(), RuleStrategy.model_construct(entry=bad, exit=bad)
        )


@pytest.mark.parametrize("value", [True, "30", "float('nan')"])
def test_constants_are_numeric_not_expressions(value: object) -> None:
    with pytest.raises(ValidationError):
        Value.model_validate({"type": "value", "value": value})


def test_caching_across_entry_exit_and_periods(monkeypatch: pytest.MonkeyPatch) -> None:
    from strategy_backtest_agent import indicators

    calls: list[tuple[str, int]] = []
    original_rsi, original_ema = indicators.rsi, indicators.ema

    def counted_rsi(series: pd.Series, period: int) -> pd.Series:
        calls.append(("rsi", period))
        return original_rsi(series, period)

    def counted_ema(series: pd.Series, period: int) -> pd.Series:
        calls.append(("ema", period))
        return original_ema(series, period)

    monkeypatch.setattr(indicators, "rsi", counted_rsi)
    monkeypatch.setattr(indicators, "ema", counted_ema)
    rule = strategy(
        {
            "type": "and",
            "conditions": [
                comparison(indicator()),
                comparison({"type": "price"}, ">", indicator("ema", 200)),
            ],
        },
        {
            "type": "or",
            "conditions": [
                comparison(indicator(), ">"),
                comparison({"type": "price"}, "<", indicator("ema", 50)),
            ],
        },
    )
    context = prepare_indicators(make_candles([10.0] * 1001), rule)
    for i in range(1001):
        evaluate_rule(rule.entry, i, context)
        evaluate_rule(rule.exit, i, context)
    assert sorted(calls) == [("ema", 50), ("ema", 200), ("rsi", 14)]
