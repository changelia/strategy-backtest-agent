"""Offline regression coverage for the direct natural-language backtest boundary."""

import asyncio
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from strategy_backtest_agent import AIStrategyConfig, BacktestClient
from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.reports.inputs import CLIBacktest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Direct DSL tests must never access the network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "sendto", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def customer_config() -> AIStrategyConfig:
    path = Path(__file__).resolve().parents[1] / "examples/customer-ai-strategy.json"
    return AIStrategyConfig.model_validate_json(path.read_bytes())


@pytest.mark.parametrize("asynchronous", [False, True])
def test_direct_rule_execution_validates_serialized_timestamps(
    customer_config: AIStrategyConfig,
    monkeypatch: pytest.MonkeyPatch,
    asynchronous: bool,
) -> None:
    parser = Mock(return_value=customer_config)
    monkeypatch.setattr("strategy_backtest_agent.ai.parser.parse_strategy", parser)
    client = BacktestClient(api_key="", model="offline-test")
    request = "test"
    result = (
        asyncio.run(client.arun(request, demo=True))
        if asynchronous
        else client.run(request, demo=True)
    )
    parser.assert_called_once_with(request, api_key="", model="offline-test")
    assert isinstance(result.data, CLIBacktest)
    source = json.loads(result.to_json())
    assert set(source) == {"input", "parsed_strategy", "backtest_result"}
    assert source["input"] == request
    assert source["parsed_strategy"] == customer_config.model_dump(mode="json")
    assert CLIBacktest.model_validate_json(json.dumps(source["backtest_result"])) == result.data
    period = result.data.evaluation_period
    assert period is not None
    assert period.requested_end == datetime(2024, 7, 1, tzinfo=UTC)
    assert period.requested_start == period.requested_end - timedelta(days=30)
    for boundary in (period.requested_start, period.requested_end):
        assert isinstance(boundary, datetime)
        assert boundary.tzinfo is not None and boundary.utcoffset() == timedelta(0)


@pytest.mark.parametrize("demo", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_direct_config_parity_and_saved_reports(
    customer_config: AIStrategyConfig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    demo: bool,
    legacy: bool,
) -> None:
    if legacy:
        values = customer_config.model_dump(mode="json")
        values["strategy"] = {"type": "rsi", "period": 14, "entry_below": 30, "exit_above": 70}
        customer_config = AIStrategyConfig.model_validate_json(json.dumps(values))
    parser = Mock(return_value=customer_config)
    monkeypatch.setattr("strategy_backtest_agent.ai.parser.parse_strategy", parser)

    class OfflineProvider:
        calls = 0

        async def fetch_candles(
            self, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> list[Candle]:
            assert symbol == customer_config.symbol
            self.calls += 1
            return [c for c in demo_candles(timeframe, 32) if start <= c.timestamp < end]

    provider = OfflineProvider()
    client = BacktestClient(api_key="", market_data_provider=provider)
    end = datetime(2024, 7, 1, tzinfo=UTC)
    direct = client.run("test", demo=demo, evaluation_end=end)
    awaited = asyncio.run(client.arun("test", demo=demo, evaluation_end=end))
    explicit = client.run(config=customer_config, demo=demo, evaluation_end=end)
    assert isinstance(direct.data, CLIBacktest)
    assert direct.data == awaited.data == explicit.data
    assert direct.to_json() == awaited.to_json()
    assert direct.data.execution == customer_config.execution_config()
    assert direct.data.data_source == ("synthetic_demo" if demo else "custom")
    assert provider.calls == (0 if demo else 3)
    source = json.loads(direct.to_json())
    assert source["parsed_strategy"] == customer_config.model_dump(mode="json")
    assert source["backtest_result"] == json.loads(explicit.to_json())
    path = tmp_path / "source.json"
    path.write_text(direct.to_json(), encoding="utf-8")
    for format_name in ("json", "markdown"):
        report = client.report(direct, format=format_name)
        assert report == client.report(awaited, format=format_name)
        assert report == client.report(path, format=format_name)
        assert report == client.report(path, format=format_name)
    direct_report = json.loads(client.report(direct, format="json"))
    config_report = json.loads(client.report(explicit, format="json"))
    # Envelopes change source hashes and metric paths, but never financial values.
    for report in (direct_report, config_report):
        assert report["evidence"]["source"]["data_source"] == direct.data.data_source
    assert [m["value"] for m in direct_report["evidence"]["metrics"]] == [
        m["value"] for m in config_report["evidence"]["metrics"]
    ]


def test_json_boundary_preserves_strict_rejection(
    customer_config: AIStrategyConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = BacktestClient(api_key="")
    monkeypatch.setattr(
        "strategy_backtest_agent.ai.parser.parse_strategy", Mock(return_value=customer_config)
    )
    source = json.loads(client.run("test", demo=True).to_json())["backtest_result"]
    # JSON timestamps are valid only at the JSON boundary, not in strict Python models.
    with pytest.raises(ValidationError) as error:
        CLIBacktest.model_validate(source)
    assert {tuple(e["loc"]) for e in error.value.errors()} >= {
        ("evaluation_period", "requested_start"),
        ("evaluation_period", "requested_end"),
    }
    for field, invalid in (("requested_start", "not-a-date"), ("requested_end", "2024-07-01")):
        altered = json.loads(json.dumps(source))
        altered["evaluation_period"][field] = invalid
        with pytest.raises(ValidationError):
            CLIBacktest.model_validate_json(json.dumps(altered))
    source["evaluation_period"]["warmup_candles"] = "14"
    with pytest.raises(ValidationError):
        CLIBacktest.model_validate_json(json.dumps(source))
