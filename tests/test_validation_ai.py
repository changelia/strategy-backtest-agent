"""Mocked real SDK structured validation parsing; no network or performance generation."""

import json
from types import SimpleNamespace

import httpx2
import pytest
from test_ai_parser import install_transport, response_payload
from test_comparison_ai import extraction

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import ValidationParserOutput
from strategy_backtest_agent.ai.parser import StrategyParseError, parse_validation


def values(count: int = 2) -> dict[str, object]:
    result = extraction(count)
    result.pop("sort_by")
    return {**result, "train_ratio": None}


@pytest.mark.parametrize("count", [1, 2, 5])
def test_one_real_sdk_request_strict_schema_defaults(
    count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["store"] is False
        assert "tools" not in body
        assert "held-out" in body["instructions"]
        assert "select a strategy" in body["instructions"]
        schema = body["text"]["format"]["schema"]
        assert body["text"]["format"]["strict"] is True
        assert "oneOf" not in json.dumps(schema)
        assert schema["additionalProperties"] is False
        assert "ValidationExtraction" in schema["$defs"]
        assert "RuleStrategy" in schema["$defs"]
        assert "sort_by" not in json.dumps(schema)
        return httpx2.Response(
            200, json=response_payload({"configuration": values(count), "rejection": None})
        )

    install_transport(monkeypatch, handler)
    parsed = parse_validation("Validate RSI strategies on BTCUSDT")
    assert len(requests) == 1
    assert len(parsed.strategies) == count
    assert [s.id for s in parsed.strategies] == [f"strategy-{i}" for i in range(1, count + 1)]
    assert parsed.train_ratio == 0.7
    assert parsed.timeframe == "1h" and parsed.period_days == 30
    assert parsed.initial_balance == 10000 and parsed.fee == 0.001


def test_explicit_settings_and_utc_end(monkeypatch: pytest.MonkeyPatch) -> None:
    output = {
        **values(),
        "train_ratio": 0.8,
        "period_days": 180,
        "timeframe": "4h",
        "initial_balance": 5000,
        "fee": 0.002,
        "evaluation_end": "2024-04-01T04:00:00+04:00",
    }
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": output, "rejection": None})
        ),
    )
    config = parse_validation("Validate RSI on BTCUSDT over 180 days using 80/20 on 4h")
    assert config.train_ratio == 0.8 and config.period_days == 180
    assert config.timeframe == "4h" and config.initial_balance == 5000 and config.fee == 0.002
    assert config.evaluation_end is not None
    assert config.evaluation_end.isoformat() == "2024-04-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "reason",
    ["unsupported", "ambiguous", "missing_symbol", "inconsistent_settings", "strategy_count"],
)
def test_rejections(reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": None, "rejection": reason})
        ),
    )
    with pytest.raises(StrategyParseError, match=reason.replace("_", " ")):
        parse_validation("Validate BTCUSDT strategies")


@pytest.mark.parametrize("kind", ["ratio", "empty", "six", "performance", "code", "override"])
def test_invalid_extracted_config(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    output = values(0 if kind == "empty" else 6 if kind == "six" else 2)
    if kind == "ratio":
        output["train_ratio"] = 0.95
    elif kind == "performance":
        output["return_percent"] = 200
    elif kind == "code":
        output["python"] = "print('profits')"
    elif kind == "override":
        output["strategies"] = [{"name": "RSI", "strategy": {"type": "rsi"}, "symbol": "ETHUSDT"}]
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": output, "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="Invalid parsed|validated"):
        parse_validation("Validate RSI on BTCUSDT")


@pytest.mark.parametrize(
    "text",
    [
        "Validate Ichimoku on BTCUSDT",
        "Validate SMA crosses above on BTCUSDT",
        "Validate with random split on BTCUSDT",
        "Validate by shuffling BTCUSDT",
        "Optimize RSI on BTCUSDT",
        "Tune thresholds on BTCUSDT",
        "Walk-forward BTCUSDT",
        "Validate BTCUSDT with multiple folds",
        "Choose best Test strategy on BTCUSDT",
        "Validate robustness score on BTCUSDT",
        "Predict future BTCUSDT profitability",
    ],
)
def test_unsupported_before_api(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("must reject before API")

    monkeypatch.setattr(parser, "create_client", forbidden)
    with pytest.raises(StrategyParseError, match="Unsupported|unsupported"):
        parse_validation(text)


@pytest.mark.parametrize("text", ["", "  ", "x" * 8001])
def test_input_limits(text: str) -> None:
    with pytest.raises(StrategyParseError, match="empty|8000"):
        parse_validation(text)


def test_symbol_not_invented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": values(), "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="explicitly present"):
        parse_validation("Validate RSI on Bitcoin")


def test_constructed_output_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        responses = SimpleNamespace(
            parse=lambda **_: SimpleNamespace(
                status="completed",
                output_parsed=ValidationParserOutput.model_construct(
                    configuration=None, rejection=None
                ),
            )
        )

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(parser, "create_client", Client)
    with pytest.raises(StrategyParseError, match="Invalid parsed"):
        parse_validation("Validate RSI on BTCUSDT")


def test_no_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StrategyParseError, match="OPENAI_API_KEY"):
        parse_validation("Validate RSI on BTCUSDT")
