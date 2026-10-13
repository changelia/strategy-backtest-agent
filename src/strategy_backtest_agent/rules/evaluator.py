"""Cached causal indicators and deterministic boolean evaluation."""

import math
import operator
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from strategy_backtest_agent import indicators
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.models import (
    Comparison,
    Indicator,
    Operand,
    Price,
    Rule,
    RuleStrategy,
)


@dataclass(frozen=True)
class Context:
    prices: list[float]
    indicators: dict[tuple[str, int], list[float]]


def dependencies(strategy: RuleStrategy) -> set[tuple[str, int]]:
    found: set[tuple[str, int]] = set()

    def visit(rule: Rule) -> None:
        if isinstance(rule, Comparison):
            for operand in (rule.left, rule.right):
                if isinstance(operand, Indicator):
                    found.add((operand.name, operand.period))
        else:
            for child in rule.conditions:
                visit(child)

    visit(strategy.entry)
    visit(strategy.exit)
    return found


def warmup_count(strategy: RuleStrategy) -> int:
    """EMA: five spans; RSI: period+1 closes; SMA: period closes."""
    return max(
        (5 * p if n == "ema" else p + (n == "rsi") for n, p in dependencies(strategy)), default=0
    )


def prepare_indicators(candles: Sequence[Candle], strategy: RuleStrategy) -> Context:
    return prepare_context(candles, dependencies(strategy))


def prepare_context(
    candles: Sequence[Candle],
    indicator_dependencies: set[tuple[str, int]],
) -> Context:
    """Calculate a run-local union of validated strategy dependencies once."""
    prices = [c.close for c in candles]
    series = pd.Series(prices, dtype=float)
    functions = {"rsi": indicators.rsi, "sma": indicators.sma, "ema": indicators.ema}
    cache = {
        key: functions[key[0]](series, key[1]).tolist() for key in sorted(indicator_dependencies)
    }
    return Context(prices, cache)


def evaluate_operand(operand: Operand, index: int, context: Context) -> float:
    if isinstance(operand, Price):
        return context.prices[index]
    if isinstance(operand, Indicator):
        values = context.indicators.get((operand.name, operand.period))
        return float("nan") if values is None else values[index]
    return operand.value


def evaluate_comparison(rule: Comparison, index: int, context: Context) -> bool:
    left = evaluate_operand(rule.left, index, context)
    right = evaluate_operand(rule.right, index, context)
    if not math.isfinite(left) or not math.isfinite(right):
        return False
    operations = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}
    return bool(operations[rule.operator](left, right))


def evaluate_rule(rule: Rule, index: int, context: Context) -> bool:
    if isinstance(rule, Comparison):
        return evaluate_comparison(rule, index, context)
    values = (evaluate_rule(child, index, context) for child in rule.conditions)
    return all(values) if rule.type == "and" else any(values)
