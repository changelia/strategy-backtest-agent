"""Terminal and JSON entry point for historical RSI backtests."""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.market_data import TIMEFRAMES, BinanceMarketData, MarketDataError
from strategy_backtest_agent.models import BacktestConfig


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


async def _run(config: BacktestConfig, days: int, demo: bool, as_json: bool) -> None:
    end = datetime.now(UTC)
    candles = (
        demo_candles(config.timeframe, days)
        if demo
        else await BinanceMarketData().fetch_candles(
            config.symbol, config.timeframe, end - timedelta(days=days), end
        )
    )
    if len(candles) <= config.rsi_period:
        raise ValueError("not enough completed candles to calculate RSI; increase days")
    result = run_backtest(candles, config)
    if as_json:
        payload = {
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "period_days": days,
            "data_source": "synthetic_demo" if demo else "binance",
            "candle_count": len(candles),
            "start_time": candles[0].timestamp.isoformat().replace("+00:00", "Z"),
            "end_time": candles[-1].timestamp.isoformat().replace("+00:00", "Z"),
            "strategy": {
                "name": "RSI",
                "rsi_period": config.rsi_period,
                "entry_rsi": config.entry_rsi,
                "exit_rsi": config.exit_rsi,
                "fee": config.trading_fee,
            },
            **result.model_dump(mode="json"),
        }
        print(json.dumps(payload, allow_nan=False))
        return
    print("Strategy Backtest\n" + "─" * 32)
    print(f"Symbol: {config.symbol}\nTimeframe: {config.timeframe}\nPeriod: {days} days")
    print(f"Data: {'synthetic offline demo' if demo else 'Binance'} ({len(candles)} candles)")
    print(f"Range (candle opens, UTC): {candles[0].timestamp} → {candles[-1].timestamp}")
    print(f"\nStrategy: RSI\nRSI Period: {config.rsi_period}")
    print(f"Entry RSI: < {config.entry_rsi:g}\nExit RSI: > {config.exit_rsi:g}")
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


def main() -> None:
    """Validate CLI input and run a single historical backtest."""
    parser = argparse.ArgumentParser(description="Backtest a long-only RSI strategy")
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
    args = parser.parse_args()
    try:
        if args.days <= 0:
            raise ValueError("days must be positive")
        config = BacktestConfig.model_validate(
            {
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "initial_balance": args.balance,
                "trading_fee": args.fee,
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
    except (ValueError, OverflowError, MarketDataError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
