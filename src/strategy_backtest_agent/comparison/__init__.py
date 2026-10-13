"""Independent backtests over shared historical candles and indicators."""

from strategy_backtest_agent.comparison.models import (
    ComparisonConfig,
    ComparisonResult,
    NamedStrategy,
)

__all__ = ["ComparisonConfig", "ComparisonResult", "NamedStrategy"]
