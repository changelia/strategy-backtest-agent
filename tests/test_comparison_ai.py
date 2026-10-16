"""Single structured request for all strategies; no real API access."""

import json
from types import SimpleNamespace

import httpx2
import pytest
from test_ai_parser import install_transport, response_payload
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import ComparisonParserOutput
from strategy_backtest_agent.ai.parser import StrategyParseError, parse_comparison


def extraction(count: int = 2) -> dict[str, object]:
    rules = strategy(
        comparison(indicator()), comparison(indicator(), ">", {"type": "value", "value": 70})
    )
    return {
        "symbol": "BTCUSDT",
        "timeframe": None,
        "period_days": None,
        "initial_balance": None,
        "fee": None,
        "evaluation_end": None,
        "sort_by": None,
        "strategies": [{"name": f"RSI {i}", "strategy": rules.model_dump()} for i in range(count)],
    }


@pytest.mark.parametrize("count", [2, 3, 5])
def test_real_sdk_multiple_rules_one_request(count: int, monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["store"] is False
        assert "tools" not in body
        assert "inconsistent_settings" in body["instructions"]
        assert "transition events" in body["instructions"]
        schema = body["text"]["format"]["schema"]
        assert body["text"]["format"]["strict"] is True
        assert "oneOf" not in json.dumps(schema)
        assert schema["additionalProperties"] is False
        assert "ComparisonExtraction" in schema["$defs"]
        assert "RuleStrategy" in schema["$defs"]
        return httpx2.Response(
            200, json=response_payload({"configuration": extraction(count), "rejection": None})
        )

    install_transport(monkeypatch, handler)
    parsed = parse_comparison("Compare strategies on BTCUSDT")
    assert len(requests) == 1
    assert len(parsed.strategies) == count
    assert [item.id for item in parsed.strategies] == [f"strategy-{i}" for i in range(1, count + 1)]
    assert parsed.timeframe == "1h"
    assert parsed.period_days == 30
    assert parsed.fee == 0.001
    assert parsed.initial_balance == 10000
    assert parsed.evaluation_end is None


def test_compound_sma_and_explicit_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    compound = strategy(
        {
            "type": "and",
            "conditions": [
                comparison(indicator()),
                comparison({"type": "price"}, ">", indicator("ema", 200)),
            ],
        }
    )
    sma = strategy(
        comparison(indicator("sma", 20), ">", indicator("sma", 50)),
        comparison(indicator("sma", 20), "<", indicator("sma", 50)),
    )
    values = {
        **extraction(),
        "timeframe": "4h",
        "period_days": 90,
        "initial_balance": 5000,
        "fee": 0.002,
        "sort_by": "max_drawdown",
        "evaluation_end": "2024-04-01T04:00:00+04:00",
        "strategies": [
            {"name": "RSI and EMA", "strategy": compound.model_dump()},
            {"name": "SMA levels", "strategy": sma.model_dump()},
        ],
    }
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        ),
    )
    parsed = parse_comparison("Compare compound and SMA strategies on BTCUSDT")
    assert parsed.strategies[0].to_rules() == compound
    assert parsed.strategies[1].to_rules() == sma
    assert parsed.initial_balance == 5000
    assert parsed.fee == 0.002
    assert parsed.evaluation_end is not None
    assert parsed.evaluation_end.isoformat() == "2024-04-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "reason", ["unsupported", "ambiguous", "inconsistent_settings", "strategy_count"]
)
def test_model_rejections(reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": None, "rejection": reason})
        ),
    )
    with pytest.raises(StrategyParseError, match=reason.replace("_", " ")):
        parse_comparison("Compare BTCUSDT on 1h versus 4h with different capital and fees")


@pytest.mark.parametrize("kind", ["single", "six", "balance", "override", "macd", "winner"])
def test_invalid_structured_response(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    values = extraction(1 if kind == "single" else 6 if kind == "six" else 2)
    if kind == "balance":
        values["initial_balance"] = 0
    if kind == "override":
        values["strategies"] = [
            {
                "name": "RSI",
                "strategy": strategy(comparison(indicator())).model_dump(),
                "symbol": "ETHUSDT",
            }
        ] * 2
    if kind == "macd":
        values["strategies"] = [{"name": "MACD", "strategy": {"type": "macd"}}] * 2
    if kind == "winner":
        values["winner"] = "RSI"
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="Invalid parsed|validated"):
        parse_comparison("Compare BTCUSDT strategies")


@pytest.mark.parametrize(
    "text",
    [
        "Compare Ichimoku and RSI on BTCUSDT",
        "Compare SMA 20 crosses above SMA 50 and RSI on BTCUSDT",
        "Compare shorts and RSI on BTCUSDT",
        "Compare short selling and RSI on BTCUSDT",
        "Compare 10x leverage and RSI on BTCUSDT",
    ],
)
def test_unsupported_requests_do_not_call_api(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("unsupported request must not call OpenAI")

    monkeypatch.setattr(parser, "create_client", forbidden)
    with pytest.raises(StrategyParseError, match="Unsupported|unsupported"):
        parse_comparison(text)


@pytest.mark.parametrize("text", ["", "  ", "x" * 8001])
def test_input_limits(text: str) -> None:
    with pytest.raises(StrategyParseError, match="empty|8000"):
        parse_comparison(text)


def test_symbol_not_invented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": extraction(), "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="explicitly present"):
        parse_comparison("Compare two Bitcoin strategies")


def test_constructed_sdk_output_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        responses = SimpleNamespace(
            parse=lambda **_: SimpleNamespace(
                status="completed",
                output_parsed=ComparisonParserOutput.model_construct(
                    configuration=None, rejection=None
                ),
            )
        )

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(parser, "create_client", FakeClient)
    with pytest.raises(StrategyParseError, match="Invalid parsed"):
        parse_comparison("Compare BTCUSDT strategies")


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StrategyParseError, match="OPENAI_API_KEY"):
        parse_comparison("Compare RSI 25/70 and RSI 30/70 on BTCUSDT")
