"""Mocked real structured SDK parsing: one configuration request, no market data."""

import json
from types import SimpleNamespace

import httpx2
import pytest
from test_ai_parser import install_transport, response_payload
from test_sensitivity_grid import RSI, spec

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import SensitivityParserOutput
from strategy_backtest_agent.ai.parser import StrategyParseError, parse_sensitivity


def extraction() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": None,
        "period_days": None,
        "initial_balance": None,
        "fee": None,
        "evaluation_end": None,
        "train_ratio": None,
        "base_strategy": RSI.model_dump(),
        "parameters": [spec().model_dump()],
    }


def test_real_sdk_one_strict_request_nearby_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    values = extraction()
    values["parameters"] = [
        {
            "path": "entry.right.value",
            "coupled_paths": [],
            "values": None,
            "range": None,
            "nearby": {"step": None, "steps": 1},
        },
        {
            "path": "exit.right.value",
            "coupled_paths": [],
            "values": None,
            "range": None,
            "nearby": {"step": None, "steps": 1},
        },
    ]
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["store"] is False and "tools" not in body
        assert "Train only" in body["instructions"]
        assert "No prices, trades, metrics" in body["instructions"]
        assert body["text"]["format"]["strict"] is True
        schema = body["text"]["format"]["schema"]
        assert schema["additionalProperties"] is False
        assert "SensitivityExtraction" in schema["$defs"]
        assert "ParameterSpec" in schema["$defs"] and "RuleStrategy" in schema["$defs"]
        assert "oneOf" not in json.dumps(schema)
        return httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        )

    install_transport(monkeypatch, handler)
    config = parse_sensitivity("Analyze nearby RSI 30/70 thresholds on BTCUSDT")
    assert len(requests) == 1
    assert config.train_ratio == 0.7 and config.period_days == 30 and config.timeframe == "1h"
    assert config.initial_balance == 10000 and config.fee == 0.001
    from strategy_backtest_agent.sensitivity.grid import expand_grid

    definitions, variants = expand_grid(config.base_strategy, config.parameters)
    assert definitions[0].values == [25, 30, 35]
    assert definitions[1].values == [65, 70, 75] and len(variants) == 9


def test_explicit_period_coupling_ranges_and_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        **extraction(),
        "timeframe": "4h",
        "period_days": 180,
        "train_ratio": 0.8,
        "initial_balance": 5000,
        "fee": 0.002,
        "evaluation_end": "2024-04-01T04:00:00+04:00",
        "parameters": [
            {
                "path": "entry.left.period",
                "coupled_paths": ["exit.left.period"],
                "values": None,
                "range": {"start": 10, "stop": 20, "step": 5},
                "nearby": None,
            }
        ],
    }
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        ),
    )
    config = parse_sensitivity("Analyze RSI periods 10 to 20 step 5 on BTCUSDT")
    assert config.parameters[0].coupled_paths == ["exit.left.period"]
    assert config.train_ratio == 0.8 and config.period_days == 180 and config.timeframe == "4h"
    assert config.initial_balance == 5000 and config.fee == 0.002
    assert config.evaluation_end is not None
    assert config.evaluation_end.isoformat() == "2024-04-01T00:00:00+00:00"


@pytest.mark.parametrize("reason", ["unsupported", "ambiguous", "missing_symbol", "invalid_grid"])
def test_structured_rejections(reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": None, "rejection": reason})
        ),
    )
    with pytest.raises(StrategyParseError, match=reason.replace("_", " ")):
        parse_sensitivity("Analyze RSI thresholds on BTCUSDT")


@pytest.mark.parametrize(
    "kind", ["oversized", "path", "period", "performance", "code", "override", "ratio"]
)
def test_invalid_extractions_rejected(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    values = extraction()
    if kind == "oversized":
        values["parameters"] = [
            spec(values=list(range(20, 26))).model_dump(),
            spec("exit.right.value", values=list(range(70, 75))).model_dump(),
        ]
    elif kind == "path":
        values["parameters"] = [spec("entry.period").model_dump()]
    elif kind == "period":
        values["parameters"] = [spec("entry.left.period", values=[2.5]).model_dump()]
    elif kind == "ratio":
        values["train_ratio"] = 0.95
    else:
        values[{"performance": "returns", "code": "python", "override": "winner"}[kind]] = (
            "invented"
        )
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="Invalid parsed|validated"):
        parse_sensitivity("Analyze RSI on BTCUSDT")


@pytest.mark.parametrize(
    "text",
    [
        "Analyze Ichimoku on BTCUSDT",
        "Analyze 10x leverage on BTCUSDT",
        "Analyze short selling on BTCUSDT",
        "Analyze stop loss on BTCUSDT",
        "Analyze take profit on BTCUSDT",
        "Analyze SMA crosses above on BTCUSDT",
        "Optimize RSI on BTCUSDT",
        "Choose best thresholds on BTCUSDT",
        "Analyze RSI by random split on BTCUSDT",
        "Walk-forward BTCUSDT",
        "Analyze robustness score on BTCUSDT",
        "Predict future BTCUSDT returns",
        "Analyze and evaluate variants on Test for BTCUSDT",
    ],
)
def test_unsupported_requests_never_call_openai(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("unsupported requests must not call OpenAI")

    monkeypatch.setattr(parser, "create_client", forbidden)
    with pytest.raises(StrategyParseError, match="Unsupported|unsupported"):
        parse_sensitivity(text)


@pytest.mark.parametrize("text", ["", "   ", "x" * 8001])
def test_input_limits(text: str) -> None:
    with pytest.raises(StrategyParseError, match="empty|8000"):
        parse_sensitivity(text)


def test_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StrategyParseError, match="OPENAI_API_KEY"):
        parse_sensitivity("Analyze nearby RSI thresholds on BTCUSDT")


def test_symbol_must_be_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": extraction(), "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError, match="explicitly present"):
        parse_sensitivity("Analyze RSI on Bitcoin")


def test_constructed_sdk_objects_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        responses = SimpleNamespace(
            parse=lambda **_: SimpleNamespace(
                status="completed",
                output_parsed=SensitivityParserOutput.model_construct(
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
        parse_sensitivity("Analyze RSI on BTCUSDT")
