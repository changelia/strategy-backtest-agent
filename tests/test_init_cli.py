"""Actual init/consumer workflows and no-overwrite publication, entirely offline."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from strategy_backtest_agent.cli import main
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import BacktestConfig
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

KINDS = ("backtest", "compare", "validate", "walk-forward")
MODELS = (BacktestConfig, ComparisonConfig, ValidationConfig, WalkForwardConfig)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("No prompts or network permitted")

    monkeypatch.setattr("builtins.input", forbidden)
    monkeypatch.setattr(BinanceMarketData, "fetch_candles", forbidden)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def invoke(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["strategy-backtest", *args])
    main()


@pytest.mark.parametrize("kind,model", zip(KINDS, MODELS, strict=True))
def test_generated_templates_validate_execute_and_repeat(
    kind: str,
    model: type[BacktestConfig | ComparisonConfig | ValidationConfig | WalkForwardConfig],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = [tmp_path / f"{kind}-{index}.json" for index in range(2)]
    outputs = []
    for path in paths:
        invoke(monkeypatch, ["init", "--type", kind, "--output", str(path)])
        capsys.readouterr()
        config = model.model_validate_json(path.read_bytes())
        assert config.symbol == "BTCUSDT" and config.initial_balance == 10000
        args = [] if kind == "backtest" else [kind]
        invoke(monkeypatch, [*args, "--config", str(path), "--demo", "--json"])
        output = capsys.readouterr()
        assert not output.err
        result = json.loads(output.out)
        report = build_report(output.out.encode())
        assert report.evidence.source.data_source == "synthetic_demo"
        assert report.ai_interpretation is None
        if kind == "backtest":
            assert result["execution"] == {
                "fee_rate": 0.001,
                "spread_bps": 10.0,
                "slippage_bps": 5.0,
            }
        else:
            assert result["shared_data"]["warmup_candles"] == 15
        if kind == "walk-forward":
            assert len(result["folds"]) == 3
        outputs.append(output.out)
    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--type", "backtest"],
        ["--output", "x.json"],
        ["--type", "unknown", "--output", "x.json"],
        ["--type", "backtest", "--output"],
        ["--type", "backtest", "--output", "x.json", "--force"],
        ["backtest", "--output", "x.json"],
    ],
)
def test_invalid_init_arguments_create_nothing(
    args: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["init", *args])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("conflict", ["file", "directory", "symlink", "dangling", "parent"])
def test_init_preserves_conflicting_destinations(
    conflict: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = tmp_path / "keep.json"
    original.write_text("private original")
    destination = tmp_path / "new.json"
    if conflict == "file":
        destination.write_text("existing")
    elif conflict == "directory":
        destination.mkdir()
    elif conflict in ("symlink", "dangling"):
        destination.symlink_to(original if conflict == "symlink" else tmp_path / "absent")
    else:
        parent = tmp_path / "linked"
        parent.symlink_to(tmp_path, target_is_directory=True)
        destination = parent / "new.json"
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["init", "--type", "backtest", "--output", str(destination)])
    assert exc.value.code == 2
    assert "Error:" in capsys.readouterr().err
    assert original.read_text() == "private original"
    if conflict == "file":
        assert destination.read_text() == "existing"
    assert not list(tmp_path.glob(".research-report-*.tmp"))


@pytest.mark.parametrize("failure", ["fsync", "link", "open"])
def test_failed_init_write_leaves_no_partial_config(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "config.json"

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("synthetic write failure")

    monkeypatch.setattr(os, failure, fail)
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["init", "--type", "backtest", "--output", str(destination)])
    assert exc.value.code == 2
    assert "synthetic write failure" in capsys.readouterr().err
    assert not destination.exists()
    assert not list(tmp_path.iterdir())


def test_racing_creator_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "config.json"
    link = os.link

    def racing_link(*args: Any, **kwargs: Any) -> None:
        destination.write_text("racing creator")
        link(*args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(SystemExit):
        invoke(monkeypatch, ["init", "--type", "backtest", "--output", str(destination)])
    assert destination.read_text() == "racing creator"
    assert list(tmp_path.iterdir()) == [destination]
    assert "Error:" in capsys.readouterr().err


def test_parent_traversal_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["init", "--type", "backtest", "--output", str(tmp_path / ".." / "x")])
    assert exc.value.code == 2


@pytest.mark.parametrize("kind", ["compare", "validate", "walk-forward"])
def test_offline_mode_rejects_ai_before_parsing(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, [kind, "Backtest something", "--demo"])
    assert exc.value.code == 2


@pytest.mark.parametrize("flag", ["--fee=0.02", "--symbol=ETHUSDT", "--bal=200"])
def test_backtest_config_rejects_conflicting_legacy_flags(
    flag: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    invoke(monkeypatch, ["init", "--type", "backtest", "--output", str(path)])
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["--config", str(path), "--demo", flag])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "invalid", ["{", '{"unexpected": true}', '{"entry_rsi": 90, "exit_rsi": 10}']
)
def test_backtest_rejects_bad_config_before_execution(
    invalid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(invalid)
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, ["--config", str(path), "--demo"])
    assert exc.value.code == 2
    assert "Error:" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["compare", "validate", "walk-forward"])
def test_demo_rejects_conflicting_historical_end(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "config.json"
    invoke(monkeypatch, ["init", "--type", kind, "--output", str(path)])
    capsys.readouterr()
    config = json.loads(path.read_bytes())
    config["evaluation_end"] = "2025-01-01T00:00:00Z"
    path.write_text(json.dumps(config))
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, [kind, "--config", str(path), "--demo"])
    assert exc.value.code == 2
    assert "--demo requires evaluation_end" in capsys.readouterr().err


def test_backtest_config_cost_override_preserves_declared_fee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"trading_fee": 0.02}')
    invoke(
        monkeypatch,
        ["--config", str(path), "--demo", "--days", "10", "--spread-bps", "10", "--json"],
    )
    output = json.loads(capsys.readouterr().out)
    assert output["execution"]["fee_rate"] == 0.02
    assert output["execution"]["spread_bps"] == 10
