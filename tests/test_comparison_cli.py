"""Both CLI entry paths use shared history; JSON stdout stays machine-readable."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from test_comparison_engine import END, config, history

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError
from strategy_backtest_agent.models import Candle


def setup_provider(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, datetime, datetime]]:
    requests: list[tuple[str, str, datetime, datetime]] = []

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        requests.append((symbol, timeframe, start, end))
        return history([10.0] * 27)

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return requests


@pytest.mark.parametrize("mode", ["config", "ai"])
@pytest.mark.parametrize("as_json", [True, False])
def test_cli_success(
    mode: str,
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests = setup_provider(monkeypatch)
    settings = config()

    def parse(text: str) -> ComparisonConfig:
        if mode == "config":
            raise AssertionError("config mode must not call AI")
        assert text == "Compare RSI strategies on BTCUSDT"
        return settings

    monkeypatch.setattr(parser, "parse_comparison", parse)
    path = tmp_path / "comparison.json"
    path.write_text(settings.model_dump_json())
    args = ["--config", str(path)] if mode == "config" else ["Compare RSI strategies on BTCUSDT"]
    monkeypatch.setattr(
        "sys.argv",
        [
            "strategy-backtest",
            "compare",
            *args,
            "--sort",
            "profit_factor",
            *(["--json"] if as_json else []),
        ],
    )
    main()
    output = capsys.readouterr()
    assert output.err == ""
    assert len(requests) == 1
    assert requests[0][3] == END
    if as_json:
        payload = json.loads(output.out)
        assert payload["configuration"]["evaluation_end"] == "2024-01-02T00:00:00Z"
        assert payload["ranking_criterion"] == "profit_factor"
        assert payload["ranking"] == ["rsi-25", "rsi-30"]
        assert payload["shared_data"]["candle_count"] == 24
        assert payload["shared_data"]["warmup_candles"] == 3
        assert payload["results"][0]["result"]["total_trades"] == 0
        assert payload["results"][0]["result"]["profit_factor"] is None
        assert set(payload) == {
            "configuration",
            "shared_data",
            "buy_and_hold_return_percent",
            "results",
            "ranking_criterion",
            "ranking",
        }
        assert "resp_" not in output.out and "instructions" not in output.out
    else:
        assert "Strategy Comparison" in output.out
        assert "Buy & Hold:" in output.out
        assert "prior warm-up: 3" in output.out
        assert "N/A" in output.out
        assert "ENTRY:" in output.out and "EXIT:" in output.out
        assert "Excess" in output.out and "Profit factor" in output.out


@pytest.mark.parametrize(
    "kind", ["json", "validation", "missing_file", "provider", "key", "unsupported"]
)
def test_cli_errors(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_provider(monkeypatch)
    path = tmp_path / "comparison.json"
    if kind != "missing_file":
        path.write_text(
            "{"
            if kind == "json"
            else json.dumps({"symbol": "BTCUSDT"})
            if kind == "validation"
            else config().model_dump_json()
        )
    if kind == "provider":

        async def fail(
            self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> list[Candle]:
            raise MarketDataError("provider unavailable")

        monkeypatch.setattr(BinanceMarketData, "fetch_candles", fail)
    args = (
        ["Compare RSI 25/70 and RSI 30/70 on BTCUSDT"]
        if kind == "key"
        else ["Compare MACD and RSI on BTCUSDT"]
        if kind == "unsupported"
        else ["--config", str(path)]
    )
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "compare", *args, "--json"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Error:" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    "arguments", [[], ["--sort", "unknown"], ["Compare RSI on BTCUSDT", "--config", "other.json"]]
)
def test_argument_exclusivity(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "compare", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert capsys.readouterr().out == ""
