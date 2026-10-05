"""Long-only execution on next-candle opens, with no provider dependencies."""

from collections.abc import Sequence

from strategy_backtest_agent.metrics import summarize
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle, Trade
from strategy_backtest_agent.strategy import rsi_signals


def run_backtest(candles: Sequence[Candle], config: BacktestConfig) -> BacktestResult:
    """Execute candle N signals at N+1 open and liquidate at the final close."""
    if any(a.timestamp >= b.timestamp for a, b in zip(candles, candles[1:], strict=False)):
        raise ValueError("candles must have unique, strictly increasing timestamps")
    signals = rsi_signals(candles, config)
    cash = config.initial_balance
    fee = config.trading_fee
    quantity = 0.0
    cost = 0.0
    entry: Candle | None = None
    trades: list[Trade] = []
    equity = [cash]

    def close_position(candle: Candle, price: float) -> None:
        nonlocal cash, quantity, entry
        assert entry is not None
        cash = quantity * price * (1 - fee)
        pnl = cash - cost
        trades.append(
            Trade(
                entry_time=entry.timestamp,
                entry_price=entry.open,
                exit_time=candle.timestamp,
                exit_price=price,
                quantity=quantity,
                pnl=pnl,
                pnl_percent=pnl / cost * 100,
            )
        )
        quantity = 0.0
        entry = None

    for i, candle in enumerate(candles):
        signal = signals[i - 1] if i > 0 else 0
        if quantity > 0 and signal == -1:
            close_position(candle, candle.open)
        elif quantity == 0 and signal == 1 and cash > 0:
            cost = cash
            quantity = cash / (candle.open * (1 + fee))
            cash = 0.0
            entry = candle
        # Sample portfolio value at each open and close; fees apply only on execution.
        equity.append(cash + quantity * candle.open)
        if i == len(candles) - 1 and quantity > 0:
            close_position(candle, candle.close)
        equity.append(cash + quantity * candle.close)
    benchmark = None
    if candles:
        benchmark = (candles[-1].close * (1 - fee) / (candles[0].open * (1 + fee)) - 1) * 100
    return summarize(config.initial_balance, cash, trades, equity, benchmark)
