"""Execution scenarios from validated JSON only; no OpenAI imports or credentials."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from strategy_backtest_agent.costs.engine import fetch_and_run_costs
from strategy_backtest_agent.costs.formatter import format_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest costs", description="Frozen-strategy Train cost scenarios"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = CostScenarioConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        report = asyncio.run(
            fetch_and_run_costs(BinanceMarketData(), config, data_source="binance")
        )
        print(report.model_dump_json() if args.json else format_cost_scenarios(report))
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors()
        )
        parser.exit(2, f"Error: Invalid cost scenario configuration: {messages}\n")
    except (ValueError, OverflowError, OSError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")
