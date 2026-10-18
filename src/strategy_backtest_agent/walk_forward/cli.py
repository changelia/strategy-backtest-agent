"""Walk-forward CLI; config-file mode never imports the AI parser."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from strategy_backtest_agent.demo import research_demo_candles
from strategy_backtest_agent.execution_cli import add_cost_arguments, override_execution
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError
from strategy_backtest_agent.walk_forward.engine import fetch_and_walk_forward, run_walk_forward
from strategy_backtest_agent.walk_forward.formatter import format_walk_forward
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest walk-forward",
        description="Validate 1–5 long-only strategies on shared data",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("text", nargs="?", help="One quoted natural-language walk-forward request")
    source.add_argument(
        "--config", type=Path, help="Validated JSON configuration; no OpenAI key needed"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit walk-forward results as JSON only"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use fixed synthetic offline candles; not a profitability example",
    )
    add_cost_arguments(parser)
    args = parser.parse_args(argv)
    try:
        if args.demo and args.config is None:
            raise ValueError("--demo requires --config; natural-language mode may contact OpenAI")
        if args.config is not None:
            config = WalkForwardConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        else:
            from strategy_backtest_agent.ai.parser import parse_walk_forward

            config = parse_walk_forward(args.text)
        config = override_execution(config, args)
        if args.demo:
            result = run_walk_forward(
                research_demo_candles(config), config, data_source="synthetic_demo"
            )
        else:
            result = asyncio.run(
                fetch_and_walk_forward(BinanceMarketData(), config, data_source="binance")
            )
        if args.json:
            print(result.model_dump_json())
        else:
            print(format_walk_forward(result))
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors()
        )
        parser.exit(2, f"Error: Invalid walk-forward configuration: {messages}\n")
    except (ValueError, OverflowError, OSError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")
