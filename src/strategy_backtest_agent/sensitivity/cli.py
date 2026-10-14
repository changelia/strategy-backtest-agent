"""Sensitivity CLI; config-file mode never imports the AI parser."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from strategy_backtest_agent.execution_cli import add_cost_arguments, override_execution
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError
from strategy_backtest_agent.sensitivity.engine import fetch_and_analyze
from strategy_backtest_agent.sensitivity.formatter import format_sensitivity
from strategy_backtest_agent.sensitivity.models import SensitivityConfig


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest sensitivity",
        description="Analyze a bounded parameter grid on Train only",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("text", nargs="?", help="One quoted natural-language sensitivity request")
    source.add_argument(
        "--config", type=Path, help="Validated JSON configuration; no OpenAI key needed"
    )
    parser.add_argument("--json", action="store_true", help="Emit sensitivity results as JSON only")
    add_cost_arguments(parser)
    args = parser.parse_args(argv)
    try:
        if args.config is not None:
            config = SensitivityConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        else:
            from strategy_backtest_agent.ai.parser import parse_sensitivity

            config = parse_sensitivity(args.text)
        config = override_execution(config, args)
        result = asyncio.run(fetch_and_analyze(BinanceMarketData(), config, data_source="binance"))
        if args.json:
            print(result.model_dump_json())
        else:
            print(format_sensitivity(result))
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors()
        )
        parser.exit(2, f"Error: Invalid sensitivity configuration: {messages}\n")
    except (ValueError, OverflowError, OSError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")
