"""One history fetch and causal cache; existing backtester for every isolated segment."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from statistics import median

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import (
    normalized_strategies,
    prepare_history,
    required_warmup,
)
from strategy_backtest_agent.market_data import MarketDataProvider
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import dependencies
from strategy_backtest_agent.rules.history import fetch_history, interval_duration
from strategy_backtest_agent.sensitivity.cache import prepare_train_context
from strategy_backtest_agent.sensitivity.models import SensitivitySharedData
from strategy_backtest_agent.validation.models import SegmentResult
from strategy_backtest_agent.walk_forward.models import (
    WARNINGS,
    FoldStrategyResult,
    IndexPoint,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardReport,
    WalkForwardSummary,
)


def generate_folds(
    candles: Sequence[Candle], boundary: int, config: WalkForwardConfig
) -> list[tuple[int, int, int, WalkForwardFold]]:
    train, test, step = config.windows.counts(config.timeframe)
    duration = interval_duration(config.timeframe)
    folds: list[tuple[int, int, int, WalkForwardFold]] = []
    offset = 0
    while boundary + offset + train + test <= len(candles):
        start = boundary + offset if config.windows.mode == "rolling" else boundary
        cut = boundary + offset + train
        end = cut + test
        folds.append(
            (
                start,
                cut,
                end,
                WalkForwardFold(
                    id=f"fold-{len(folds) + 1:03d}",
                    train_start=candles[start].timestamp,
                    train_end=candles[cut].timestamp,
                    test_start=candles[cut].timestamp,
                    test_end=candles[end - 1].timestamp + duration,
                    train_candle_count=cut - start,
                    test_candle_count=test,
                ),
            )
        )
        offset += step
    if len(folds) < 2:
        raise ValueError("walk-forward requires at least two complete folds")
    if len(folds) > config.windows.max_folds:
        raise ValueError("complete fold count exceeds max_folds")
    return folds


def summarize_tests(rows: list[FoldStrategyResult], stitch: bool) -> WalkForwardSummary:
    returns = [row.test.result.total_return_percent for row in rows]
    excess = [row.test.excess_return_pp for row in rows if row.test.excess_return_pp is not None]
    positive = sum(value > 0 for value in returns)
    points = None
    if stitch:
        points = [IndexPoint(time=rows[0].test.start, value=100.0)]
        for row in rows:
            points.append(
                IndexPoint(
                    time=row.test.end,
                    value=points[-1].value
                    * (row.test.result.final_balance / row.test.result.initial_balance),
                )
            )
    return WalkForwardSummary(
        strategy_id=rows[0].strategy_id,
        fold_count=len(rows),
        total_test_trades=sum(row.test.result.total_trades for row in rows),
        positive_test_folds=positive,
        positive_test_fraction=positive / len(rows),
        median_test_return_percent=median(returns),
        minimum_test_return_percent=min(returns),
        maximum_test_return_percent=max(returns),
        median_test_max_drawdown_percent=median(
            row.test.result.max_drawdown_percent for row in rows
        ),
        median_test_excess_return_pp=median(excess) if excess else None,
        outperforming_test_folds=sum(value > 0 for value in excess),
        stitched_oos_index=points,
    )


def run_walk_forward(
    candles: Sequence[Candle],
    config: WalkForwardConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> WalkForwardReport:
    config = WalkForwardConfig.model_validate(config.model_dump(warnings=False))
    rules = normalized_strategies(config)
    resolved, boundary, shared = prepare_history(
        candles, config, rules, evaluation_end=evaluation_end, data_source=data_source
    )
    folds = generate_folds(candles, boundary, config)
    keys = set().union(*(dependencies(rule) for rule in rules))
    context, seeds = prepare_train_context(candles, boundary, keys)
    data = SensitivitySharedData.model_validate(
        {
            **shared.model_dump(),
            "warmup_policy": (
                "indicator-local seeds before first evaluation open; causal continuation"
            ),
            "indicator_initializations": seeds,
        }
    )
    results = []
    portfolio = config.to_backtest_config()
    for start, cut, end, fold in folds:
        for named, rule in zip(config.strategies, rules, strict=True):
            segments = []
            for first, stop, left, right in (
                (start, cut, fold.train_start, fold.train_end),
                (cut, end, fold.test_start, fold.test_end),
            ):
                prefix = context.prefix(stop)
                result = run_backtest(
                    candles[:stop], portfolio, rule, evaluation_start=first, context=prefix
                )
                benchmark = result.buy_and_hold_return_percent
                segments.append(
                    SegmentResult(
                        start=left,
                        end=right,
                        candle_count=stop - first,
                        warmup_candles=first,
                        result=result,
                        excess_return_pp=(result.total_return_percent - benchmark)
                        if benchmark is not None
                        else None,
                    )
                )
            results.append(
                FoldStrategyResult(
                    fold_id=fold.id,
                    strategy_id=named.id,
                    name=named.name,
                    strategy=rule,
                    train=segments[0],
                    test=segments[1],
                )
            )
    return WalkForwardReport(
        configuration=WalkForwardConfig.model_validate(resolved.model_dump()),
        shared_data=data,
        folds=[item[3] for item in folds],
        unused_trailing_candles=len(candles) - folds[-1][2],
        results=results,
        summaries=[
            summarize_tests(
                [row for row in results if row.strategy_id == named.id], config.stitch_oos
            )
            for named in config.strategies
        ],
        methodology_warnings=list(WARNINGS),
    )


async def fetch_and_walk_forward(
    provider: MarketDataProvider, config: WalkForwardConfig, *, data_source: str = "provided"
) -> WalkForwardReport:
    config = WalkForwardConfig.model_validate(config.model_dump(warnings=False))
    end = config.evaluation_end or datetime.now(UTC)
    candles, _ = await fetch_history(
        provider,
        config.symbol,
        config.timeframe,
        end - timedelta(days=config.period_days),
        end,
        required_warmup(config),
    )
    return run_walk_forward(candles, config, evaluation_end=end, data_source=data_source)
