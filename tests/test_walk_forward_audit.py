"""Final financial audit: independent hand calculations and both window protocols."""

import json
from collections.abc import Sequence
from datetime import timedelta
from statistics import median

import pytest
from conftest import make_candles
from test_comparison_engine import named
from test_rules import comparison, indicator, strategy
from test_validation_engine import PRICE, ZERO
from test_walk_forward import START, history, settings

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle
from strategy_backtest_agent.rules.evaluator import Context
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.walk_forward import engine
from strategy_backtest_agent.walk_forward.engine import run_walk_forward, summarize_tests


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
@pytest.mark.parametrize("normal_exit", [False, True])
def test_manual_multiple_roundtrips_final_open_exit_and_costs(mode: str, normal_exit: bool) -> None:
    # Four candles/segment. Buy at second open 10, sell at third open 20;
    # then either enter at final open 5 and liquidate at close 8, or remain flat.
    rule = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 15}),
        comparison(PRICE, ">", {"type": "value", "value": 15}),
    )
    config = settings(
        timeframe="6h",
        fee=0.01,
        execution={"spread_bps": 20, "slippage_bps": 10},
        strategies=[named("levels", rule)],
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    closes: list[float] = [10, 20, 20 if normal_exit else 10, 8] * 4
    opens: list[float] = [11, 10, 20, 5] * 4
    source = [
        c.model_copy(update={"timestamp": START + timedelta(hours=6 * i)})
        for i, c in enumerate(make_candles(closes, opens))
    ]
    report = run_walk_forward(source, config)
    # Independent arithmetic: full spread 20 bps => 10 per side, plus 10 slippage.
    factor = (0.998 * 0.99) / (1.002 * 1.01)
    first_cash = 1000 * (20 / 10) * factor
    final_cash = first_cash if normal_exit else first_cash * (8 / 5) * factor
    for row in report.results:
        result = row.test.result
        assert result.final_balance == pytest.approx(final_cash)
        assert result.initial_balance == 1000
        assert result.total_trades == (1 if normal_exit else 2)
        assert result.final_balance == pytest.approx(1000 + sum(t.pnl for t in result.trades))
        q1 = 1000 / (10 * 1.002 * 1.01)
        q2 = 0 if normal_exit else first_cash / (5 * 1.002 * 1.01)
        assert result.costs.fees == pytest.approx(
            q1 * (10 * 1.002 + 20 * 0.998) * 0.01 + q2 * (5 * 1.002 + 8 * 0.998) * 0.01
        )
        assert result.costs.modeled_spread_cost == pytest.approx(q1 * 30 * 0.001 + q2 * 13 * 0.001)
        assert result.costs.modeled_slippage_cost == pytest.approx(
            q1 * 30 * 0.001 + q2 * 13 * 0.001
        )
        assert result.buy_and_hold_return_percent == pytest.approx((8 / 11 * factor - 1) * 100)
        benchmark_q = 1000 / (11 * 1.002 * 1.01)
        assert result.benchmark_costs is not None
        assert result.benchmark_costs.fees == pytest.approx(
            benchmark_q * (11 * 1.002 + 8 * 0.998) * 0.01
        )
        assert result.benchmark_costs.modeled_spread_cost == pytest.approx(benchmark_q * 19 * 0.001)
        assert result.benchmark_costs.modeled_slippage_cost == pytest.approx(
            benchmark_q * 19 * 0.001
        )
        forced = [
            t for t in result.trades if t.exit_execution is not None and t.exit_execution.forced
        ]
        assert len(forced) == (0 if normal_exit else 1)
        for trade in result.trades:
            assert row.test.start < trade.entry_time <= trade.exit_time < row.test.end
    # An expanding Train is one continuous segment: internal day boundaries do not
    # liquidate positions or suppress signals. Only its final close liquidates.
    continued_multiplier = (20 / 11 if normal_exit else 20 / 5) * factor
    for i, row in enumerate(report.results):
        assert row.train.result.initial_balance == 1000
        assert row.train.result.final_balance == pytest.approx(
            final_cash * continued_multiplier ** (i if mode == "expanding" else 0)
        )


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_regular_exit_at_last_open_is_not_liquidated_twice(mode: str) -> None:
    rule = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 15}),
        comparison(PRICE, ">", {"type": "value", "value": 15}),
    )
    config = settings(
        timeframe="8h",
        strategies=[named("levels", rule)],
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    source = [
        c.model_copy(update={"timestamp": START + timedelta(hours=8 * i)})
        for i, c in enumerate(make_candles([10, 20, 1] * 4, [10, 10, 30] * 4))
    ]
    report = run_walk_forward(source, config)
    for row in report.results:
        result = row.test.result
        assert result.final_balance == 3000  # 100 units bought at 10, sold at 30.
        assert result.total_trades == 1
        assert result.trades[0].exit_execution is not None
        assert not result.trades[0].exit_execution.forced
        assert result.trades[0].exit_time == row.test.end - timedelta(hours=8)
        assert result.buy_and_hold_return_percent == pytest.approx(-90)


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_train_position_closes_locally_and_test_does_not_inherit_it(mode: str) -> None:
    rule = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 50}), comparison(PRICE, "<", ZERO)
    )
    config = settings(
        strategies=[named("train-only", rule)],
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    source = history(config, [10, 20, 100, 100, 100, 100, 100, 100])
    source[1] = source[1].model_copy(update={"open": 10, "low": 10})
    report = run_walk_forward(source, config)
    assert report.results[0].train.result.final_balance == 2000
    assert report.results[0].train.result.trades[0].exit_time == START + timedelta(hours=12)
    for row in report.results:
        assert row.test.result.initial_balance == row.test.result.final_balance == 1000
        assert row.test.result.total_trades == 0
        assert row.test.result.costs.fees == 0
        assert row.test.result.win_rate is None and row.test.result.profit_factor is None


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
@pytest.mark.parametrize("name", ["rsi", "ema", "sma"])
def test_both_modes_future_prefix_and_more_folds_are_invariant(mode: str, name: str) -> None:
    rule = strategy(comparison(indicator(name, 2), ">", ZERO), comparison(PRICE, "<", ZERO))
    config = settings(
        strategies=[named("fixed", rule)], windows={"mode": mode, "train_days": 1, "test_days": 1}
    )
    source = history(config)
    warmup = len(source) - 8
    changed = [
        c
        if i < warmup + 4
        else c.model_copy(update={"open": 1000, "close": 1000, "high": 1000, "low": 1000})
        for i, c in enumerate(source)
    ]
    before = run_walk_forward(source, config)
    assert before.results[0] == run_walk_forward(changed, config).results[0]
    shorter = type(config).model_validate(
        {**config.model_dump(), "period_days": 3, "evaluation_end": START + timedelta(days=3)}
    )
    assert run_walk_forward(source[:-2], shorter).results == before.results[:2]
    assert before.model_dump_json() == run_walk_forward(source, config).model_dump_json()
    # Round-trip JSON preserves frozen protocol, precise dates and original strategy definitions.
    assert json.loads(before.model_dump_json())["configuration"] == config.model_dump(mode="json")


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_execution_never_receives_future_data(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(
        strategies=[named("fixed", strategy(comparison(indicator("ema", 2))))],
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    observed: list[tuple[int, int]] = []

    def inspect(
        candles: Sequence[Candle],
        portfolio: BacktestConfig,
        rule: RuleStrategy,
        *,
        evaluation_start: int,
        context: Context,
    ) -> BacktestResult:
        assert context.prices == [c.close for c in candles]
        assert all(len(v) == len(candles) for v in context.indicators.values())
        observed.append((evaluation_start, len(candles)))
        return run_backtest(
            candles, portfolio, rule, evaluation_start=evaluation_start, context=context
        )

    monkeypatch.setattr(engine, "run_backtest", inspect)
    run_walk_forward(history(config), config)
    assert observed == [
        (10 if mode == "expanding" else 10 + 2 * i, 12 + 2 * i)
        if segment == 0
        else (12 + 2 * i, 14 + 2 * i)
        for i in range(3)
        for segment in range(2)
    ]


def test_modes_share_test_execution_and_initialization_semantics() -> None:
    reports = []
    for mode in ("rolling", "expanding"):
        config = settings(
            strategies=[named("ema", strategy(comparison(indicator("ema", 2))))],
            fee=0.01,
            execution={"spread_bps": 20, "slippage_bps": 10},
            windows={"mode": mode, "train_days": 1, "test_days": 1},
        )
        source = history(config, [10, 11, 9, 8, 12, 15, 11, 13, 9, 7, 8, 9, 10, 11, 13, 8, 12, 14])
        reports.append(run_walk_forward(source, config))
    a, b = reports
    assert a.shared_data == b.shared_data
    assert [r.test for r in a.results] == [r.test for r in b.results]


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_test_only_aggregation_and_normalized_index(mode: str) -> None:
    config = settings(stitch_oos=True, windows={"mode": mode, "train_days": 1, "test_days": 1})
    source = history(config, [10, 90, 10, 20, 10, 5, 10, 10])
    source = [
        c.model_copy(update={"open": 10, "high": max(10, c.close), "low": min(10, c.close)})
        for c in source
    ]
    report = run_walk_forward(source, config)
    summary = report.summaries[0]
    assert summary.total_test_trades == 3
    assert summary.median_test_return_percent == 0
    assert summary.positive_test_fraction == 1 / 3
    assert summary.minimum_test_return_percent == -50
    assert summary.maximum_test_return_percent == 100
    assert summary.median_test_max_drawdown_percent == median(
        r.test.result.max_drawdown_percent for r in report.results
    )
    assert summary.stitched_oos_index is not None
    assert [p.value for p in summary.stitched_oos_index] == [100, 200, 100, 100]
    # Replace diagnostic Train reports with another valid Train: OOS cannot change.
    altered = [r.model_copy(update={"train": report.results[0].train}) for r in report.results]
    assert summarize_tests(altered, True) == summary
    for earlier, later in zip(report.folds, report.folds[1:], strict=False):
        assert earlier.test_end == later.test_start


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_zero_trade_folds_charge_no_strategy_costs_but_net_benchmark_has_costs(mode: str) -> None:
    never = strategy(comparison(PRICE, "<", ZERO))
    config = settings(
        strategies=[named("never", never)],
        stitch_oos=True,
        fee=0.01,
        execution={"spread_bps": 20, "slippage_bps": 10},
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    report = run_walk_forward(history(config), config)
    for row in report.results:
        for segment in (row.train, row.test):
            result = segment.result
            assert result.initial_balance == result.final_balance == 1000
            assert result.win_rate is None and result.profit_factor is None
            assert result.total_trades == 0 and result.max_drawdown_percent == 0
            assert result.costs.model_dump() == {
                "fees": 0,
                "modeled_spread_cost": 0,
                "modeled_slippage_cost": 0,
            }
            assert result.buy_and_hold_return_percent == pytest.approx(
                (0.998 * 0.99 / (1.002 * 1.01) - 1) * 100
            )
    summary = report.summaries[0]
    assert summary.positive_test_folds == 0 and summary.outperforming_test_folds == 3
    assert summary.stitched_oos_index is not None
    assert [p.value for p in summary.stitched_oos_index] == [100] * 4
    assert '"win_rate":null' in report.model_dump_json()
    assert '"profit_factor":null' in report.model_dump_json()


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_final_train_entry_signal_never_becomes_first_test_fill(mode: str) -> None:
    rule = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 15}), comparison(PRICE, "<", ZERO)
    )
    config = settings(
        strategies=[named("last-signal", rule)],
        windows={"mode": mode, "train_days": 1, "test_days": 1},
    )
    report = run_walk_forward(history(config, [10, 20, 10, 10, 10, 10, 10, 10]), config)
    assert report.results[0].train.result.total_trades == 0
    for row in report.results:
        assert row.test.result.total_trades == 0
        assert row.test.result.final_balance == 1000


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_hand_calculated_drawdown_includes_entry_cost_and_final_liquidation(mode: str) -> None:
    config = settings(
        windows={"mode": mode, "train_days": 1, "test_days": 1},
        fee=0.01,
        execution={"spread_bps": 20, "slippage_bps": 10},
    )
    source = history(config, [10, 10, 10, 5, 10, 20, 10, 10])
    source = [
        c.model_copy(update={"open": 10, "high": max(10, c.close), "low": min(10, c.close)})
        for c in source
    ]
    report = run_walk_forward(source, config)
    q = 1000 / (10 * 1.002 * 1.01)
    final_loss = q * 5 * 0.998 * 0.99
    entry_value = q * 10
    assert report.results[0].test.result.max_drawdown_percent == pytest.approx(
        (final_loss / 1000 - 1) * 100
    )
    assert report.results[1].test.result.max_drawdown_percent == pytest.approx(
        (entry_value / 1000 - 1) * 100
    )
    assert report.results[1].test.result.final_balance == pytest.approx(q * 20 * 0.998 * 0.99)


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
@pytest.mark.parametrize("name", ["rsi", "ema", "sma"])
def test_added_strategy_preserves_actual_cached_values_and_seed(
    mode: str, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = strategy(comparison(indicator(name, 2)), comparison(indicator(name, 2), ">"))
    solo = settings(
        strategies=[named("fixed", rule)], windows={"mode": mode, "train_days": 1, "test_days": 1}
    )
    combined = type(solo).model_validate(
        {
            **solo.model_dump(),
            "strategies": [
                named("fixed", rule),
                named("long", strategy(comparison(indicator("ema", 10)))),
            ],
        }
    )
    caches: list[tuple[int, Context]] = []

    def inspect(
        candles: Sequence[Candle],
        portfolio: BacktestConfig,
        fixed: RuleStrategy,
        *,
        evaluation_start: int,
        context: Context,
    ) -> BacktestResult:
        if fixed == rule:
            caches.append((evaluation_start, context))
        return run_backtest(
            candles, portfolio, fixed, evaluation_start=evaluation_start, context=context
        )

    monkeypatch.setattr(engine, "run_backtest", inspect)
    reports = []
    for config in (solo, combined):
        source = history(config)
        source = [
            c.model_copy(update={"open": value, "close": value, "high": value, "low": value})
            for c in source
            for value in [20.0 + (int((c.timestamp - START).total_seconds() / 43200) % 9)]
        ]
        reports.append(run_walk_forward(source, config))
    # Six segments per strategy: compare actual eligible cached indicator values,
    # allowing only the additional unused warm-up prefix to differ.
    for (left, first_cache), (right, second_cache) in zip(caches[:6], caches[6:], strict=True):
        assert first_cache.indicators[(name, 2)][left:] == pytest.approx(
            second_cache.indicators[(name, 2)][right:]
        )
    a, b = reports
    assert a.shared_data.indicator_initializations[0] in b.shared_data.indicator_initializations
    for first, second in zip(a.results, b.results[::2], strict=True):
        assert first.train.result == second.train.result
        assert first.test.result == second.test.result
