"""Real SDK schema generation and parsing over mocked HTTP, plus rule CLI JSON."""

import json
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from conftest import make_candles
from test_ai_parser import extraction, install_transport, response_payload
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.ai.parser import StrategyParseError, parse_strategy
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import Candle


@pytest.mark.parametrize("kind", ["compound", "sma", "nested"])
def test_sdk_recursive_rules_and_defaults(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    rsi = comparison(indicator(), "<")
    ema = comparison({"type": "price"}, ">", indicator("ema", 200))
    entry = {
        "compound": {"type": "and", "conditions": [rsi, ema]},
        "sma": comparison(indicator("sma", 20), ">", indicator("sma", 50)),
        "nested": {"type": "or", "conditions": [rsi, {"type": "and", "conditions": [rsi, ema]}]},
    }[kind]
    rules = strategy(entry, comparison(indicator(), ">", {"type": "value", "value": 70}))

    def handler(request: httpx2.Request) -> httpx2.Response:
        schema = json.loads(request.content)["text"]["format"]["schema"]
        assert "oneOf" not in json.dumps(schema)
        assert "discriminator" not in json.dumps(schema)
        assert "RuleStrategy" in schema["$defs"]
        assert "Group" in schema["$defs"]
        assert schema["$defs"]["Group"]["additionalProperties"] is False
        return httpx2.Response(
            200,
            json=response_payload(
                {"configuration": extraction(strategy=rules.model_dump()), "rejection": None}
            ),
        )

    install_transport(monkeypatch, handler)
    parsed = parse_strategy("Backtest BTCUSDT using specified rules")
    assert parsed.strategy == rules
    assert (parsed.timeframe, parsed.period_days, parsed.initial_balance) == ("1h", 30, 10000)


@pytest.mark.parametrize(
    "bad",
    [
        comparison(indicator("macd", 14)),
        comparison(indicator("ema", 1001)),
        comparison({"type": "price"}, "crosses_above"),
        {"type": "and", "conditions": []},
    ],
)
def test_invalid_rule_response(bad: object, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": extraction(
                        strategy={"type": "rules", "entry": bad, "exit": bad}
                    ),
                    "rejection": None,
                }
            ),
        ),
    )
    with pytest.raises(StrategyParseError, match="validated|Invalid"):
        parse_strategy("Backtest BTCUSDT")


@pytest.mark.parametrize("as_json", [True, False])
def test_compound_cli(
    as_json: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = strategy(
        {
            "type": "and",
            "conditions": [
                comparison({"type": "price"}, ">", indicator("ema", 2)),
                comparison(indicator("rsi", 2), ">", {"type": "value", "value": 30}),
            ],
        }
    )
    config = AIStrategyConfig(symbol="BTCUSDT", period_days=1, strategy=rules)
    monkeypatch.setattr(parser, "parse_strategy", lambda _: config)
    requests: list[tuple[datetime, datetime]] = []

    async def provider(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        requests.append((start, end))
        # Start may be between hours. Return exactly the contained, completed hourly candles.
        first = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        source = make_candles(list(range(10, 45)))
        return [
            c.model_copy(update={"timestamp": first + timedelta(hours=i)})
            for i, c in enumerate(source)
            if first + timedelta(hours=i + 1) <= end
        ]

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", provider)
    monkeypatch.setattr(
        "sys.argv",
        ["strategy-backtest", "ai", "Backtest BTCUSDT", *(["--json"] if as_json else [])],
    )
    main()
    output = capsys.readouterr()
    assert not output.err
    assert len(requests) == 1  # never per candle, never duplicate fetch
    assert requests[0][1] - requests[0][0] == timedelta(hours=34)
    if as_json:
        result = json.loads(output.out)
        assert result["parsed_strategy"]["strategy"] == rules.model_dump()
        backtest = result["backtest_result"]
        assert backtest["evaluation_period"]["warmup_candles"] == 10
        assert backtest["candle_count"] == 23
        assert datetime.fromisoformat(backtest["start_time"]).tzinfo == UTC
        assert backtest["indicator_configuration"] == [
            {"name": "ema", "period": 2},
            {"name": "rsi", "period": 2},
        ]
    else:
        assert "PRICE > EMA(2) AND RSI(2) > 30" in output.out
        assert "Running backtest..." in output.out
