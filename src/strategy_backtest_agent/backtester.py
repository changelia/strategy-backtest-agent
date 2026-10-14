"""Long-only execution on next-candle opens, with no provider dependencies."""

import math
from collections.abc import Sequence

from strategy_backtest_agent.execution import EXECUTION_WARNINGS, quote_execution, total_costs
from strategy_backtest_agent.metrics import summarize
from strategy_backtest_agent.models import (
    BacktestConfig,
    BacktestResult,
    Candle,
    ExecutionFill,
    Trade,
)
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
    config = BacktestConfig.model_validate(config.model_dump(warnings=False))
    execution = config.execution_config()
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
    fee = execution.fee_rate
    quantity = 0.0
    cost = 0.0
    entry: Candle | None = None
    entry_fill: ExecutionFill | None = None
    trades: list[Trade] = []
    equity = [cash]

    def mark_equity(price: float) -> None:
        value = cash + quantity * price
        if not math.isfinite(value) or value < 0:
            raise ValueError(
                "portfolio equity is not finite/nonnegative at current numeric precision"
            )
        equity.append(value)

    def close_position(candle: Candle, price: float, *, forced: bool = False) -> None:
        nonlocal cash, quantity, entry, entry_fill
        assert entry is not None and entry_fill is not None
        exit_fill = quote_execution(price, "sell", execution).fill(quantity, forced=forced)
        cash = quantity * exit_fill.fill_price * (1 - fee)
        pnl = cash - cost
        trades.append(
            Trade(
                entry_time=entry.timestamp,
                entry_price=entry_fill.fill_price,
                exit_time=candle.timestamp,
                exit_price=exit_fill.fill_price,
                quantity=quantity,
                pnl=pnl,
                pnl_percent=pnl / cost * 100,
                entry_execution=entry_fill,
                exit_execution=exit_fill,
            )
        )
        quantity = 0.0
        entry = None
        entry_fill = None

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
            buy = quote_execution(candle.open, "buy", execution)
            quantity = cash / (buy.fill_price * (1 + fee))
            entry_fill = buy.fill(quantity)
            cash = 0.0
            entry = candle
        # Sample portfolio value at each open and close; fees apply only on execution.
        mark_equity(candle.open)
        if i == len(candles) - 1 and quantity > 0:
            close_position(candle, candle.close, forced=True)
        mark_equity(candle.close)
    benchmark = None
    benchmark_costs = None
    if evaluation_start < len(candles):
        buy = quote_execution(candles[evaluation_start].open, "buy", execution)
        sell = quote_execution(candles[-1].close, "sell", execution)
        benchmark = (sell.fill_price * (1 - fee) / (buy.fill_price * (1 + fee)) - 1) * 100
        benchmark_quantity = config.initial_balance / (buy.fill_price * (1 + fee))
        benchmark_costs = total_costs([buy.fill(benchmark_quantity), sell.fill(benchmark_quantity)])
    result = summarize(config.initial_balance, cash, trades, equity, benchmark)
    fills = [
        fill
        for trade in trades
        for fill in (trade.entry_execution, trade.exit_execution)
        if fill is not None
    ]
    return BacktestResult.model_validate(
        {
            **result.model_dump(),
            "execution": execution,
            "costs": total_costs(fills),
            "benchmark_costs": benchmark_costs,
            "execution_warnings": list(EXECUTION_WARNINGS),
        }
    )
