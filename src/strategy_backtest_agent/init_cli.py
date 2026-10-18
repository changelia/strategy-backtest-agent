"""Validated, deterministic research templates; no credentials or prompts."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.models import BacktestConfig, Model
from strategy_backtest_agent.reports.cli import write_new
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

TYPES = ("backtest", "compare", "validate", "walk-forward")


def template(kind: str) -> Model:
    costs = {"fee_rate": 0.001, "spread_bps": 10.0, "slippage_bps": 5.0}
    if kind == "backtest":
        return BacktestConfig.model_validate({"execution": costs})
    strategies = [
        {
            "id": "rsi-30",
            "name": "Example RSI 14 30/70",
            "strategy": {"type": "rsi", "period": 14, "entry_below": 30.0, "exit_above": 70.0},
        },
    ]
    config: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "period_days": 30,
        "initial_balance": 10000.0,
        "fee": 0.001,
        "execution": costs,
        "evaluation_end": "2024-07-01T00:00:00Z",
        "strategies": strategies,
    }
    if kind == "compare":
        strategies.append(
            {
                "id": "rsi-25",
                "name": "Example RSI 14 25/70",
                "strategy": {"type": "rsi", "period": 14, "entry_below": 25.0, "exit_above": 70.0},
            }
        )
        model: type[Model] = ComparisonConfig
    elif kind == "validate":
        config["train_ratio"] = 0.7
        model = ValidationConfig
    elif kind == "walk-forward":
        config.update(
            period_days=60,
            stitch_oos=True,
            windows={
                "mode": "rolling",
                "train_days": 30,
                "test_days": 10,
                "step_days": 10,
                "max_folds": 10,
            },
        )
        model = WalkForwardConfig
    else:
        raise ValueError("unsupported template type")
    return model.model_validate_json(json.dumps(config))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest init",
        description="Create validated JSON research configurations without prompts or credentials.",
        epilog=(
            "Run backtest with --config FILE --days 180 --demo; other types with "
            "TYPE --config FILE --demo. Synthetic examples do not imply profitability. "
            "Existing files and symlink destinations are never overwritten."
        ),
    )
    parser.add_argument("--type", choices=TYPES, required=True, help="Target CLI workflow")
    parser.add_argument("--output", type=Path, required=True, help="New configuration file path")
    args = parser.parse_args(argv)
    try:
        content = template(args.type).model_dump_json(indent=2) + "\n"
        write_new(args.output, content)
    except (ValueError, OSError, ValidationError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(f"Created {args.type} configuration: {args.output}")
