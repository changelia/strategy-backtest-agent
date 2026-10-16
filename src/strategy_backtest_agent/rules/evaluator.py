"""Cached causal indicators and deterministic boolean evaluation."""

import math
import operator
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from strategy_backtest_agent import indicators
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.indicator_specs import (
    indicator_from_key,
    indicator_key,
    prior_candles,
)
from strategy_backtest_agent.rules.models import (
    INDICATOR_TYPES,
    ATRIndicator,
    BollingerIndicator,
    Comparison,
    Indicator,
    MACDIndicator,
    Operand,
    Price,
    Rule,
    RuleStrategy,
)


@dataclass(frozen=True)
class Context:
    prices: list[float]
    indicators: dict[tuple[str, int], list[float]]
    range_inputs: list[tuple[float, float, float]] | None = None

    def prefix(self, stop: int) -> "Context":
        """Truncate every dependency input alongside cached values at a segment end."""
        return Context(
            self.prices[:stop],
            {key: values[:stop] for key, values in self.indicators.items()},
            self.range_inputs[:stop] if self.range_inputs is not None else None,
        )


def dependencies(strategy: RuleStrategy) -> set[tuple[str, int]]:
    found: set[tuple[str, int]] = set()

    def visit(rule: Rule) -> None:
        if isinstance(rule, Comparison):
            for operand in (rule.left, rule.right):
                if isinstance(operand, INDICATOR_TYPES):
                    found.add(indicator_key(operand))
        else:
            for child in rule.conditions:
                visit(child)

    visit(strategy.entry)
    visit(strategy.exit)
    return found


def indicator_warmup(name: str, period: int) -> int:
    """Existing finite prior-close policy for a validated indicator dependency."""
    return prior_candles(indicator_from_key(name, period))


def warmup_count(strategy: RuleStrategy) -> int:
    """EMA: five spans; RSI: period+1 closes; SMA: period closes."""
    return max((indicator_warmup(n, p) for n, p in dependencies(strategy)), default=0)


def prepare_indicators(candles: Sequence[Candle], strategy: RuleStrategy) -> Context:
    return prepare_context(candles, dependencies(strategy))


def prepare_context(
    candles: Sequence[Candle],
    indicator_dependencies: set[tuple[str, int]],
    *,
    evaluation_start: int | None = None,
    local_seeds: bool = False,
) -> Context:
    """One calculation per parameter family; advanced seeds never depend on peers.

    Without an evaluation boundary this is the direct finite-history evaluator.
    With a boundary, advanced dependencies use their own prior history. Legacy
    shared-history semantics are retained unless local_seeds is explicitly enabled.
    """
    prices = [c.close for c in candles]
    functions = {"rsi": indicators.rsi, "sma": indicators.sma, "ema": indicators.ema}
    cache: dict[tuple[str, int], list[float]] = {}
    families: dict[tuple[str, int], dict[str, list[float]]] = {}
    specs = [indicator_from_key(*key) for key in sorted(indicator_dependencies)]
    legacy_required = max(
        (prior_candles(spec) for spec in specs if isinstance(spec, Indicator)), default=0
    )
    for spec in specs:
        key = indicator_key(spec)
        start = 0
        if evaluation_start is not None:
            required = prior_candles(spec)
            if evaluation_start < required:
                raise ValueError(f"insufficient {spec.name} prior history: need {required} candles")
            start = evaluation_start - (
                legacy_required if isinstance(spec, Indicator) and not local_seeds else required
            )
        local_prices = pd.Series(prices[start:], dtype=float)
        if isinstance(spec, Indicator):
            values = functions[spec.name](local_prices, spec.period).tolist()
        elif isinstance(spec, ATRIndicator):
            values = indicators.atr(candles[start:], spec.period).tolist()
        else:
            family = indicator_key(
                spec.model_copy(
                    update={"component": "macd" if isinstance(spec, MACDIndicator) else "middle"}
                )
            )
            if family not in families:
                if isinstance(spec, MACDIndicator):
                    parts = indicators.macd(
                        local_prices, spec.fast_period, spec.slow_period, spec.signal_period
                    )
                else:
                    assert isinstance(spec, BollingerIndicator)
                    parts = indicators.bollinger(local_prices, spec.period, spec.multiplier)
                families[family] = {name: part.tolist() for name, part in parts.items()}
            values = families[family][spec.component]
        cache[key] = [float("nan")] * start + values
    ranges = (
        [(c.high, c.low, c.close) for c in candles]
        if any(isinstance(spec, ATRIndicator) for spec in specs)
        else None
    )
    return Context(prices, cache, ranges)


def evaluate_operand(operand: Operand, index: int, context: Context) -> float:
    if isinstance(operand, Price):
        return context.prices[index]
    if isinstance(operand, INDICATOR_TYPES):
        values = context.indicators.get(indicator_key(operand))
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
