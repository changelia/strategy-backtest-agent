"""Internal consistency checks on supplied evidence, never backtest execution."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose
from typing import Any

from strategy_backtest_agent.comparison.engine import rank_results
from strategy_backtest_agent.comparison.models import ComparisonResult, SharedData
from strategy_backtest_agent.costs.models import CostScenarioReport
from strategy_backtest_agent.execution import quote_execution, total_costs
from strategy_backtest_agent.metrics import profit_factor
from strategy_backtest_agent.models import BacktestResult, ExecutionConfig, ExecutionFill
from strategy_backtest_agent.reports.inputs import CLIBacktest, ResearchInput
from strategy_backtest_agent.reports.models import EvidenceScope
from strategy_backtest_agent.rules.evaluator import dependencies
from strategy_backtest_agent.rules.history import interval_duration
from strategy_backtest_agent.rules.indicator_specs import (
    indicator_key,
    initialization_policy,
    input_fields,
    prior_candles,
)
from strategy_backtest_agent.rules.models import Indicator, RuleStrategy
from strategy_backtest_agent.sensitivity.analysis import describe_grid
from strategy_backtest_agent.sensitivity.grid import expand_grid
from strategy_backtest_agent.sensitivity.models import SensitivityReport
from strategy_backtest_agent.validation.models import SegmentResult, ValidationReport, train_count
from strategy_backtest_agent.walk_forward.engine import summarize_tests
from strategy_backtest_agent.walk_forward.models import WalkForwardReport

NET_POLICY = "net first evaluation open to final close under the same execution costs"


def require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise ValueError(f"{path}: {message}")


def equivalent(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        require(type(actual) is type(expected) and actual == expected, path, "inconsistent value")
    elif isinstance(expected, float | int):
        require(
            type(actual) in (int, float) and isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8),
            path,
            "inconsistent numerical relationship",
        )
    elif isinstance(expected, dict):
        require(
            isinstance(actual, dict) and actual.keys() == expected.keys(),
            path,
            "inconsistent fields",
        )
        for key, value in expected.items():
            equivalent(actual[key], value, f"{path}/{key}")
    elif isinstance(expected, list):
        require(
            isinstance(actual, list) and len(actual) == len(expected), path, "inconsistent list"
        )
        for index, (a, b) in enumerate(zip(actual, expected, strict=True)):
            equivalent(a, b, f"{path}/{index}")
    else:
        require(actual == expected, path, "inconsistent value")


@dataclass(frozen=True)
class Segment:
    scope: EvidenceScope
    path: str
    result: BacktestResult
    excess: float | None
    excess_path: str | None


def _raw_at(raw: dict[str, Any], path: str) -> Any:
    value: Any = raw
    for part in path.strip("/").split("/"):
        if part:
            value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def check_result(segment: Segment, raw: dict[str, Any], duration: timedelta) -> None:
    result, scope, path = segment.result, segment.scope, segment.path
    supplied = _raw_at(raw, path)
    required = set(BacktestResult.model_fields)
    require(
        isinstance(supplied, dict) and required <= supplied.keys(),
        path,
        "missing metrics/execution fields; supply complete v0.9 --json output",
    )
    require(result.initial_balance > 0 and result.final_balance >= 0, path, "invalid balances")
    equivalent(
        result.total_return_percent,
        (result.final_balance / result.initial_balance - 1) * 100,
        path + "/total_return_percent",
    )
    require(
        -100 <= result.max_drawdown_percent <= 0, path, "drawdown must be a percentage in [-100,0]"
    )
    require(result.total_trades == len(result.trades), path, "trade count contradicts trades")
    require(
        result.winning_trades == sum(t.pnl > 0 for t in result.trades)
        and result.losing_trades == sum(t.pnl < 0 for t in result.trades),
        path,
        "win/loss counts contradict PnL",
    )
    equivalent(
        result.win_rate,
        result.winning_trades / result.total_trades * 100 if result.total_trades else None,
        path + "/win_rate",
    )
    equivalent(result.profit_factor, profit_factor(result.trades), path + "/profit_factor")
    equivalent(
        result.final_balance,
        result.initial_balance + sum(t.pnl for t in result.trades),
        path + "/final_balance",
    )
    require(
        result.execution is not None and result.execution == scope.execution,
        path,
        "missing or contradictory execution assumptions",
    )
    require(
        result.benchmark_policy == NET_POLICY,
        path + "/benchmark_policy",
        "unsupported or ambiguous benchmark policy; never label gross/unknown returns as net",
    )
    require(
        result.buy_and_hold_return_percent is None or result.buy_and_hold_return_percent >= -100,
        path,
        "invalid benchmark return",
    )
    require(
        (result.benchmark_costs is None) == (result.buy_and_hold_return_percent is None),
        path,
        "benchmark costs and return must both be present or both null",
    )
    require(
        result.max_drawdown_percent <= min(0, result.total_return_percent) + 1e-8,
        path + "/max_drawdown_percent",
        "drawdown cannot be smaller than final loss from initial capital",
    )
    previous_exit = None
    cash = result.initial_balance
    fills: list[ExecutionFill] = []
    for index, trade in enumerate(result.trades):
        at = f"{path}/trades/{index}"
        require(
            trade.entry_time <= trade.exit_time
            and (previous_exit is None or previous_exit < trade.entry_time),
            at,
            "overlapping/nonchronological trades",
        )
        if scope.start is not None and scope.end is not None:
            require(
                scope.start < trade.entry_time <= trade.exit_time < scope.end,
                at,
                "trade crosses segment boundary or executes at first segment open",
            )
        entry, exit = trade.entry_execution, trade.exit_execution
        require(entry is not None and exit is not None, at, "missing v0.9 fill attribution")
        assert entry is not None and exit is not None and result.execution is not None
        require(
            entry.side == "buy" and exit.side == "sell" and not entry.forced,
            at,
            "invalid fill side",
        )
        if exit.forced:
            require(
                index == len(result.trades) - 1
                and scope.end is not None
                and trade.exit_time == scope.end - duration,
                at,
                "forced liquidation outside final segment candle",
            )
        require(
            exit.forced or trade.exit_time > trade.entry_time, at, "ordinary exit must follow entry"
        )
        if scope.start is not None:
            require(
                (trade.entry_time - scope.start) % duration == timedelta(0)
                and (trade.exit_time - scope.start) % duration == timedelta(0),
                at,
                "trade timestamps must align to segment candle opens",
            )
        for fill in (entry, exit):
            expected = quote_execution(fill.reference_price, fill.side, result.execution).fill(
                trade.quantity, forced=fill.forced
            )
            equivalent(
                fill.model_dump(mode="json"), expected.model_dump(mode="json"), at + "/execution"
            )
        equivalent(trade.entry_price, entry.fill_price, at + "/entry_price")
        equivalent(trade.exit_price, exit.fill_price, at + "/exit_price")
        cost = entry.quantity * entry.fill_price + entry.fee
        proceeds = exit.quantity * exit.fill_price - exit.fee
        equivalent(cost, cash, at + "/allocated_cash")
        equivalent(trade.pnl, proceeds - cost, at + "/pnl")
        equivalent(trade.pnl_percent, trade.pnl / cost * 100, at + "/pnl_percent")
        cash = proceeds
        previous_exit = trade.exit_time
        fills.extend((entry, exit))
    equivalent(result.costs.model_dump(), total_costs(fills).model_dump(), path + "/costs")
    if segment.excess_path is not None:
        equivalent(
            segment.excess,
            result.total_return_percent - result.buy_and_hold_return_percent
            if result.buy_and_hold_return_percent is not None
            else None,
            segment.excess_path,
        )


def shared_check(data: SharedData, config: Any) -> timedelta:
    duration = interval_duration(config.timeframe)
    path = "/shared_data"
    require(
        data.evaluation_start < data.evaluation_end
        and data.evaluation_start <= data.first_candle_open < data.evaluation_start + duration
        and data.last_candle_open + duration
        <= data.evaluation_end
        < data.last_candle_open + 2 * duration,
        path,
        "invalid evaluation coverage/boundaries",
    )
    require(
        data.candle_count * duration == data.last_candle_open - data.first_candle_open + duration,
        path,
        "candle counts contradict UTC boundaries",
    )
    require(
        data.history_candle_count == data.candle_count + data.warmup_candles
        and data.warmup_candles >= data.required_warmup_candles,
        path,
        "invalid warm-up/history counts",
    )
    require(
        config.evaluation_end == data.evaluation_end
        and data.evaluation_start == data.evaluation_end - timedelta(days=config.period_days),
        path,
        "configuration contradicts evaluation range",
    )
    for anchor in data.indicator_initializations:
        require(
            anchor.history_start == data.first_candle_open - anchor.prior_candle_count * duration,
            path + "/indicator_initializations",
            "initialization boundary contradicts prior count",
        )
    return duration


def _segment(
    scope_id: str,
    label: str,
    role: Any,
    data: SegmentResult,
    path: str,
    rule: RuleStrategy,
    execution: ExecutionConfig,
    balance: float,
    duration: timedelta,
    expected_start: datetime,
    expected_end: datetime,
) -> Segment:
    require(
        data.start == expected_start
        and data.end == expected_end
        and data.candle_count * duration == data.end - data.start,
        path,
        "inconsistent segment boundaries/count",
    )
    equivalent(data.result.initial_balance, balance, path + "/result/initial_balance")
    return Segment(
        EvidenceScope(
            id=scope_id,
            label=label,
            role=role,
            start=data.start,
            end=data.end,
            strategy=rule.model_dump(mode="json"),
            execution=execution,
        ),
        path + "/result",
        data.result,
        data.excess_return_pp,
        path + "/excess_return_pp",
    )


def check_dependencies(
    data: ComparisonResult
    | ValidationReport
    | SensitivityReport
    | CostScenarioReport
    | WalkForwardReport,
) -> None:
    if isinstance(data, SensitivityReport):
        rules = [variant.strategy for variant in data.variants]
    elif isinstance(data, CostScenarioReport):
        rules = [data.configuration.strategy]
    else:
        rules = [named.to_rules() for named in data.configuration.strategies]
    keys = set().union(*(dependencies(rule) for rule in rules))
    shared = data.shared_data
    actual = [indicator_key(spec) for spec in shared.indicators]
    require(
        actual == sorted(keys),
        "/shared_data/indicators",
        "dependencies/order contradict configured strategies",
    )
    required = max((prior_candles(spec) for spec in shared.indicators), default=0)
    require(
        shared.required_warmup_candles == required,
        "/shared_data/required_warmup_candles",
        "required warm-up contradicts configured indicator dependencies",
    )
    local = not isinstance(data, ComparisonResult | ValidationReport)
    legacy_required = max(
        (prior_candles(spec) for spec in shared.indicators if isinstance(spec, Indicator)),
        default=0,
    )
    anchors = shared.indicator_initializations
    if local or any(not isinstance(spec, Indicator) for spec in shared.indicators):
        require(
            [indicator_key(a.indicator) for a in anchors] == sorted(keys),
            "/shared_data/indicator_initializations",
            "missing/duplicate initialization metadata",
        )
    for anchor in anchors:
        count = (
            legacy_required
            if isinstance(anchor.indicator, Indicator) and not local
            else prior_candles(anchor.indicator)
        )
        require(
            anchor.prior_candle_count == count
            and count <= shared.warmup_candles
            and anchor.input_fields == input_fields(anchor.indicator)
            and anchor.seed_policy == initialization_policy(anchor.indicator),
            "/shared_data/indicator_initializations",
            "initialization policy or input fields contradict indicator definitions",
        )


def check_research(data: ResearchInput, raw: dict[str, Any], prefix: str) -> list[Segment]:
    segments = []
    if isinstance(data, CLIBacktest):
        duration = interval_duration(data.timeframe)
        require(
            data.candle_count * duration == data.end_time - data.start_time + duration,
            "/candle_count",
            "backtest start/end are candle-open timestamps and must match candle count",
        )
        require(
            data.execution is not None, "/execution", "explicit v0.9 execution assumptions required"
        )
        assert data.execution is not None
        if isinstance(data.strategy, RuleStrategy):
            require(
                data.trading_fee == data.execution.fee_rate,
                "/trading_fee",
                "fee contradicts execution",
            )
        else:
            require(
                data.strategy.fee == data.execution.fee_rate
                and data.strategy.entry_rsi < data.strategy.exit_rsi,
                "/strategy",
                "invalid legacy RSI configuration",
            )
        if data.evaluation_period is not None:
            period = data.evaluation_period
            require(
                period.requested_start < period.requested_end
                and period.requested_start <= data.start_time < period.requested_start + duration
                and data.end_time + duration <= period.requested_end < data.end_time + 2 * duration
                and period.warmup_candles >= period.required_warmup_candles,
                "/evaluation_period",
                "invalid requested range/warm-up",
            )
        segments.append(
            Segment(
                EvidenceScope(
                    id="strategy.single",
                    label="Single strategy",
                    role="strategy",
                    start=data.start_time,
                    end=data.end_time + duration,
                    strategy=data.strategy.model_dump(mode="json"),
                    execution=data.execution,
                ),
                prefix,
                data,
                None,
                None,
            )
        )
    else:
        config: Any = data.configuration
        shared = data.shared_data
        duration = shared_check(shared, config)
        check_dependencies(data)
        start, end = shared.first_candle_open, shared.last_candle_open + duration
        if isinstance(data, ComparisonResult):
            require(
                [r.id for r in data.results] == [s.id for s in data.configuration.strategies],
                "/results",
                "strategy IDs/order must match configuration exactly",
            )
            equivalent(data.ranking, rank_results(data.results, data.ranking_criterion), "/ranking")
            require(
                data.ranking_criterion == data.configuration.sort_by,
                "/ranking_criterion",
                "sort mismatch",
            )
            for index, (comparison_row, named) in enumerate(
                zip(data.results, data.configuration.strategies, strict=True)
            ):
                require(
                    comparison_row.strategy == named.to_rules()
                    and comparison_row.name == named.name,
                    "/results",
                    "strategy changed",
                )
                equivalent(
                    comparison_row.result.initial_balance,
                    config.initial_balance,
                    "/results/initial_balance",
                )
                equivalent(
                    comparison_row.result.buy_and_hold_return_percent,
                    data.buy_and_hold_return_percent,
                    "/buy_and_hold_return_percent",
                )
                segments.append(
                    Segment(
                        EvidenceScope(
                            id=f"strategy.{comparison_row.id}",
                            label=comparison_row.name,
                            role="strategy",
                            start=start,
                            end=end,
                            strategy=comparison_row.strategy.model_dump(mode="json"),
                            execution=config.execution_config(),
                        ),
                        f"/results/{index}/result",
                        comparison_row.result,
                        comparison_row.excess_return_pp,
                        f"/results/{index}/excess_return_pp",
                    )
                )
        elif isinstance(data, ValidationReport | SensitivityReport | CostScenarioReport):
            split = data.split
            require(
                split.train_ratio == config.train_ratio
                and split.train_start == start
                and split.test_end == end
                and split.train_candle_count + split.test_candle_count == shared.candle_count
                and split.train_candle_count
                == train_count(shared.candle_count, config.train_ratio),
                "/split",
                "split contradicts shared history/configuration",
            )
            if isinstance(data, ValidationReport):
                require(
                    [r.id for r in data.results] == [s.id for s in data.configuration.strategies],
                    "/results",
                    "strategy IDs/order mismatch",
                )
                for index, (validation_row, named) in enumerate(
                    zip(data.results, data.configuration.strategies, strict=True)
                ):
                    require(
                        validation_row.strategy == named.to_rules()
                        and validation_row.name == named.name,
                        "/results",
                        "strategy changed",
                    )
                    for label, segment, left, right in [
                        ("train", validation_row.train, start, split.train_end),
                        ("test", validation_row.test, split.test_start, end),
                    ]:
                        segments.append(
                            _segment(
                                f"strategy.{validation_row.id}.{label}",
                                validation_row.name,
                                label,
                                segment,
                                f"/results/{index}/{label}",
                                validation_row.strategy,
                                config.execution_config(),
                                config.initial_balance,
                                duration,
                                left,
                                right,
                            )
                        )
                    equivalent(
                        validation_row.return_gap_pp,
                        validation_row.test.result.total_return_percent
                        - validation_row.train.result.total_return_percent,
                        f"/results/{index}/return_gap_pp",
                    )
            elif isinstance(data, SensitivityReport):
                definitions, variants = expand_grid(
                    data.configuration.base_strategy, data.configuration.parameters
                )
                equivalent(
                    [v.model_dump(mode="json") for v in data.variants],
                    [v.model_dump(mode="json") for v in variants],
                    "/variants",
                )
                equivalent(
                    [p.model_dump(mode="json") for p in data.parameters],
                    [p.model_dump(mode="json") for p in definitions],
                    "/parameters",
                )
                require(
                    [r.variant_id for r in data.results] == [v.id for v in variants],
                    "/results",
                    "variant IDs/order mismatch",
                )
                rows = list(data.results)
                summary, neighbors, series, matrix = describe_grid(definitions, variants, rows)
                for name, expected in [
                    ("summary", summary.model_dump(mode="json")),
                    ("neighbors", [n.model_dump(mode="json") for n in neighbors]),
                    (
                        "ordered_series",
                        [p.model_dump(mode="json") for p in series] if series is not None else None,
                    ),
                    ("matrix", matrix.model_dump(mode="json") if matrix else None),
                ]:
                    equivalent(
                        getattr(data, name).model_dump(mode="json")
                        if name in ("summary", "matrix") and getattr(data, name) is not None
                        else [n.model_dump(mode="json") for n in getattr(data, name)]
                        if name in ("neighbors", "ordered_series")
                        and getattr(data, name) is not None
                        else None,
                        expected,
                        "/" + name,
                    )
                require(
                    [r.observation for r in rows] == [r.observation for r in data.results],
                    "/results",
                    "grid observation mismatch",
                )
                for index, (variant_row, variant) in enumerate(
                    zip(data.results, variants, strict=True)
                ):
                    segments.append(
                        _segment(
                            f"variant.{variant.id}.train",
                            variant.id,
                            "variant_train",
                            variant_row.train,
                            f"/results/{index}/train",
                            variant.strategy,
                            config.execution_config(),
                            config.initial_balance,
                            duration,
                            start,
                            split.train_end,
                        )
                    )
            else:
                require(
                    [r.id for r in data.results] == [s.id for s in data.configuration.scenarios]
                    and data.baseline_id == data.configuration.scenarios[0].id,
                    "/results",
                    "scenario IDs/order/baseline mismatch",
                )
                baseline = data.results[0].train.result.total_return_percent
                for index, (cost_row, scenario) in enumerate(
                    zip(data.results, data.configuration.scenarios, strict=True)
                ):
                    require(
                        cost_row.name == scenario.name
                        and cost_row.execution == scenario.execution_config(config.fee),
                        "/results",
                        "scenario assumptions changed",
                    )
                    equivalent(
                        cost_row.return_difference_pp,
                        cost_row.train.result.total_return_percent - baseline,
                        f"/results/{index}/return_difference_pp",
                    )
                    segments.append(
                        _segment(
                            f"scenario.{cost_row.id}.train",
                            cost_row.name,
                            "scenario_train",
                            cost_row.train,
                            f"/results/{index}/train",
                            data.configuration.strategy,
                            cost_row.execution,
                            config.initial_balance,
                            duration,
                            start,
                            split.train_end,
                        )
                    )
        else:
            assert isinstance(data, WalkForwardReport)
            train, test, step = data.configuration.windows.counts(config.timeframe)
            count = 1 + (shared.candle_count - train - test) // step
            require(
                2 <= count <= data.configuration.windows.max_folds and len(data.folds) == count,
                "/folds",
                "incomplete/missing/excess folds",
            )
            expected_pairs = [
                (f.id, s.id) for f in data.folds for s in data.configuration.strategies
            ]
            require(
                [(r.fold_id, r.strategy_id) for r in data.results] == expected_pairs,
                "/results",
                "fold/strategy IDs/order mismatch",
            )
            require(
                [s.strategy_id for s in data.summaries]
                == [s.id for s in data.configuration.strategies],
                "/summaries",
                "fold_summary IDs/order mismatch",
            )
            for index, fold in enumerate(data.folds):
                left = (
                    start + index * step * duration
                    if data.configuration.windows.mode == "rolling"
                    else start
                )
                cut = start + (index * step + train) * duration
                right = cut + test * duration
                require(
                    fold.id == f"fold-{index + 1:03d}"
                    and fold.train_start == left
                    and fold.train_end == fold.test_start == cut
                    and fold.test_end == right
                    and fold.train_candle_count * duration == cut - left
                    and fold.test_candle_count == test,
                    "/folds",
                    "fold generation contradicts declared window policy",
                )
                for offset, named in enumerate(data.configuration.strategies):
                    row_index = index * len(data.configuration.strategies) + offset
                    fold_row = data.results[row_index]
                    require(
                        fold_row.strategy == named.to_rules() and fold_row.name == named.name,
                        "/results",
                        "strategy changed across folds",
                    )
                    for label, segment, a, b in [
                        ("train", fold_row.train, left, cut),
                        ("test", fold_row.test, cut, right),
                    ]:
                        segments.append(
                            _segment(
                                f"fold.{fold.id}.strategy.{named.id}.{label}",
                                fold_row.name,
                                label,
                                segment,
                                f"/results/{row_index}/{label}",
                                fold_row.strategy,
                                config.execution_config(),
                                config.initial_balance,
                                duration,
                                a,
                                b,
                            )
                        )
            require(
                data.unused_trailing_candles
                == shared.candle_count - (train + test + (count - 1) * step),
                "/unused_trailing_candles",
                "incorrect trailing candle count",
            )
            for index, fold_summary in enumerate(data.summaries):
                fold_rows = [r for r in data.results if r.strategy_id == fold_summary.strategy_id]
                expected_summary = summarize_tests(fold_rows, data.configuration.stitch_oos)
                equivalent(
                    fold_summary.model_dump(mode="json"),
                    expected_summary.model_dump(mode="json"),
                    f"/summaries/{index}",
                )
    if not isinstance(data, CLIBacktest):
        for checked_segment in segments:
            raw_segment = _raw_at(raw, checked_segment.path.removesuffix("/result"))
            if checked_segment.scope.start is not None and "warmup_candles" in raw_segment:
                required_prefix = data.shared_data.warmup_candles + int(
                    (checked_segment.scope.start - data.shared_data.first_candle_open) / duration
                )
                require(
                    raw_segment["warmup_candles"] == required_prefix,
                    checked_segment.path,
                    "segment preceding-history count contradicts initialization boundary",
                )
    for validated_segment in segments:
        check_result(validated_segment, raw, duration)
    return segments
