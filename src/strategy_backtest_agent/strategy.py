"""RSI signals, independent of execution and market-data providers."""

from collections.abc import Sequence

import pandas as pd

from strategy_backtest_agent.indicators import rsi
from strategy_backtest_agent.models import BacktestConfig, Candle


def rsi_signals(candles: Sequence[Candle], config: BacktestConfig) -> list[int]:
    """Return 1 for buy, -1 for sell, and 0 for hold on each completed candle."""
    values = rsi(pd.Series([c.close for c in candles], dtype=float), config.rsi_period)
    return [1 if v < config.entry_rsi else -1 if v > config.exit_rsi else 0 for v in values]
