"""One fetch and anchored cache, independent Train-only cost scenario portfolios."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import prepare_history
from strategy_backtest_agent.costs.models import (
    WARNINGS,
    CostScenarioConfig,
    CostScenarioReport,
    CostScenarioResult,
)
from strategy_backtest_agent.market_data import MarketDataProvider
from strategy_backtest_agent.models import BacktestConfig, Candle
from strategy_backtest_agent.rules.evaluator import dependencies, warmup_count
from strategy_backtest_agent.rules.history import fetch_history
from strategy_backtest_agent.sensitivity.cache import prepare_train_context
from strategy_backtest_agent.sensitivity.models import INITIALIZATION_POLICY, SensitivitySharedData
from strategy_backtest_agent.validation.engine import chronological_split
from strategy_backtest_agent.validation.models import SegmentResult


def run_cost_scenarios(
    candles: Sequence[Candle],
    config: CostScenarioConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> CostScenarioReport:
    config = CostScenarioConfig.model_validate(config.model_dump(warnings=False))
    resolved, boundary, shared = prepare_history(
        candles, config, [config.strategy], evaluation_end=evaluation_end, data_source=data_source
    )
    cut, split = chronological_split(candles, boundary, config.train_ratio, config.timeframe)
    train = candles[:cut]
    context, anchors = prepare_train_context(train, boundary, dependencies(config.strategy))
    results = []
    baseline_return = None
    for scenario in config.scenarios:
        execution = scenario.execution_config(config.fee)
        portfolio = BacktestConfig.model_validate(
            {
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "initial_balance": config.initial_balance,
                "execution": execution,
            }
        )
        result = run_backtest(
            train, portfolio, config.strategy, evaluation_start=boundary, context=context
        )
        if baseline_return is None:
            baseline_return = result.total_return_percent
        benchmark = result.buy_and_hold_return_percent
        results.append(
            CostScenarioResult(
                id=scenario.id,
                name=scenario.name,
                execution=execution,
                return_difference_pp=result.total_return_percent - baseline_return,
                train=SegmentResult(
                    start=split.train_start,
                    end=split.train_end,
                    candle_count=split.train_candle_count,
                    warmup_candles=boundary,
                    result=result,
                    excess_return_pp=result.total_return_percent - benchmark
                    if benchmark is not None
                    else None,
                ),
            )
        )
    return CostScenarioReport(
        configuration=CostScenarioConfig.model_validate(resolved.model_dump()),
        shared_data=SensitivitySharedData.model_validate(
            {
                **shared.model_dump(),
                "warmup_policy": INITIALIZATION_POLICY,
                "indicator_initializations": anchors,
            }
        ),
        split=split,
        baseline_id=config.scenarios[0].id,
        results=results,
        methodology_warnings=list(WARNINGS),
    )


async def fetch_and_run_costs(
    provider: MarketDataProvider, config: CostScenarioConfig, *, data_source: str = "provided"
) -> CostScenarioReport:
    config = CostScenarioConfig.model_validate(config.model_dump(warnings=False))
    end = config.evaluation_end or datetime.now(UTC)
    candles, _ = await fetch_history(
        provider,
        config.symbol,
        config.timeframe,
        end - timedelta(days=config.period_days),
        end,
        warmup_count(config.strategy),
    )
    return run_cost_scenarios(candles, config, evaluation_end=end, data_source=data_source)
