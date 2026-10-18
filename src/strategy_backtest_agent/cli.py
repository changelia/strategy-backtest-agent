"""Terminal and JSON entry point for historical strategy backtests."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic import ValidationError

from strategy_backtest_agent.execution import format_costs, format_execution
from strategy_backtest_agent.market_data import TIMEFRAMES, BinanceMarketData, MarketDataError
from strategy_backtest_agent.models import BacktestConfig
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.services import backtest_payload, execute_backtest


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


async def _run(
    config: BacktestConfig,
    days: int,
    demo: bool,
    as_json: bool,
    ai_context: dict[str, object] | None = None,
    strategy: RuleStrategy | None = None,
) -> None:
    execution = await execute_backtest(
        config, days, demo=demo, strategy=strategy, provider=BinanceMarketData()
    )
    candles, result, boundary = (
        execution.evaluation_candles,
        execution.result,
        execution.evaluation_start,
    )
    if as_json:
        payload = backtest_payload(execution)
        if ai_context is not None:
            payload = {**ai_context, "backtest_result": payload}
        print(json.dumps(payload, allow_nan=False))
        return
    print("Strategy Backtest\n" + "─" * 32)
    print(f"Symbol: {config.symbol}\nTimeframe: {config.timeframe}\nPeriod: {days} days")
    print(f"Data: {'synthetic offline demo' if demo else 'Binance'} ({len(candles)} candles)")
    print(f"Range (candle opens, UTC): {candles[0].timestamp} → {candles[-1].timestamp}")
    if strategy is None:
        print(f"\nStrategy: RSI\nRSI Period: {config.rsi_period}")
        print(f"Entry RSI: < {config.entry_rsi:g}\nExit RSI: > {config.exit_rsi:g}")
    else:
        print(f"Warm-up: {boundary} prior candles (excluded from trades and metrics)")
        print(f"\nENTRY: {format_rule(strategy.entry)}")
        print(f"EXIT: {format_rule(strategy.exit)}")
    print(f"Fee per side: {config.trading_fee * 100:g}%\n\nResults (quote currency)")
    print(f"Initial Balance: {result.initial_balance:,.2f}")
    print(f"Final Balance: {result.final_balance:,.2f}")
    print(f"Total Return: {_percent(result.total_return_percent)}")
    print(f"Buy & Hold: {_percent(result.buy_and_hold_return_percent)}")
    print(f"Trades: {result.total_trades}")
    print(f"Winning Trades: {result.winning_trades}\nLosing Trades: {result.losing_trades}")
    print(f"Win Rate: {_percent(result.win_rate)}")
    print(f"Max Drawdown: {_percent(result.max_drawdown_percent)}")
    factor = (
        "N/A (no losing trades)" if result.profit_factor is None else f"{result.profit_factor:.2f}"
    )
    print(f"Profit Factor: {factor}")
    print(format_execution(config.execution_config()))
    print(format_costs(result.costs))
    for warning in result.execution_warnings:
        print(warning)


def main() -> None:
    """Load local settings once, then dispatch the requested CLI command."""
    if sys.argv[1:2] == ["doctor"]:
        from strategy_backtest_agent.doctor import main as doctor_main

        doctor_main(sys.argv[2:])
        return
    load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=False)
    if sys.argv[1:2] == ["init"]:
        from strategy_backtest_agent.init_cli import main as init_main

        init_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["report"]:
        from strategy_backtest_agent.reports.cli import main as report_main

        report_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["walk-forward"]:
        from strategy_backtest_agent.walk_forward.cli import main as walk_forward_main

        walk_forward_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["costs"]:
        from strategy_backtest_agent.costs.cli import main as costs_main

        costs_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["sensitivity"]:
        from strategy_backtest_agent.sensitivity.cli import main as sensitivity_main

        sensitivity_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["validate"]:
        from strategy_backtest_agent.validation.cli import main as validation_main

        validation_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["compare"]:
        from strategy_backtest_agent.comparison.cli import main as comparison_main

        comparison_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["ai"]:
        _ai_main()
        return
    parser = argparse.ArgumentParser(
        description="Backtest a long-only RSI strategy",
        epilog=(
            "Templates: strategy-backtest init --help. Diagnostics: strategy-backtest doctor. "
            'Natural language: strategy-backtest ai "Backtest BTCUSDT" [--json]'
        ),
    )
    parser.add_argument("--config", type=Path, help="BacktestConfig JSON; duration uses --days")
    parser.add_argument("--symbol", default="BTCUSDT", help="Uppercase provider symbol (BTCUSDT)")
    parser.add_argument(
        "--timeframe", choices=TIMEFRAMES, default="1h", help="Candle interval (1h)"
    )
    parser.add_argument(
        "--days", type=int, default=180, help="Previous calendar days, positive (180)"
    )
    parser.add_argument(
        "--balance", type=float, default=10000, help="Positive quote-currency cash (10000)"
    )
    parser.add_argument(
        "--fee",
        "--trading-fee",
        dest="fee",
        type=float,
        default=0.001,
        help="Fee fraction per entry/exit, 0 <= fee < 1 (0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--rsi-period", type=int, default=14, help="Positive Wilder RSI period (14)"
    )
    parser.add_argument(
        "--entry-rsi", type=float, default=30, help="Buy below threshold, 0–100 (30)"
    )
    parser.add_argument(
        "--exit-rsi", type=float, default=70, help="Sell above threshold, 0–100 (70)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit valid JSON only; undefined metrics are null"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Use deterministic synthetic offline candles"
    )
    from strategy_backtest_agent.execution_cli import add_cost_arguments

    add_cost_arguments(parser)
    args = parser.parse_args()
    try:
        if args.days <= 0:
            raise ValueError("days must be positive")
        if args.config is not None:
            incompatible = {
                "--symbol",
                "--timeframe",
                "--balance",
                "--fee",
                "--trading-fee",
                "--rsi-period",
                "--entry-rsi",
                "--exit-rsi",
            }
            if any(
                token.startswith("--")
                and any(flag.startswith(token.split("=", 1)[0]) for flag in incompatible)
                for token in sys.argv[1:]
            ):
                raise ValueError("--config cannot be combined with legacy strategy/account flags")
            config = BacktestConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
            from strategy_backtest_agent.execution_cli import override_execution

            config = override_execution(config, args)
        else:
            config = BacktestConfig.model_validate(
                {
                    "symbol": args.symbol,
                    "timeframe": args.timeframe,
                    "initial_balance": args.balance,
                    "trading_fee": args.fee,
                    "execution": {
                        "fee_rate": args.fee,
                        "spread_bps": args.spread_bps or 0,
                        "slippage_bps": args.slippage_bps or 0,
                    },
                    "rsi_period": args.rsi_period,
                    "entry_rsi": args.entry_rsi,
                    "exit_rsi": args.exit_rsi,
                }
            )
        asyncio.run(_run(config, args.days, args.demo, args.json))
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'config'}: {error['msg']}"
            for error in exc.errors()
        )
        parser.exit(2, f"Error: {messages}\n")
    except (ValueError, OverflowError, OSError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")


def _ai_main() -> None:
    """Parse natural language before invoking the existing historical execution path."""
    from strategy_backtest_agent.ai.parser import StrategyParseError, parse_strategy

    parser = argparse.ArgumentParser(
        prog="strategy-backtest ai",
        description="Parse long-only RSI, SMA, EMA, MACD, Bollinger or ATR rules",
    )
    parser.add_argument(
        "text", help="Natural-language historical backtest request (one quoted argument)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit input, parsed_strategy, and backtest_result as JSON",
    )
    from strategy_backtest_agent.execution_cli import add_cost_arguments, override_execution

    add_cost_arguments(parser)
    args = parser.parse_args(sys.argv[2:])
    try:
        parsed = override_execution(parse_strategy(args.text), args)
        context: dict[str, object] = {
            "input": args.text,
            "parsed_strategy": parsed.model_dump(mode="json"),
        }
        if not args.json:
            print("AI Strategy\n" + "─" * 32)
            print(f"Input:\n{args.text}\n\nParsed Configuration:")
            print(f"Symbol: {parsed.symbol}\nTimeframe: {parsed.timeframe}")
            print(f"Period: {parsed.period_days} days\nBalance: {parsed.initial_balance:,.2f}")
            if isinstance(parsed.strategy, RuleStrategy):
                print(f"ENTRY:\n  {format_rule(parsed.strategy.entry)}")
                print(f"EXIT:\n  {format_rule(parsed.strategy.exit)}")
            else:
                print(f"RSI Period: {parsed.strategy.period}")
                print(f"Entry RSI: < {parsed.strategy.entry_below:g}")
                print(f"Exit RSI: > {parsed.strategy.exit_above:g}")
            print(f"Fee: {parsed.fee * 100:g}%")
            print("\nRunning backtest...\n")
        asyncio.run(
            _run(
                parsed.to_backtest_config(),
                parsed.period_days,
                False,
                args.json,
                context,
                parsed.strategy if isinstance(parsed.strategy, RuleStrategy) else None,
            )
        )
    except (StrategyParseError, MarketDataError, ValueError, OverflowError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
