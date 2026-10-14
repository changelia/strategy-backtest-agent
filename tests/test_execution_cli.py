"""New cost flags on existing commands and cost-scenario config/JSON CLI, all offline."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import BaseModel
from test_comparison_engine import config as comparison_config
from test_comparison_engine import history
from test_cost_scenarios import settings as cost_config
from test_sensitivity_grid import settings as sensitivity_config
from test_validation_models import settings as validation_config

from strategy_backtest_agent.cli import main
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import Candle


def provider(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    calls = []

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        calls.append(end)
        return history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3)

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return calls


@pytest.mark.parametrize("command", ["compare", "validate", "sensitivity"])
def test_existing_config_commands_support_flags_json_and_fixed_dates(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = provider(monkeypatch)
    config: BaseModel
    if command == "compare":
        config = comparison_config()
    elif command == "validate":
        config = validation_config()
    else:
        config = sensitivity_config()
    path = tmp_path / "existing.json"
    path.write_text(config.model_dump_json())
    monkeypatch.setattr(
        "sys.argv",
        [
            "strategy-backtest",
            command,
            "--config",
            str(path),
            "--spread-bps",
            "20",
            "--slippage-bps",
            "10",
            "--json",
        ],
    )
    main()
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert output.err == "" and len(calls) == 1
    assert payload["configuration"]["execution"] == {
        "fee_rate": 0.001,
        "spread_bps": 20,
        "slippage_bps": 10,
    }
    result = (
        payload["results"][0]["result"]
        if command == "compare"
        else payload["results"][0]["train"]["result"]
    )
    assert result["execution"] == payload["configuration"]["execution"]
    assert result["equity_policy"] == "reference_prices"
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("as_json", [True, False])
def test_costs_config_only_cli(
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Price-only frozen strategy requires no prior indicators: return exactly 24 evaluation candles.
    calls = []

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        calls.append(end)
        return history([90, 110, 100] * 8, warmup=0)

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    path = tmp_path / "scenarios.json"
    path.write_text(cost_config().model_dump_json())
    args = ["strategy-backtest", "costs", "--config", str(path)] + (["--json"] if as_json else [])
    monkeypatch.setattr("sys.argv", args)
    main()
    output = capsys.readouterr()
    assert output.err == "" and len(calls) == 1
    if as_json:
        payload = json.loads(output.out)
        assert [row["id"] for row in payload["results"]] == ["baseline", "low", "medium"]
        assert payload["baseline_id"] == "baseline"
        assert "test" not in payload["results"][0]
        assert payload["results"][1]["execution"]["spread_bps"] == 5
        assert "winner" not in payload and "ranking" not in payload
        json.dumps(payload, allow_nan=False)
    else:
        assert "Execution Cost Scenarios" in output.out
        assert "Fees charged:" in output.out and "modeled spread cost:" in output.out
        assert "frozen strategy" in output.out and "mid-price proxies" in output.out


@pytest.mark.parametrize("kind", ["missing", "json", "negative", "baseline", "count"])
def test_costs_config_errors_have_empty_stdout_and_no_fetch(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = provider(monkeypatch)
    values = cost_config().model_dump(mode="json")
    if kind == "negative":
        values["scenarios"][1]["spread_bps"] = -1
    elif kind == "baseline":
        values["scenarios"][0]["slippage_bps"] = 1
    elif kind == "count":
        values["scenarios"] = []
    path = tmp_path / "bad.json"
    if kind != "missing":
        path.write_text("{" if kind == "json" else json.dumps(values))
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "costs", "--config", str(path), "--json"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and calls == []
    output = capsys.readouterr()
    assert output.out == "" and "Error:" in output.err and "Traceback" not in output.err


def test_standard_demo_flags_and_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "strategy-backtest",
            "--demo",
            "--days",
            "30",
            "--spread-bps",
            "20",
            "--slippage-bps",
            "10",
            "--json",
        ],
    )
    main()
    data = json.loads(capsys.readouterr().out)
    assert data["execution"] == {"fee_rate": 0.001, "spread_bps": 20, "slippage_bps": 10}
    assert data["costs"]["modeled_spread_cost"] > 0
    assert data["trades"][0]["entry_execution"]["side"] == "buy"
    assert data["trades"][0]["exit_execution"]["side"] == "sell"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--demo", "--spread-bps", "-1"],
        ["--demo", "--slippage-bps", "nan"],
        ["--demo", "--slippage-bps", "10000"],
    ],
)
def test_invalid_standard_flags(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", *arguments, "--json"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and capsys.readouterr().out == ""


def test_ai_cli_flags_preserve_fee_and_emit_execution_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from test_ai_cli import setup_flow

    parsed = setup_flow(monkeypatch, True)
    monkeypatch.setattr("sys.argv", [*sys.argv, "--spread-bps", "20", "--slippage-bps", "10"])
    main()
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert output.err == ""
    execution = payload["backtest_result"]["execution"]
    assert execution == {"fee_rate": parsed.fee, "spread_bps": 20, "slippage_bps": 10}
    assert payload["parsed_strategy"]["execution"] == execution


def test_documented_scenario_example_is_valid() -> None:
    from strategy_backtest_agent.costs.models import CostScenarioConfig

    config = CostScenarioConfig.model_validate_json(
        Path("examples/execution-scenarios.json").read_text()
    )
    assert len(config.scenarios) == 4 and config.strategy.type == "rules"
    assert config.evaluation_end is not None
