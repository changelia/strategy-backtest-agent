"""Long-only execution on next-candle opens, with no provider dependencies."""

from collections.abc import Sequence

from strategy_backtest_agent.metrics import summarize
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle, Trade
from strategy_backtest_agent.rules.evaluator import (
    Context,
    dependencies,
    evaluate_rule,
    prepare_indicators,
)
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.strategy import legacy_rules, rsi_signals


def run_backtest(
    candles: Sequence[Candle],
    config: BacktestConfig,
    strategy: RuleStrategy | None = None,
    *,
    evaluation_start: int = 0,
    context: Context | None = None,
) -> BacktestResult:
    """Execute candle N signals at N+1 open and liquidate at the final close."""
    if any(a.timestamp >= b.timestamp for a, b in zip(candles, candles[1:], strict=False)):
        raise ValueError("candles must have unique, strictly increasing timestamps")
    if not 0 <= evaluation_start <= len(candles):
        raise ValueError("invalid evaluation_start")
    if strategy is None:
        strategy = legacy_rules(config)
    if strategy is not None:
        strategy = RuleStrategy.model_validate(strategy.model_dump(warnings=False))
    if context is not None:
        if strategy is None:
            raise ValueError("a prepared context requires a DSL strategy")
        if context.prices != [c.close for c in candles]:
            raise ValueError("prepared context does not match candle closes")
        if any(
            key not in context.indicators or len(context.indicators[key]) != len(candles)
            for key in dependencies(strategy)
        ):
            raise ValueError("prepared context has missing or incomplete indicator series")
    elif strategy is not None:
        context = prepare_indicators(candles, strategy)
    signals = rsi_signals(candles, config) if strategy is None else []
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

    for i in range(evaluation_start, len(candles)):
        candle = candles[i]
        signal = 0
        if i > evaluation_start:
            if strategy is not None and context is not None:
                rule = strategy.exit if quantity > 0 else strategy.entry
                if evaluate_rule(rule, i - 1, context):
                    signal = -1 if quantity > 0 else 1
            else:
                signal = signals[i - 1]
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
    if evaluation_start < len(candles):
        benchmark = (
            candles[-1].close * (1 - fee) / (candles[evaluation_start].open * (1 + fee)) - 1
        ) * 100
    return summarize(config.initial_balance, cash, trades, equity, benchmark)
