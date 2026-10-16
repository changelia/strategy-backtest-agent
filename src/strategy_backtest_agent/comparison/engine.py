"""Shared history and indicator preparation; isolated deterministic portfolios."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.models import (
    ComparisonConfig,
    ComparisonResult,
    MarketConfig,
    RankingCriterion,
    SharedConfig,
    SharedData,
    StrategyResult,
)
from strategy_backtest_agent.market_data import MarketDataProvider
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import (
    Context,
    dependencies,
    prepare_context,
    warmup_count,
)
from strategy_backtest_agent.rules.history import fetch_history, interval_duration, validate_history
from strategy_backtest_agent.rules.indicator_specs import (
    indicator_from_key,
    initialization_profiles,
)
from strategy_backtest_agent.rules.models import Indicator, RuleStrategy


def normalized_strategies(config: SharedConfig) -> list[RuleStrategy]:
    return [item.to_rules() for item in config.strategies]


def required_warmup(config: SharedConfig) -> int:
    return max(map(warmup_count, normalized_strategies(config)))


def rank_results(results: Sequence[StrategyResult], criterion: RankingCriterion) -> list[str]:
    """Descending selected metric, nulls last, ties by case-sensitive strategy ID."""

    def key(item: StrategyResult) -> tuple[bool, float, str]:
        metrics = {
            "total_return": item.result.total_return_percent,
            "excess_return": item.excess_return_pp,
            "max_drawdown": item.result.max_drawdown_percent,
            "profit_factor": item.result.profit_factor,
        }
        value = metrics[criterion]
        return value is None, -value if value is not None else 0, item.id

    return [item.id for item in sorted(results, key=key)]


def prepare_history(
    candles: Sequence[Candle],
    config: MarketConfig,
    rules: list[RuleStrategy],
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> tuple[MarketConfig, int, SharedData]:
    """Validate shared history and record metadata without preparing indicator values."""
    if not candles:
        raise ValueError("requires completed historical candles")
    duration = interval_duration(config.timeframe)
    end = evaluation_end or config.evaluation_end or (candles[-1].timestamp + duration)
    if end.tzinfo is None:
        raise ValueError("evaluation_end must be timezone-aware")
    end = end.astimezone(UTC)
    if config.evaluation_end is not None and config.evaluation_end != end:
        raise ValueError("evaluation_end conflicts with configured boundary")
    resolved_config = type(config).model_validate({**config.model_dump(), "evaluation_end": end})
    start = end - timedelta(days=config.period_days)
    rules = [RuleStrategy.model_validate(rule.model_dump()) for rule in rules]
    required = max(map(warmup_count, rules))
    boundary = validate_history(candles, config.timeframe, start, end, required)
    keys = set().union(*(dependencies(rule) for rule in rules))
    # Hash all initialization and evaluation data so revisions to provider history are detectable.
    digest = hashlib.sha256()
    for candle in candles:
        encoded = json.dumps(
            candle.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        digest.update(encoded + b"\n")
    shared = SharedData(
        source=data_source,
        evaluation_start=start,
        evaluation_end=end,
        first_candle_open=candles[boundary].timestamp,
        last_candle_open=candles[-1].timestamp,
        candle_count=len(candles) - boundary,
        history_candle_count=len(candles),
        warmup_candles=boundary,
        required_warmup_candles=required,
        indicators=[indicator_from_key(name, period) for name, period in sorted(keys)],
        candles_sha256=digest.hexdigest(),
    )
    specs = [indicator_from_key(*key) for key in sorted(keys)]
    if any(not isinstance(spec, Indicator) for spec in specs):
        anchors = initialization_profiles(candles, boundary, keys, local_seeds=False)
        shared = shared.model_copy(
            update={
                "indicator_initializations": anchors,
                "warmup_policy": "advanced indicator-local v1 seeds; legacy shared close seeds",
            }
        )
    return resolved_config, boundary, shared


def prepare_shared_history(
    candles: Sequence[Candle],
    config: SharedConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> tuple[MarketConfig, int, list[RuleStrategy], Context, SharedData]:
    """Prepare the existing comparison/validation cache and full-history metadata."""
    rules = normalized_strategies(config)
    resolved, boundary, shared = prepare_history(
        candles, config, rules, evaluation_end=evaluation_end, data_source=data_source
    )
    keys = set().union(*(dependencies(rule) for rule in rules))
    return (
        resolved,
        boundary,
        rules,
        prepare_context(candles, keys, evaluation_start=boundary),
        shared,
    )


def run_comparison(
    candles: Sequence[Candle],
    config: ComparisonConfig,
    *,
    evaluation_end: datetime | None = None,
    data_source: str = "provided",
) -> ComparisonResult:
    """Compare directly supplied full history without providers or OpenAI.

    Without a configured end, derive it from the last supplied completed candle.
    The caller supplies the requested period and sufficient preceding warm-up.
    """
    config = ComparisonConfig.model_validate(config.model_dump(warnings=False))
    if not candles:
        raise ValueError("comparison requires completed historical candles")
    resolved_config, boundary, rules, context, shared = prepare_shared_history(
        candles, config, evaluation_end=evaluation_end, data_source=data_source
    )
    portfolio = config.to_backtest_config()
    results: list[StrategyResult] = []
    for named, rule in zip(config.strategies, rules, strict=True):
        result = run_backtest(candles, portfolio, rule, evaluation_start=boundary, context=context)
        benchmark = result.buy_and_hold_return_percent
        if results and benchmark != results[0].result.buy_and_hold_return_percent:
            raise ValueError("strategies must share an identical buy-and-hold benchmark")
        results.append(
            StrategyResult(
                id=named.id,
                name=named.name,
                strategy=rule,
                result=result,
                excess_return_pp=(result.total_return_percent - benchmark)
                if benchmark is not None
                else None,
            )
        )
    return ComparisonResult(
        configuration=ComparisonConfig.model_validate(resolved_config.model_dump()),
        shared_data=shared,
        buy_and_hold_return_percent=results[0].result.buy_and_hold_return_percent,
        results=results,
        ranking_criterion=config.sort_by,
        ranking=rank_results(results, config.sort_by),
    )


async def fetch_and_compare(
    provider: MarketDataProvider,
    config: ComparisonConfig,
    *,
    data_source: str = "provided",
) -> ComparisonResult:
    """Fetch once; all strategies use one recorded UTC window and prepared cache."""
    config = ComparisonConfig.model_validate(config.model_dump(warnings=False))
    end = config.evaluation_end or datetime.now(UTC)
    start = end - timedelta(days=config.period_days)
    candles, _ = await fetch_history(
        provider,
        config.symbol,
        config.timeframe,
        start,
        end,
        required_warmup(config),
    )
    return run_comparison(candles, config, evaluation_end=end, data_source=data_source)
