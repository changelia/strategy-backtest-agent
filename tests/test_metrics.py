from datetime import UTC, datetime

import pytest

from strategy_backtest_agent.metrics import max_drawdown, profit_factor, summarize
from strategy_backtest_agent.models import Trade


def trade(pnl: float) -> Trade:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    return Trade(
        entry_time=now,
        exit_time=now,
        entry_price=100,
        exit_price=100 + pnl,
        quantity=1,
        pnl=pnl,
        pnl_percent=pnl,
    )


def test_drawdown() -> None:
    assert max_drawdown([100, 120, 90, 110, 60, 130]) == -50
    assert max_drawdown([]) == 0
    assert max_drawdown([0, 0]) == 0
    assert max_drawdown([100, 0]) == -100
    with pytest.raises(ValueError):
        max_drawdown([-1])


@pytest.mark.parametrize(
    "pnls, expected", [([], None), ([10], None), ([0], None), ([-10], 0), ([30, -10, 0], 3)]
)
def test_profit_factor(pnls: list[float], expected: float | None) -> None:
    assert profit_factor([trade(pnl) for pnl in pnls]) == expected


def test_counts_breakeven_and_return() -> None:
    result = summarize(100, 120, [trade(30), trade(-10), trade(0)], [100, 120], None)
    assert result.total_return_percent == pytest.approx(20)
    assert result.total_trades == 3
    assert result.winning_trades == result.losing_trades == 1
    assert result.win_rate == pytest.approx(100 / 3)
    with pytest.raises(ValueError):
        summarize(0, 0, [], [], None)
