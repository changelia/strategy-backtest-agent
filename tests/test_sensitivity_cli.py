"""Config-only and AI CLI modes, JSON-only stdout and sanitized stderr errors."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from test_comparison_engine import END, history
from test_sensitivity_grid import settings, spec

from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.sensitivity.models import SensitivityConfig


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
def test_success(
    mode: str,
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests = setup_provider(monkeypatch)
    config = settings(parameters=[spec(), spec("exit.right.value", values=[65, 70, 75])])

    def parse(text: str) -> SensitivityConfig:
        if mode == "config":
            raise AssertionError("config must not call AI")
        assert text == "Analyze RSI on BTCUSDT"
        return config

    monkeypatch.setattr(parser, "parse_sensitivity", parse)
    path = tmp_path / "sensitivity.json"
    path.write_text(config.model_dump_json())
    args = ["--config", str(path)] if mode == "config" else ["Analyze RSI on BTCUSDT"]
    monkeypatch.setattr(
        "sys.argv", ["strategy-backtest", "sensitivity", *args, *(["--json"] if as_json else [])]
    )
    main()
    output = capsys.readouterr()
    assert output.err == "" and len(requests) == 1 and requests[0][3] == END
    if as_json:
        data = json.loads(output.out)
        assert set(data) == {
            "configuration",
            "shared_data",
            "split",
            "parameters",
            "variants",
            "results",
            "summary",
            "neighbors",
            "ordered_series",
            "matrix",
            "execution_assumptions",
            "methodology_warnings",
        }
        assert (
            len(data["variants"]) == len(data["results"]) == data["summary"]["variant_count"] == 9
        )
        assert data["split"]["train_candle_count"] == 16
        assert data["results"][0]["train"]["result"]["profit_factor"] is None
        assert data["results"][0]["train"]["result"]["win_rate"] is None
        assert data["matrix"]["row_values"] == [25, 30, 35]
        assert "ranking" not in data and "winner" not in data
        assert "test" not in data["results"][0]
        assert data["configuration"]["evaluation_end"] == "2024-01-02T00:00:00Z"
        assert "NaN" not in output.out and "Infinity" not in output.out
        assert "resp_" not in output.out and "instructions" not in output.out
    else:
        assert "Parameter Sensitivity Analysis" in output.out
        assert "In-sample sensitivity analysis" in output.out
        assert "Reserved Test (not evaluated)" in output.out
        assert "ENTRY:" in output.out and "EXIT:" in output.out
        assert "Train return matrix" in output.out and "insufficient trades" in output.out
        assert "overfit" in output.out and "N/A" in output.out
        assert "Median" in output.out and "Buy & Hold" in output.out


@pytest.mark.parametrize(
    "kind", ["json", "invalid", "missing", "provider", "key", "unsupported", "oversized"]
)
def test_errors(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    requests = setup_provider(monkeypatch)
    path = tmp_path / "sensitivity.json"
    if kind != "missing":
        values = settings().model_dump(mode="json")
        if kind == "oversized":
            values["parameters"] = [
                spec(values=list(range(20, 26))).model_dump(),
                spec("exit.right.value", values=list(range(70, 75))).model_dump(),
            ]
        path.write_text(
            "{" if kind == "json" else "{}" if kind == "invalid" else json.dumps(values)
        )
    if kind == "provider":

        async def fail(
            self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> list[Candle]:
            raise MarketDataError("provider unavailable")

        monkeypatch.setattr(BinanceMarketData, "fetch_candles", fail)
    args = (
        ["Analyze RSI on BTCUSDT"]
        if kind == "key"
        else ["Optimize RSI on BTCUSDT"]
        if kind == "unsupported"
        else ["--config", str(path)]
    )
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "sensitivity", *args, "--json"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "Error:" in output.err and "Traceback" not in output.err
    assert requests == []


@pytest.mark.parametrize(
    "arguments",
    [[], ["Analyze RSI on BTCUSDT", "--config", "other.json"], ["--sort", "total_return"]],
)
def test_argument_exclusivity(arguments: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "sensitivity", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "sensitivity", "--help"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    assert "strategy-backtest sensitivity" in capsys.readouterr().out


@pytest.mark.parametrize(
    "filename", ["sensitivity.json", "sensitivity-sma.json", "sensitivity-ema.json"]
)
def test_documented_configs_validate(filename: str) -> None:
    from strategy_backtest_agent.sensitivity.grid import expand_grid

    config = SensitivityConfig.model_validate_json(Path("examples", filename).read_text())
    definitions, variants = expand_grid(config.base_strategy, config.parameters)
    assert len(definitions) == 2 and len(variants) == 9
