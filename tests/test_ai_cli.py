import json
from datetime import datetime

import pytest
from conftest import make_candles

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.ai.parser import StrategyParseError
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError
from strategy_backtest_agent.models import Candle


def setup_flow(monkeypatch: pytest.MonkeyPatch, as_json: bool) -> AIStrategyConfig:
    parsed = AIStrategyConfig.model_validate(
        {
            "symbol": "ETHUSDT",
            "timeframe": "4h",
            "period_days": 90,
            "initial_balance": 5000,
            "fee": 0.002,
            "strategy": {"period": 2, "entry_below": 25, "exit_above": 65},
        }
    )

    def parse(text: str) -> AIStrategyConfig:
        assert text == "Backtest ETHUSDT on 4h for 90 days using RSI 25/65"
        return parsed

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        assert (symbol, timeframe) == ("ETHUSDT", "4h")
        assert (end - start).days == 90
        return make_candles([10, 9, 8, 12, 13], [10, 9, 8, 7, 15])

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(parser, "parse_strategy", parse)
    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "strategy-backtest",
            "ai",
            "Backtest ETHUSDT on 4h for 90 days using RSI 25/65",
            *(["--json"] if as_json else []),
        ],
    )
    return parsed


def test_ai_cli_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_flow(monkeypatch, False)
    main()
    output = capsys.readouterr()
    assert output.err == ""
    assert "AI Strategy" in output.out
    assert "Parsed Configuration:" in output.out
    assert "Symbol: ETHUSDT" in output.out
    assert "Period: 90 days" in output.out
    assert "Balance: 5,000.00" in output.out
    assert "Running backtest..." in output.out
    assert "Final Balance:" in output.out


def test_ai_json_matches_deterministic_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parsed = setup_flow(monkeypatch, True)
    main()
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert output.err == ""
    assert set(payload) == {"input", "parsed_strategy", "backtest_result"}
    assert payload["parsed_strategy"] == parsed.model_dump(mode="json")
    expected = run_backtest(
        make_candles([10, 9, 8, 12, 13], [10, 9, 8, 7, 15]), parsed.to_backtest_config()
    ).model_dump(mode="json")
    for key, value in expected.items():
        assert payload["backtest_result"][key] == value
    assert "instructions" not in output.out
    assert "resp_" not in output.out


@pytest.mark.parametrize("kind", ["parser", "market"])
def test_ai_cli_failures(
    kind: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_flow(monkeypatch, True)
    if kind == "parser":

        def fail(text: str) -> AIStrategyConfig:
            raise StrategyParseError("Request rejected: ambiguous")

        monkeypatch.setattr(parser, "parse_strategy", fail)
    else:

        async def fail_fetch(
            self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> list[Candle]:
            raise MarketDataError("market data unavailable")

        monkeypatch.setattr(BinanceMarketData, "fetch_candles", fail_fetch)
    with pytest.raises(SystemExit) as error:
        main()
    output = capsys.readouterr()
    assert error.value.code == 2
    assert output.out == ""
    assert "Error:" in output.err
    assert "Traceback" not in output.err


def test_ai_cli_missing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "ai", "Backtest BTCUSDT"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "OPENAI_API_KEY is missing" in capsys.readouterr().err
