"""Comparison CLI; config-file mode never imports the AI parser."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from strategy_backtest_agent.comparison.engine import fetch_and_compare
from strategy_backtest_agent.comparison.formatter import format_comparison
from strategy_backtest_agent.comparison.models import RANKING_CRITERIA, ComparisonConfig
from strategy_backtest_agent.execution_cli import add_cost_arguments, override_execution
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="strategy-backtest compare",
        description="Compare 2–5 long-only strategies on shared data",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("text", nargs="?", help="One quoted natural-language comparison request")
    source.add_argument(
        "--config", type=Path, help="Validated JSON configuration; no OpenAI key needed"
    )
    parser.add_argument("--json", action="store_true", help="Emit comparison results as JSON only")
    parser.add_argument(
        "--sort", choices=RANKING_CRITERIA, help="Override the configuration ranking"
    )
    add_cost_arguments(parser)
    args = parser.parse_args(argv)
    try:
        if args.config is not None:
            config = ComparisonConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        else:
            from strategy_backtest_agent.ai.parser import parse_comparison

            config = parse_comparison(args.text)
        if args.sort is not None:
            config = ComparisonConfig.model_validate({**config.model_dump(), "sort_by": args.sort})
        config = override_execution(config, args)
        result = asyncio.run(fetch_and_compare(BinanceMarketData(), config, data_source="binance"))
        if args.json:
            print(result.model_dump_json())
        else:
            print(format_comparison(result))
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors()
        )
        parser.exit(2, f"Error: Invalid comparison configuration: {messages}\n")
    except (ValueError, OverflowError, OSError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")
