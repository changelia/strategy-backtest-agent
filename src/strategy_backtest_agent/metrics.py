"""Portfolio and closed-trade metrics."""

from collections.abc import Sequence

from strategy_backtest_agent.models import BacktestResult, Trade


def max_drawdown(equity: Sequence[float]) -> float:
    """Return the largest peak-to-trough decline as a nonpositive percentage."""
    peak = 0.0
    worst = 0.0
    for value in equity:
        if value < 0:
            raise ValueError("equity cannot be negative")
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak - 1) * 100)
    return worst


def profit_factor(trades: Sequence[Trade]) -> float | None:
    """Return gross net-PnL gains / losses; no losses means undefined."""
    gains = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl < 0)
    return gains / losses if losses > 0 else None


def summarize(
    initial: float,
    final: float,
    trades: list[Trade],
    equity: Sequence[float],
    buy_and_hold: float | None,
) -> BacktestResult:
    """Build metrics from fee-inclusive balances and closed trades."""
    if initial <= 0:
        raise ValueError("initial balance must be positive")
    winners = sum(t.pnl > 0 for t in trades)
    return BacktestResult(
        initial_balance=initial,
        final_balance=final,
        total_return_percent=(final / initial - 1) * 100,
        buy_and_hold_return_percent=buy_and_hold,
        total_trades=len(trades),
        winning_trades=winners,
        losing_trades=sum(t.pnl < 0 for t in trades),
        win_rate=winners / len(trades) * 100 if trades else None,
        max_drawdown_percent=max_drawdown(equity),
        profit_factor=profit_factor(trades),
        trades=trades,
    )
