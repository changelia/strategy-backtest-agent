"""RSI signals, independent of execution and market-data providers."""

from collections.abc import Sequence

import pandas as pd

from strategy_backtest_agent.indicators import rsi
from strategy_backtest_agent.models import BacktestConfig, Candle
from strategy_backtest_agent.rules.models import RuleStrategy


def rsi_signals(candles: Sequence[Candle], config: BacktestConfig) -> list[int]:
    """Return 1 for buy, -1 for sell, and 0 for hold on each completed candle."""
    values = rsi(pd.Series([c.close for c in candles], dtype=float), config.rsi_period)
    return [1 if v < config.entry_rsi else -1 if v > config.exit_rsi else 0 for v in values]


def legacy_rules(config: BacktestConfig) -> "RuleStrategy | None":
    """Translate legacy RSI without altering initialization or historical limits."""
    if not 2 <= config.rsi_period <= 500:
        # The original public API allowed period 1 and unbounded positive periods.
        return None
    operand = {"type": "indicator", "name": "rsi", "period": config.rsi_period}
    return RuleStrategy.model_validate(
        {
            "entry": {
                "type": "comparison",
                "left": operand,
                "operator": "<",
                "right": {"type": "value", "value": config.entry_rsi},
            },
            "exit": {
                "type": "comparison",
                "left": operand,
                "operator": ">",
                "right": {"type": "value", "value": config.exit_rsi},
            },
        }
    )
