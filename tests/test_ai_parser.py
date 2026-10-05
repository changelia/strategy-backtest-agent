import json
from collections.abc import Callable

import httpx2
import pytest
from openai import OpenAI

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.ai.models import ParserOutput
from strategy_backtest_agent.ai.parser import StrategyParseError, parse_strategy


def extraction(**updates: object) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": None,
        "period_days": None,
        "initial_balance": None,
        "fee": None,
        "strategy": None,
        **updates,
    }


def response_payload(output: object, status: str = "completed") -> dict[str, object]:
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 1,
        "model": "test-model",
        "status": status,
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "none",
        "tools": [],
    }


def install_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx2.Request], httpx2.Response]
) -> None:
    def client() -> OpenAI:
        return OpenAI(
            api_key="test-placeholder",
            max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )

    monkeypatch.setattr(parser, "create_client", client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_actual_sdk_structured_parse_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["model"] == parser.DEFAULT_MODEL
        assert body["store"] is False
        assert "tools" not in body
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["input"] == "Backtest BTCUSDT"
        assert "Do not provide financial advice" in body["instructions"]
        schema = body["text"]["format"]["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"configuration", "rejection"}
        return httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": extraction(),
                    "rejection": None,
                }
            ),
        )

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    install_transport(monkeypatch, handler)
    parsed = parse_strategy("Backtest BTCUSDT")
    assert parsed.period_days == 30
    assert parsed.strategy.period == 14


def test_custom_values_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(request.content)["model"] == "configured-model"
        return httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": extraction(
                        symbol="ETHUSDT",
                        timeframe="4h",
                        period_days=180,
                        initial_balance=5000,
                        fee=0.002,
                        strategy={"period": 10, "entry_below": 25, "exit_above": 65},
                    ),
                    "rejection": None,
                }
            ),
        )

    install_transport(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    parsed = parse_strategy(
        "Backtest ETHUSDT on 4h for 180 days with 5000, fee 0.2%, RSI period 10, buy <25 sell >65"
    )
    assert (
        parsed.symbol,
        parsed.timeframe,
        parsed.period_days,
        parsed.initial_balance,
        parsed.fee,
    ) == (
        "ETHUSDT",
        "4h",
        180,
        5000,
        0.002,
    )
    assert parsed.to_backtest_config().rsi_period == 10
    assert (parsed.strategy.entry_below, parsed.strategy.exit_above) == (25, 65)


@pytest.mark.parametrize(
    "text",
    [
        "Buy when MACD crosses",
        "short BTCUSDT with 10x leverage",
        "Short BTCUSDT",
        "Buy with leverage",
        "Buy BTCUSDT with stop loss",
        "Use Bollinger Bands",
        "RSI and SMA",
        "BTCUSDT take profit",
        "Predict BTCUSDT prices",
        "live trading BTCUSDT",
    ],
)
def test_explicit_unsupported_requests_never_call_ai(
    text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden() -> OpenAI:
        raise AssertionError("unsupported input must not call AI")

    monkeypatch.setattr(parser, "create_client", forbidden)
    with pytest.raises(StrategyParseError, match="Unsupported strategy"):
        parse_strategy(text)


@pytest.mark.parametrize(
    "code",
    [
        "unsupported",
        "ambiguous",
        "missing_symbol",
        "multiple_symbols",
        "multiple_conditions",
        "short_selling",
        "leverage",
    ],
)
def test_structured_rejections(code: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": None,
                    "rejection": code,
                }
            ),
        ),
    )
    with pytest.raises(StrategyParseError, match="Request rejected"):
        parse_strategy("Request requiring semantic rejection")


@pytest.mark.parametrize(
    "output",
    [
        {
            "configuration": extraction(
                strategy={"period": None, "entry_below": 70, "exit_above": 30}
            ),
            "rejection": None,
        },
        {"configuration": extraction(period_days=0), "rejection": None},
        {"configuration": extraction(symbol=None), "rejection": None},
        {"configuration": extraction(fee=-1), "rejection": None},
        {"configuration": extraction(), "rejection": None, "profit": 100},
        {"configuration": None, "rejection": None},
        {"wrong": "schema"},
    ],
)
def test_invalid_and_malformed_output(output: object, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(monkeypatch, lambda _: httpx2.Response(200, json=response_payload(output)))
    with pytest.raises(StrategyParseError, match="Invalid parsed strategy"):
        parse_strategy("Backtest BTCUSDT")


@pytest.mark.parametrize(
    "status,message",
    [
        (401, "authentication"),
        (429, "rate limit"),
        (500, "request failed"),
        (400, "request failed"),
    ],
)
def test_api_errors_are_sanitized(
    status: int, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            status,
            json={
                "error": {"message": "sensitive server detail", "type": "test_error"},
            },
        ),
    )
    with pytest.raises(StrategyParseError, match=message) as error:
        parse_strategy("Backtest BTCUSDT")
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize("exception", [httpx2.ReadTimeout, httpx2.ConnectError])
def test_network_errors(
    exception: type[httpx2.RequestError], monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exception("network unavailable", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(StrategyParseError, match="timed out|unavailable"):
        parse_strategy("Backtest BTCUSDT")


def test_refusal_and_incomplete_response(monkeypatch: pytest.MonkeyPatch) -> None:
    for status in ["completed", "incomplete"]:
        payload = response_payload(None, status)
        payload["output"] = []

        def handler(
            request: httpx2.Request, payload: dict[str, object] = payload
        ) -> httpx2.Response:
            return httpx2.Response(200, json=payload)

        install_transport(monkeypatch, handler)
        with pytest.raises(StrategyParseError, match="complete structured strategy"):
            parse_strategy("Backtest BTCUSDT")


@pytest.mark.parametrize("text", ["", "   ", "x" * 8001])
def test_empty_and_oversized_input(text: str) -> None:
    with pytest.raises(StrategyParseError, match="empty|8000"):
        parse_strategy(text)


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(StrategyParseError, match="OPENAI_API_KEY is missing"):
        parse_strategy("Backtest BTCUSDT")


def test_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", " ")
    with pytest.raises(StrategyParseError, match="OPENAI_MODEL must not be empty"):
        parse_strategy("Backtest BTCUSDT")


def test_constructed_output_cannot_bypass_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulates an injected client returning a Pydantic object made without validation.
    from types import SimpleNamespace

    class FakeClient:
        responses = SimpleNamespace(
            parse=lambda **_: SimpleNamespace(
                status="completed",
                output_parsed=ParserOutput.model_construct(
                    configuration=None,
                    rejection=None,
                ),
            )
        )

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(parser, "create_client", FakeClient)
    with pytest.raises(StrategyParseError, match="Invalid parsed strategy"):
        parse_strategy("Backtest BTCUSDT")


def test_model_cannot_invent_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": extraction(),
                    "rejection": None,
                }
            ),
        ),
    )
    with pytest.raises(StrategyParseError, match="explicitly present"):
        parse_strategy("Backtest Bitcoin")


def test_partial_rsi_defaults_preserve_explicit_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200,
            json=response_payload(
                {
                    "configuration": extraction(
                        strategy={"period": None, "entry_below": 25, "exit_above": None}
                    ),
                    "rejection": None,
                }
            ),
        ),
    )
    parsed = parse_strategy("Backtest BTCUSDT buying below RSI 25")
    assert (parsed.strategy.period, parsed.strategy.entry_below, parsed.strategy.exit_above) == (
        14,
        25,
        70,
    )


def test_non_json_model_text_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = response_payload(None)
    payload["output"] = [
        {
            "id": "msg_fixture",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "```json\n{}\n```", "annotations": []}],
        }
    ]
    install_transport(monkeypatch, lambda _: httpx2.Response(200, json=payload))
    with pytest.raises(StrategyParseError, match="Invalid parsed strategy|could not be validated"):
        parse_strategy("Backtest BTCUSDT")
