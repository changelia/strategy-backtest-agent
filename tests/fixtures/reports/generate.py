"""Run with PYTHONPATH pointing to a tagged checkout's src; never imports report code.

See README.md for exact provenance and regeneration commands. No network calls.
"""

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import run_comparison
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.costs.engine import run_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import dependencies, prepare_context
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity.engine import run_sensitivity
from strategy_backtest_agent.sensitivity.models import SensitivityConfig
from strategy_backtest_agent.validation.engine import run_validation
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.engine import run_walk_forward
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

START = datetime(2024, 1, 1, tzinfo=UTC)
spec = {"type": "indicator", "name": "rsi", "period": 14}
rule = RuleStrategy.model_validate(
    {
        "entry": {
            "type": "comparison",
            "left": spec,
            "operator": "<",
            "right": {"type": "value", "value": 30.0},
        },
        "exit": {
            "type": "comparison",
            "left": spec,
            "operator": ">",
            "right": {"type": "value", "value": 70.0},
        },
    }
)
source = []
for i in range(-15, 96):
    price = 100 + 20 * math.sin(i / 5)
    source.append(
        Candle(
            timestamp=START + timedelta(hours=i),
            open=price,
            high=price + 5,
            low=price - 5,
            close=price,
            volume=1,
        )
    )
base = {
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "period_days": 4,
    "evaluation_end": START + timedelta(days=4),
    "initial_balance": 1000,
    "fee": 0.001,
    "execution": {"spread_bps": 10, "slippage_bps": 5},
}
named = {"id": "rsi", "name": "RSI 14", "strategy": rule}
wf = WalkForwardConfig.model_validate(
    {
        **base,
        "strategies": [named],
        "windows": {"train_days": 1, "test_days": 1},
        "stitch_oos": True,
    }
)
comp = ComparisonConfig.model_validate({**base, "strategies": [named, {**named, "id": "baseline"}]})
val = ValidationConfig.model_validate({**base, "strategies": [named]})
sens = SensitivityConfig.model_validate(
    {
        **base,
        "base_strategy": rule,
        "parameters": [{"path": "entry.right.value", "values": [30.0, 35.0]}],
    }
)
cost = CostScenarioConfig.model_validate(
    {
        **{k: v for k, v in base.items() if k != "execution"},
        "strategy": rule,
        "scenarios": [
            {"id": "base", "name": "base"},
            {"id": "costs", "name": "costs", "spread_bps": 10, "slippage_bps": 5},
        ],
    }
)
output = Path(sys.argv[1])
fixture_source = "synthetic offline versioned fixture"
for name, report in [
    ("comparison", run_comparison(source, comp, data_source=fixture_source)),
    ("validation", run_validation(source, val, data_source=fixture_source)),
    ("sensitivity", run_sensitivity(source, sens, data_source=fixture_source)),
    ("costs", run_cost_scenarios(source, cost, data_source=fixture_source)),
    ("walk_forward", run_walk_forward(source, wf, data_source=fixture_source)),
]:
    (output / f"{name}.json").write_text(report.model_dump_json(indent=2) + "\n")
result = run_backtest(
    source,
    wf.to_backtest_config(),
    rule,
    evaluation_start=15,
    context=prepare_context(source, dependencies(rule)),
)
standard = {
    **result.model_dump(mode="json"),
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "period_days": 4,
    "data_source": "synthetic offline versioned fixture",
    "candle_count": 96,
    "start_time": source[15].timestamp.isoformat(),
    "end_time": source[-1].timestamp.isoformat(),
    "strategy": rule.model_dump(mode="json"),
    "trading_fee": 0.001,
    "indicator_configuration": [{"name": "rsi", "period": 14}],
}
(output / "backtest.json").write_text(json.dumps(standard, indent=2) + "\n")
