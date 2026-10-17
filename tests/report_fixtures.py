"""Offline native-result adapters, grounding, security and report determinism."""

from typing import Any

from test_comparison_engine import named
from test_rules import comparison, strategy
from test_validation_engine import ALWAYS, PRICE, ZERO
from test_walk_forward import history, settings

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import run_comparison
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.costs.engine import run_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig
from strategy_backtest_agent.sensitivity.engine import run_sensitivity
from strategy_backtest_agent.sensitivity.models import SensitivityConfig
from strategy_backtest_agent.validation.engine import run_validation
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.engine import run_walk_forward


def make_native_results() -> dict[str, dict[str, Any]]:
    config = settings(fee=0.01, execution={"spread_bps": 20, "slippage_bps": 10}, stitch_oos=True)
    source = history(config, [10, 10, 10, 20, 10, 5, 10, 10])
    source = [
        c.model_copy(update={"open": 10, "high": max(10, c.close), "low": min(10, c.close)})
        for c in source
    ]
    base = config.model_dump(exclude={"windows", "stitch_oos"})
    never = strategy(comparison(PRICE, "<", ZERO))
    single = run_backtest(source, config.to_backtest_config(), ALWAYS)
    standard = {
        **single.model_dump(mode="json"),
        "symbol": "BTCUSDT",
        "timeframe": "12h",
        "period_days": 4,
        "data_source": "synthetic offline audit",
        "candle_count": 8,
        "start_time": source[0].timestamp.isoformat(),
        "end_time": source[-1].timestamp.isoformat(),
        "strategy": ALWAYS.model_dump(mode="json"),
        "trading_fee": 0.01,
        "indicator_configuration": [],
    }
    comparison_config = ComparisonConfig.model_validate(
        {**base, "strategies": [named("always", ALWAYS), named("never", never)]}
    )
    sensitivity_config = SensitivityConfig.model_validate(
        {
            **{k: v for k, v in base.items() if k != "strategies"},
            "base_strategy": ALWAYS,
            "parameters": [{"path": "entry.right.value", "values": [100, 200]}],
            "train_ratio": 0.5,
        }
    )
    costs_config = CostScenarioConfig.model_validate(
        {
            **{k: v for k, v in base.items() if k not in ("strategies", "execution")},
            "strategy": ALWAYS,
            "train_ratio": 0.5,
            "scenarios": [
                {"id": "base", "name": "baseline"},
                {"id": "costs", "name": "modeled costs", "spread_bps": 20, "slippage_bps": 10},
            ],
        }
    )
    return {
        "backtest": standard,
        "comparison": run_comparison(
            source, comparison_config, data_source="synthetic offline audit"
        ).model_dump(mode="json"),
        "validation": run_validation(
            source,
            ValidationConfig.model_validate({**base, "train_ratio": 0.5}),
            data_source="synthetic offline audit",
        ).model_dump(mode="json"),
        "sensitivity": run_sensitivity(
            source, sensitivity_config, data_source="synthetic offline audit"
        ).model_dump(mode="json"),
        "costs": run_cost_scenarios(
            source, costs_config, data_source="synthetic offline audit"
        ).model_dump(mode="json"),
        "walk_forward": run_walk_forward(
            source, config, data_source="synthetic offline audit"
        ).model_dump(mode="json"),
    }
