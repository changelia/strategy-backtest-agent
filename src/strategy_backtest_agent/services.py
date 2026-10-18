"""Shared high-level backtest orchestration and legacy CLI JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataProvider
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle
from strategy_backtest_agent.rules.evaluator import dependencies, prepare_context, warmup_count
from strategy_backtest_agent.rules.history import fetch_rule_history, interval_duration
from strategy_backtest_agent.rules.indicator_specs import (
    indicator_from_key,
    initialization_profiles,
)
from strategy_backtest_agent.rules.models import Indicator, IndicatorInitialization, RuleStrategy


@dataclass(frozen=True)
class BacktestExecution:
    config: BacktestConfig
    days: int
    demo: bool
    data_source: str
    requested_start: datetime
    requested_end: datetime
    candles: list[Candle]
    evaluation_start: int
    strategy: RuleStrategy | None
    result: BacktestResult
    initializations: list[IndicatorInitialization]

    @property
    def evaluation_candles(self) -> list[Candle]:
        return self.candles[self.evaluation_start :]


async def execute_backtest(
    config: BacktestConfig,
    days: int,
    *,
    demo: bool = False,
    provider: MarketDataProvider | None = None,
    strategy: RuleStrategy | None = None,
    evaluation_end: datetime | None = None,
) -> BacktestExecution:
    """Run the existing backtester through a shared live/demo orchestration path."""
    if type(days) is not int or days <= 0:
        raise ValueError("days must be a positive integer")
    end = evaluation_end or (datetime(2024, 7, 1, tzinfo=UTC) if demo else datetime.now(UTC))
    if end.tzinfo is None:
        raise ValueError("evaluation_end must be timezone-aware")
    end = end.astimezone(UTC)
    if demo and evaluation_end is not None and end != datetime(2024, 7, 1, tzinfo=UTC):
        raise ValueError("demo data ends at 2024-07-01T00:00:00Z")
    start = end - timedelta(days=days)
    boundary = 0
    initializations: list[IndicatorInitialization] = []
    if strategy is not None:
        if demo:
            duration = interval_duration(config.timeframe)
            required = warmup_count(strategy)
            synthetic_end = datetime(2024, 7, 1, tzinfo=UTC)
            if evaluation_end is not None and end != synthetic_end:
                raise ValueError("demo data ends at 2024-07-01T00:00:00Z")
            evaluation_count = days * 86400 // int(duration.total_seconds())
            history_days = days + (required * duration.total_seconds() + 86399) // 86400
            all_candles = demo_candles(config.timeframe, int(history_days))
            candles = all_candles[-(evaluation_count + required) :]
            boundary = required
            if len(candles) != evaluation_count + required:
                raise ValueError("synthetic demo could not satisfy indicator warm-up")
        else:
            candles, boundary = await fetch_rule_history(
                provider if provider is not None else BinanceMarketData(),
                config.symbol,
                config.timeframe,
                start,
                end,
                strategy,
            )
    elif demo:
        candles = demo_candles(config.timeframe, days)
    else:
        data_provider = provider if provider is not None else BinanceMarketData()
        candles = await data_provider.fetch_candles(config.symbol, config.timeframe, start, end)
    if strategy is None and len(candles) <= config.rsi_period:
        raise ValueError("not enough completed candles to calculate RSI; increase days")
    context = None
    if (
        strategy is not None
        and boundary
        and any(
            not isinstance(indicator_from_key(*key), Indicator) for key in dependencies(strategy)
        )
    ):
        context = prepare_context(candles, dependencies(strategy), evaluation_start=boundary)
        initializations = initialization_profiles(
            candles, boundary, dependencies(strategy), local_seeds=False
        )
    result = run_backtest(candles, config, strategy, evaluation_start=boundary, context=context)
    return BacktestExecution(
        config=config,
        days=days,
        demo=demo,
        data_source=(
            "synthetic_demo"
            if demo
            else "custom"
            if provider is not None and type(provider) is not BinanceMarketData
            else "binance"
        ),
        requested_start=start,
        requested_end=end,
        candles=candles,
        evaluation_start=boundary,
        strategy=strategy,
        result=result,
        initializations=initializations,
    )


def backtest_payload(execution: BacktestExecution) -> dict[str, Any]:
    """Build the exact existing CLI research JSON shape for reports and API clients."""
    config, result = execution.config, execution.result
    candles = execution.evaluation_candles
    payload: dict[str, Any] = {
        "symbol": config.symbol,
        "timeframe": config.timeframe,
        "period_days": execution.days,
        "data_source": execution.data_source,
        "candle_count": len(candles),
        "start_time": candles[0].timestamp.isoformat().replace("+00:00", "Z"),
        "end_time": candles[-1].timestamp.isoformat().replace("+00:00", "Z"),
        "strategy": {
            "name": "RSI",
            "rsi_period": config.rsi_period,
            "entry_rsi": config.entry_rsi,
            "exit_rsi": config.exit_rsi,
            "fee": config.trading_fee,
        },
        **result.model_dump(mode="json"),
    }
    if execution.strategy is not None:
        keys = sorted(dependencies(execution.strategy))
        payload["strategy"] = execution.strategy.model_dump(mode="json")
        payload["trading_fee"] = config.trading_fee
        payload["indicator_configuration"] = [
            (
                {"name": spec.name, "period": spec.period}
                if isinstance(spec, Indicator)
                else spec.model_dump(mode="json")
            )
            for key in keys
            for spec in [indicator_from_key(*key)]
        ]
        payload["evaluation_period"] = {
            "requested_start": execution.requested_start.isoformat().replace("+00:00", "Z"),
            "requested_end": execution.requested_end.isoformat().replace("+00:00", "Z"),
            "warmup_candles": execution.evaluation_start,
            "required_warmup_candles": warmup_count(execution.strategy),
            "ema_policy": "first-close seed, five spans of prior closes",
        }
        if execution.initializations:
            payload["indicator_initializations"] = [
                item.model_dump(mode="json") for item in execution.initializations
            ]
    return payload


def backtest_json(execution: BacktestExecution) -> bytes:
    return (json.dumps(backtest_payload(execution), allow_nan=False) + "\n").encode("utf-8")
