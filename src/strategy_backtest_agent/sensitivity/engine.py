"""One shared history fetch, Train-only cache and independent variant portfolios."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import prepare_history
from strategy_backtest_agent.market_data import MarketDataProvider
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import dependencies, prepare_context, warmup_count
from strategy_backtest_agent.rules.history import fetch_history
from strategy_backtest_agent.sensitivity.analysis import describe_grid
from strategy_backtest_agent.sensitivity.grid import expand_grid
from strategy_backtest_agent.sensitivity.models import (
    WARNINGS,
    SensitivityConfig,
    SensitivityReport,
    VariantResult,
)
from strategy_backtest_agent.validation.engine import chronological_split
from strategy_backtest_agent.validation.models import SegmentResult


def run_sensitivity(
    candles: Sequence[Candle],
    config: SensitivityConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> SensitivityReport:
    config = SensitivityConfig.model_validate(config.model_dump(warnings=False))
    parameters, variants = expand_grid(config.base_strategy, config.parameters)
    rules = [variant.strategy for variant in variants]
    resolved, boundary, shared = prepare_history(
        candles, config, rules, evaluation_end=evaluation_end, data_source=data_source
    )
    cut, split = chronological_split(candles, boundary, config.train_ratio, config.timeframe)
    train_candles = candles[:cut]
    # Test OHLC values are never supplied to indicator functions or the backtester.
    cache = prepare_context(train_candles, set().union(*(dependencies(rule) for rule in rules)))
    results = []
    for variant in variants:
        result = run_backtest(
            train_candles,
            config.to_backtest_config(),
            variant.strategy,
            evaluation_start=boundary,
            context=cache,
        )
        benchmark = result.buy_and_hold_return_percent
        results.append(
            VariantResult(
                variant_id=variant.id,
                observation="no_neighbors",
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
    summary, neighbors, series, matrix = describe_grid(parameters, variants, results)
    return SensitivityReport(
        configuration=SensitivityConfig.model_validate(resolved.model_dump()),
        shared_data=shared,
        split=split,
        parameters=parameters,
        variants=variants,
        results=results,
        summary=summary,
        neighbors=neighbors,
        ordered_series=series,
        matrix=matrix,
        methodology_warnings=list(WARNINGS),
    )


async def fetch_and_analyze(
    provider: MarketDataProvider, config: SensitivityConfig, *, data_source: str = "provided"
) -> SensitivityReport:
    config = SensitivityConfig.model_validate(config.model_dump(warnings=False))
    _, variants = expand_grid(config.base_strategy, config.parameters)
    required = max(warmup_count(variant.strategy) for variant in variants)
    end = config.evaluation_end or datetime.now(UTC)
    candles, _ = await fetch_history(
        provider,
        config.symbol,
        config.timeframe,
        end - timedelta(days=config.period_days),
        end,
        required,
    )
    return run_sensitivity(candles, config, evaluation_end=end, data_source=data_source)
