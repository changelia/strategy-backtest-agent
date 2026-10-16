"""Shared causal indicators; chronological segments with fresh isolated portfolios."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import prepare_shared_history, required_warmup
from strategy_backtest_agent.market_data import MarketDataProvider
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.history import fetch_history, interval_duration
from strategy_backtest_agent.validation.models import (
    WARNINGS,
    ChronologicalSplit,
    SegmentResult,
    StrategyValidationResult,
    ValidationConfig,
    ValidationReport,
    train_count,
)


def chronological_split(
    candles: Sequence[Candle], boundary: int, ratio: float, timeframe: str
) -> tuple[int, ChronologicalSplit]:
    """Shared v0.5.0 completed-candle split policy, including execution minimums."""
    count = len(candles) - boundary
    train_size = train_count(count, ratio)
    if min(train_size, count - train_size) < 2:
        raise ValueError("insufficient evaluation history: each segment needs at least 2 candles")
    cut = boundary + train_size
    duration = interval_duration(timeframe)
    split = ChronologicalSplit(
        train_ratio=ratio,
        train_start=candles[boundary].timestamp,
        train_end=candles[cut].timestamp,
        test_start=candles[cut].timestamp,
        test_end=candles[-1].timestamp + duration,
        train_candle_count=train_size,
        test_candle_count=count - train_size,
    )
    return cut, split


def run_validation(
    candles: Sequence[Candle],
    config: ValidationConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> ValidationReport:
    """Split completed evaluation candles; never carry signals or positions across the split.

    Cached RSI/SMA/EMA values are causal prefixes. Train receives only its history
    prefix and truncated context; Test retains preceding history for indicators only.
    Each backtest ignores signals before its evaluation_start and liquidates at its
    own final close. At least two evaluation candles per segment allow next-open execution.
    """
    config = ValidationConfig.model_validate(config.model_dump(warnings=False))
    resolved, boundary, rules, context, shared = prepare_shared_history(
        candles, config, evaluation_end=evaluation_end, data_source=data_source
    )
    cut, split = chronological_split(candles, boundary, config.train_ratio, config.timeframe)
    train_context = context.prefix(cut)
    portfolio = config.to_backtest_config()
    rows = []
    for named, rule in zip(config.strategies, rules, strict=True):
        segments = []
        for source, start_index, cache, start, end in (
            (candles[:cut], boundary, train_context, split.train_start, split.train_end),
            (candles, cut, context, split.test_start, split.test_end),
        ):
            result = run_backtest(
                source, portfolio, rule, evaluation_start=start_index, context=cache
            )
            benchmark = result.buy_and_hold_return_percent
            segments.append(
                SegmentResult(
                    start=start,
                    end=end,
                    candle_count=len(source) - start_index,
                    warmup_candles=start_index,
                    result=result,
                    excess_return_pp=result.total_return_percent - benchmark
                    if benchmark is not None
                    else None,
                )
            )
        train, test = segments
        rows.append(
            StrategyValidationResult(
                id=named.id,
                name=named.name,
                strategy=rule,
                train=train,
                test=test,
                return_gap_pp=test.result.total_return_percent - train.result.total_return_percent,
            )
        )
    return ValidationReport(
        configuration=ValidationConfig.model_validate(resolved.model_dump()),
        shared_data=shared,
        split=split,
        results=rows,
        methodology_warnings=list(WARNINGS),
    )


async def fetch_and_validate(
    provider: MarketDataProvider,
    config: ValidationConfig,
    *,
    data_source: str = "provided",
) -> ValidationReport:
    """One shared provider fetch, including maximum warm-up across all strategies."""
    config = ValidationConfig.model_validate(config.model_dump(warnings=False))
    end = config.evaluation_end or datetime.now(UTC)
    candles, _ = await fetch_history(
        provider,
        config.symbol,
        config.timeframe,
        end - timedelta(days=config.period_days),
        end,
        required_warmup(config),
    )
    return run_validation(candles, config, evaluation_end=end, data_source=data_source)
