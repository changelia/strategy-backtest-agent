"""Offline regression coverage for the direct natural-language backtest boundary."""

import asyncio
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from strategy_backtest_agent import AIStrategyConfig, BacktestClient
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
