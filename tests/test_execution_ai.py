"""SDK mocks for explicit execution assumptions and conservative defaults."""

import json

import httpx2
import pytest
from test_ai_parser import extraction, install_transport, response_payload
from test_comparison_ai import extraction as comparison_extraction
from test_sensitivity_ai import extraction as sensitivity_extraction
from test_validation_ai import values as validation_extraction

from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.ai.parser import (
    StrategyParseError,
    parse_comparison,
    parse_sensitivity,
    parse_strategy,
    parse_validation,
)
from strategy_backtest_agent.comparison.models import MarketConfig


@pytest.mark.parametrize("mode", ["ai", "compare", "validate", "sensitivity"])
def test_explicit_execution_costs_in_one_structured_request(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = {
        "ai": extraction,
        "compare": comparison_extraction,
        "validate": validation_extraction,
        "sensitivity": sensitivity_extraction,
    }[mode]()
    source["execution"] = {"fee_rate": None, "spread_bps": 10, "slippage_bps": 5}
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert "FULL spread_bps" in body["instructions"]
        assert "Never invent, estimate" in body["instructions"]
        assert "ExecutionExtraction" in body["text"]["format"]["schema"]["$defs"]
        assert body["store"] is False and "tools" not in body
        return httpx2.Response(
            200, json=response_payload({"configuration": source, "rejection": None})
        )

    install_transport(monkeypatch, handler)
    parse = {
        "ai": parse_strategy,
        "compare": parse_comparison,
        "validate": parse_validation,
        "sensitivity": parse_sensitivity,
    }[mode]
    config = parse("Backtest BTCUSDT using RSI with 10 bps spread and 5 bps slippage")
    assert isinstance(config, AIStrategyConfig | MarketConfig)
    assert len(calls) == 1
    assert config.execution_config().spread_bps == 10
    assert config.execution_config().slippage_bps == 5
    assert config.execution_config().fee_rate == 0.001
    assert config.to_backtest_config().execution_config() == config.execution_config()


@pytest.mark.parametrize(
    "text",
    [
        "Backtest BTCUSDT, spread: 10 bps and slippage: 5 basis points",
        "Backtest BTCUSDT with 0.1% spread and 0.05% slippage",
        "Backtest BTCUSDT, spread_bps=10, slippage_bps=5",
    ],
)
def test_named_cost_units_and_formats(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    source = extraction(execution={"fee_rate": None, "spread_bps": 10, "slippage_bps": 5})
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": source, "rejection": None})
        ),
    )
    assert parse_strategy(text).execution_config().spread_bps == 10


@pytest.mark.parametrize(
    "kind",
    ["invented", "wrong", "omitted", "ambiguous", "negative", "invalid_combined", "raw_results"],
)
def test_invalid_or_invented_execution_assumptions_are_rejected(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = extraction(execution={"fee_rate": None, "spread_bps": 10, "slippage_bps": 5})
    text = "Backtest BTCUSDT with 10 bps spread and 5 bps slippage"
    if kind == "invented":
        text = "Backtest BTCUSDT"
    elif kind == "wrong":
        text = "Backtest BTCUSDT with 20 bps spread and 5 bps slippage"
    elif kind == "omitted":
        source["execution"] = None
    elif kind == "ambiguous":
        text += " or 20 bps spread"
    elif kind == "negative":
        source["execution"] = {"fee_rate": None, "spread_bps": -1, "slippage_bps": 5}
    elif kind == "invalid_combined":
        source["execution"] = {"fee_rate": None, "spread_bps": 20000, "slippage_bps": 0}
    else:
        source["execution"] = {
            "fee_rate": 0.001,
            "spread_bps": 10,
            "slippage_bps": 5,
            "fill_price": 100.2,
        }
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": source, "rejection": None})
        ),
    )
    with pytest.raises(StrategyParseError):
        parse_strategy(text)


def test_legacy_fee_is_inherited_by_explicit_spread(monkeypatch: pytest.MonkeyPatch) -> None:
    source = extraction(
        fee=0.002, execution={"fee_rate": None, "spread_bps": 10, "slippage_bps": None}
    )
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": source, "rejection": None})
        ),
    )
    parsed = parse_strategy("Backtest BTCUSDT with fee 0.2% and spread 10 bps")
    assert parsed.fee == parsed.execution_config().fee_rate == 0.002


def test_no_cost_assumptions_preserves_zero_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": extraction(), "rejection": None})
        ),
    )
    config = parse_strategy("Backtest BTCUSDT")
    assert config.execution_config().spread_bps == config.execution_config().slippage_bps == 0
