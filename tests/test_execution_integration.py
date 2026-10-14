"""Execution settings across existing engines, holdout boundaries and stable indicator seeds."""

import math

import pytest
from pydantic import ValidationError
from test_comparison_engine import config as comparison_config
from test_comparison_engine import history, named
from test_execution import EXECUTION, RULE
from test_rules import comparison, indicator, strategy
from test_sensitivity_grid import settings as sensitivity_config
from test_sensitivity_grid import spec
from test_validation_engine import small
from test_validation_models import settings as validation_config

from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.comparison.engine import run_comparison
from strategy_backtest_agent.comparison.models import MarketConfig
from strategy_backtest_agent.models import BacktestConfig, ExecutionConfig
from strategy_backtest_agent.sensitivity.engine import run_sensitivity
from strategy_backtest_agent.validation.engine import run_validation


@pytest.mark.parametrize(
    "cls,alias", [(BacktestConfig, "trading_fee"), (MarketConfig, "fee"), (AIStrategyConfig, "fee")]
)
def test_fee_only_nested_fee_inheritance_and_conflicts(
    cls: type[BacktestConfig] | type[MarketConfig] | type[AIStrategyConfig], alias: str
) -> None:
    legacy = cls.model_validate({"symbol": "BTCUSDT", alias: 0.002})
    assert legacy.execution_config() == ExecutionConfig(fee_rate=0.002)
    inherited = cls.model_validate(
        {"symbol": "BTCUSDT", alias: 0.002, "execution": {"spread_bps": 10}}
    )
    assert inherited.execution_config().fee_rate == getattr(inherited, alias) == 0.002
    assert inherited.execution_config().spread_bps == 10
    nested = cls.model_validate(
        {"symbol": "BTCUSDT", "execution": {"fee_rate": 0.003, "spread_bps": 10}}
    )
    assert getattr(nested, alias) == nested.execution_config().fee_rate == 0.003
    assert cls.model_validate_json(nested.model_dump_json()) == nested
    with pytest.raises(ValueError, match="conflict"):
        cls.model_validate({"symbol": "BTCUSDT", alias: 0.002, "execution": {"fee_rate": 0.003}})


@pytest.mark.parametrize(
    "values", [{"fee_rate": 0.1}, {"spread_bps": -1}, {"slippage_bps": math.nan}]
)
def test_shared_cost_validation_preserves_existing_fee_bounds(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MarketConfig.model_validate({"symbol": "BTCUSDT", "execution": values})


def test_comparison_strategies_share_costs_and_cost_aware_benchmark() -> None:
    candles = history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3)
    report = run_comparison(candles, comparison_config(execution=EXECUTION))
    assert all(row.result.execution == EXECUTION for row in report.results)
    assert len({row.result.buy_and_hold_return_percent for row in report.results}) == 1
    assert (
        report.buy_and_hold_return_percent == report.results[0].result.buy_and_hold_return_percent
    )
    for row in report.results:
        assert row.result.final_balance == pytest.approx(
            row.result.initial_balance + sum(t.pnl for t in row.result.trades)
        )
        assert row.result.costs.fees > 0 and row.result.costs.modeled_spread_cost > 0


def test_train_liquidation_costs_use_train_close_and_test_is_fresh() -> None:
    candles = small([90, 110, 1e6, 1e6], [90, 100, 1e6, 1e6])
    config = validation_config(
        strategies=[named("frozen", RULE)],
        timeframe="6h",
        train_ratio=0.5,
        initial_balance=1000,
        execution=EXECUTION,
    )
    row = run_validation(candles, config).results[0]
    assert row.train.result.final_balance == pytest.approx(1000 / (100.2 * 1.001) * 109.78 * 0.999)
    assert row.train.result.trades[0].exit_execution is not None
    assert row.train.result.trades[0].exit_execution.reference_price == 110
    assert row.train.result.trades[0].exit_execution.forced
    assert row.test.result.initial_balance == row.test.result.final_balance == 1000
    assert row.test.result.trades == []
    assert row.test.result.costs.fees == row.test.result.costs.modeled_spread_cost == 0
    assert row.test.result.max_drawdown_percent == 0


def test_final_train_entry_signal_cannot_execute_in_test_with_costs() -> None:
    candles = small([100, 90, 1e6, 1e6])
    config = validation_config(
        strategies=[named("frozen", RULE)], timeframe="6h", train_ratio=0.5, execution=EXECUTION
    )
    row = run_validation(candles, config).results[0]
    assert row.train.result.total_trades == row.test.result.total_trades == 0


@pytest.mark.parametrize("name,threshold", [("rsi", 36.4), ("ema", 104.0)])
def test_sensitivity_remains_train_only_and_preserves_grid_stability_with_costs(
    name: str, threshold: float
) -> None:
    import asyncio

    from test_sensitivity_audit import Archive, recursive_archive

    from strategy_backtest_agent.sensitivity.engine import fetch_and_analyze

    base = strategy(
        comparison(indicator(name, 2), "<", {"type": "value", "value": threshold}),
        comparison({"type": "price"}, "<", {"type": "value", "value": 0}),
    )
    candles = recursive_archive(name)
    reports = [
        asyncio.run(
            fetch_and_analyze(
                Archive(candles),
                sensitivity_config(
                    base_strategy=base,
                    parameters=[spec("entry.left.period", values=values)],
                    train_ratio=0.5,
                    execution=EXECUTION,
                ),
            )
        )
        for values in ([2], [2, 6])
    ]
    assert reports[0].split == reports[1].split
    assert reports[0].results[0].train.result == reports[1].results[0].train.result
    assert all("test" not in row.model_dump() for report in reports for row in report.results)
    assert (
        reports[0].shared_data.indicator_initializations[0]
        == reports[1].shared_data.indicator_initializations[0]
    )


def test_test_price_changes_never_influence_sensitivity_cost_totals() -> None:
    config = sensitivity_config(execution=EXECUTION)
    candles = history([10, 12, 8] * 9)
    cut = 3 + 16
    changed = candles[:cut] + [
        c.model_copy(update={"open": 1000, "high": 1000, "low": 1000, "close": 1000})
        for c in candles[cut:]
    ]
    first, second = run_sensitivity(candles, config), run_sensitivity(changed, config)
    assert first.results == second.results and first.summary == second.summary
    assert first.neighbors == second.neighbors and first.matrix == second.matrix


@pytest.mark.parametrize(
    "cls,alias", [(BacktestConfig, "trading_fee"), (MarketConfig, "fee"), (AIStrategyConfig, "fee")]
)
def test_direct_construction_normalizes_fee_without_pydantic_return_warning(
    cls: type[BacktestConfig] | type[MarketConfig] | type[AIStrategyConfig], alias: str
) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        config = cls(symbol="BTCUSDT", execution=ExecutionConfig(fee_rate=0.003))
    assert getattr(config, alias) == config.execution_config().fee_rate == 0.003
