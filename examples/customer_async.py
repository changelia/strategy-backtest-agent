"""Offline awaitable API. In a notebook use `await research()` instead of asyncio.run."""

import asyncio

from strategy_backtest_agent import BacktestClient, BacktestConfig


async def research() -> None:
    client = BacktestClient()
    config = BacktestConfig(rsi_period=14, entry_rsi=30.0, exit_rsi=70.0)
    # These synchronous operations do not use an asyncio.run wrapper.
    print("Offline:", client.doctor().offline_ready)
    result = await client.arun(config=config, days=30, demo=True)
    print(result.summary())
    await client.areport(result, output="async-report.md")
    await client.areport(result, format="json", output="async-report.json")
    print("Saved async-report.md and async-report.json")


if __name__ == "__main__":
    asyncio.run(research())
