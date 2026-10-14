"""Frozen strategy cost scenarios: manual balances, cache reuse and no Test evaluation."""

import asyncio
from datetime import timedelta

import pandas as pd
import pytest
from pydantic import ValidationError
from test_comparison_engine import END, Provider, history
from test_execution import RULE
from test_rules import comparison, indicator, strategy
from test_validation_engine import small

from strategy_backtest_agent import indicators
from strategy_backtest_agent.costs.engine import fetch_and_run_costs, run_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig


def settings(**updates: object) -> CostScenarioConfig:
    return CostScenarioConfig.model_validate(
        {
            "symbol": "BTCUSDT",
            "period_days": 1,
            "evaluation_end": END,
            "strategy": RULE,
            "scenarios": [
                {"id": "baseline", "name": "Baseline"},
                {"id": "low", "name": "Low", "spread_bps": 5, "slippage_bps": 2},
                {"id": "medium", "name": "Medium", "spread_bps": 20, "slippage_bps": 10},
            ],
            **updates,
        }
    )


def test_manually_calculated_scenario_cash_costs_and_declared_order() -> None:
    report = run_cost_scenarios(
        small([90, 110, 10000, 10000], [90, 100, 10000, 10000]),
        settings(timeframe="6h", train_ratio=0.5, initial_balance=1000),
    )
    assert [row.id for row in report.results] == ["baseline", "low", "medium"]
    assert report.baseline_id == "baseline"
    baseline = 1000 / (100 * 1.001) * 110 * 0.999
    for row, fraction in zip(report.results, [0, 0.00045, 0.002], strict=True):
        quantity = 1000 / (100 * (1 + fraction) * 1.001)
        final = quantity * 110 * (1 - fraction) * 0.999
        assert row.train.result.initial_balance == 1000
        assert row.train.result.final_balance == pytest.approx(final)
        assert row.return_difference_pp == pytest.approx((final - baseline) / 1000 * 100)
        assert row.train.result.costs.fees == pytest.approx(
            quantity * (100 * (1 + fraction) + 110 * (1 - fraction)) * 0.001
        )
        assert (
            row.train.start == report.split.train_start and row.train.end == report.split.train_end
        )
        assert row.train.result.total_trades == 1
        assert row.train.result.trades[0].exit_execution is not None
        assert row.train.result.trades[0].exit_execution.forced
        assert row.train.result.trades[0].exit_execution.reference_price == 110
    assert report.results[0].train.result.costs.modeled_spread_cost == 0
    assert report.results[1].train.result.costs.modeled_spread_cost > 0
    assert report.results[1].train.result.costs.modeled_slippage_cost > 0


def test_inherited_fees_and_explicit_fee_variation() -> None:
    config = settings(
        fee=0.002,
        scenarios=[
            {"id": "base", "name": "Base"},
            {"id": "fee", "name": "Fee change", "fee_rate": 0.003},
        ],
    )
    report = run_cost_scenarios(
        small([90, 110, 100, 100]),
        config.model_copy(update={"timeframe": "6h", "train_ratio": 0.5}),
    )
    assert [row.execution.fee_rate for row in report.results] == [0.002, 0.003]
    assert (
        report.results[0].train.result.final_balance > report.results[1].train.result.final_balance
    )


@pytest.mark.parametrize(
    "kind",
    [
        "single",
        "nine",
        "duplicate",
        "first_cost",
        "negative",
        "nonfinite",
        "global_cost",
        "optimize",
        "symbol_override",
    ],
)
def test_invalid_scenarios(kind: str) -> None:
    values = settings().model_dump()
    if kind == "single":
        values["scenarios"] = values["scenarios"][:1]
    elif kind == "nine":
        values["scenarios"] = [{"id": f"s{i}", "name": f"S{i}"} for i in range(9)]
    elif kind == "duplicate":
        values["scenarios"][1]["id"] = "baseline"
    elif kind == "first_cost":
        values["scenarios"][0]["spread_bps"] = 5
    elif kind == "negative":
        values["scenarios"][1]["slippage_bps"] = -1
    elif kind == "nonfinite":
        values["scenarios"][1]["spread_bps"] = float("inf")
    elif kind == "global_cost":
        values["execution"] = {"spread_bps": 10}
    elif kind == "optimize":
        values["parameters"] = [{"path": "entry.right.value", "values": [90, 95]}]
    else:
        values["scenarios"][1]["symbol"] = "ETHUSDT"
    with pytest.raises(ValidationError):
        CostScenarioConfig.model_validate(values)


def test_one_fetch_unique_indicators_same_cache_and_independent_portfolios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    original = indicators.rsi

    def capture(series: pd.Series, period: int) -> pd.Series:
        calls.append((period, len(series)))
        return original(series, period)

    monkeypatch.setattr(indicators, "rsi", capture)
    rule = strategy(
        comparison(indicator("rsi", 2), "<", {"type": "value", "value": 45}),
        comparison(indicator("rsi", 2), ">", {"type": "value", "value": 55}),
    )
    provider = Provider(history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3))
    report = asyncio.run(fetch_and_run_costs(provider, settings(strategy=rule, train_ratio=0.5)))
    assert provider.requests == [("BTCUSDT", "1h", END - timedelta(hours=27), END)]
    assert calls == [(2, 15)]
    times = [
        [(t.entry_time, t.exit_time) for t in row.train.result.trades] for row in report.results
    ]
    assert times[0] == times[1] == times[2] and times[0]
    assert all(
        row.train.result.final_balance
        == pytest.approx(10000 + sum(t.pnl for t in row.train.result.trades))
        for row in report.results
    )
    assert all(row.train.result.initial_balance == 10000 for row in report.results)
    assert all(
        t.exit_time < report.split.test_start
        for row in report.results
        for t in row.train.result.trades
    )


def test_test_prices_cannot_affect_cost_scenarios_and_fixed_reproducibility() -> None:
    config = settings(timeframe="6h", train_ratio=0.5)
    candles = small([90, 110, 100, 100], [90, 100, 100, 100])
    changed = small([90, 110, 100000, 1], [90, 100, 100000, 1])
    first = run_cost_scenarios(candles, config)
    assert run_cost_scenarios(candles, config) == first
    second = run_cost_scenarios(changed, config)
    assert first.results == second.results and first.split == second.split
    assert first.shared_data.candles_sha256 != second.shared_data.candles_sha256
    assert "ranking" not in first.model_dump() and "winner" not in first.model_dump()


def test_invalid_mutated_scenarios_rejected_before_fetch() -> None:
    config = settings()
    config.scenarios.append(config.scenarios[0])
    provider = Provider([])
    with pytest.raises(ValueError, match="unique"):
        asyncio.run(fetch_and_run_costs(provider, config))
    assert provider.requests == []


def test_no_trade_scenarios_keep_cash_and_null_metrics() -> None:
    report = run_cost_scenarios(
        history([100] * 27), settings(strategy=strategy(comparison(indicator("rsi", 2))))
    )
    for row in report.results:
        assert row.train.result.total_trades == 0 and row.train.result.final_balance == 10000
        assert row.train.result.win_rate is row.train.result.profit_factor is None
        assert row.train.result.costs.fees == 0 and row.return_difference_pp == 0


def test_scenarios_backtest_only_train_with_identical_cached_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Sequence

    from strategy_backtest_agent.backtester import run_backtest
    from strategy_backtest_agent.costs import engine
    from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle
    from strategy_backtest_agent.rules.evaluator import Context
    from strategy_backtest_agent.rules.models import RuleStrategy

    original = run_backtest
    calls: list[tuple[int, int, int]] = []

    def audited(
        candles: Sequence[Candle],
        config: BacktestConfig,
        strategy: RuleStrategy | None = None,
        *,
        evaluation_start: int = 0,
        context: Context | None = None,
    ) -> BacktestResult:
        assert context is not None
        assert all(c.timestamp < END - timedelta(hours=12) for c in candles)
        calls.append((len(candles), evaluation_start, id(context)))
        return original(
            candles, config, strategy, evaluation_start=evaluation_start, context=context
        )

    monkeypatch.setattr(engine, "run_backtest", audited)
    rule = strategy(comparison(indicator("rsi", 2), "<", {"type": "value", "value": 45}))
    report = run_cost_scenarios(
        history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3),
        settings(strategy=rule, train_ratio=0.5),
    )
    assert len(calls) == len(report.results) == 3
    assert len(set(calls)) == 1 and calls[0][:2] == (15, 3)


def test_maximum_eight_scenarios_are_valid() -> None:
    config = settings(
        scenarios=[
            {"id": f"scenario-{i}", "name": f"Scenario {i}", "spread_bps": i} for i in range(8)
        ]
    )
    assert len(config.scenarios) == 8
