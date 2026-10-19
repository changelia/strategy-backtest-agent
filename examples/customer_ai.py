"""Paid OpenAI parsing, followed by offline synthetic research. No Binance request.

Set OPENAI_API_KEY before running. Review the printed configuration before accepting
its use in further research. A key alone never triggers a request at construction.
"""

from pathlib import Path

from strategy_backtest_agent import AIStrategyConfig, BacktestClient

client = BacktestClient(model="gpt-4.1-mini")
config = client.parse(
    "Backtest BTCUSDT on 1h candles for 30 days with initial balance 10000, "
    "fee 0.001 per side, full spread 10 bps and slippage 5 bps per side. "
    "Buy when RSI(14) < 30 and sell when RSI(14) > 70."
)
assert isinstance(config, AIStrategyConfig)
print("Inspect symbol, duration, rules, balance and execution costs:")
print(config.model_dump_json(indent=2))
# This execution uses synthetic data; the parse above still calls paid OpenAI.
result = client.run(config=config, demo=True)
print(result.summary())
with Path("ai-result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("ai-report.md")
result.save_report("ai-report.json", format="json")
print("Saved ai-result.json, ai-report.md and ai-report.json")
