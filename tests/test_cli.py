from datetime import datetime

import pytest
from conftest import make_candles

from strategy_backtest_agent.cli import main
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import Candle


def test_cli_offline(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    async def fetch(
        self: BinanceMarketData,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        return make_candles([10, 9, 8, 12, 13])

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "--rsi-period", "2"])
    main()
    output = capsys.readouterr().out
    assert "Strategy: RSI" in output
    assert "Trades: 1" in output
    assert "Profit Factor: N/A" in output


def test_invalid_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "--days", "0"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "days must be positive" in capsys.readouterr().err


def test_demo_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("demo must not access network")

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", forbidden)
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "--demo", "--json", "--days", "30"])
    main()
    output = capsys.readouterr()
    first = json.loads(output.out)
    main()
    assert json.loads(capsys.readouterr().out) == first
    assert output.err == ""
    assert first["data_source"] == "synthetic_demo"
    assert first["candle_count"] == 720
    assert first["total_trades"] > 0
    assert first["final_balance"] == pytest.approx(
        first["initial_balance"] + sum(t["pnl"] for t in first["trades"])
    )
    assert first["trades"][0]["entry_time"]


@pytest.mark.parametrize(
    "args",
    [
        ["--balance", "-1"],
        ["--balance", "0"],
        ["--balance", "nan"],
        ["--timeframe", "invalid"],
        ["--days", "-1"],
        ["--entry-rsi", "101"],
        ["--exit-rsi", "-1"],
        ["--entry-rsi", "70"],
        ["--fee", "-0.1"],
        ["--symbol", "BTC/USDT"],
        ["--rsi-period", "0"],
    ],
)
def test_invalid_options(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", *args])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_demo_terminal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "--demo"])
    main()
    output = capsys.readouterr().out
    assert "synthetic offline demo" in output
    assert "Winning Trades:" in output
    assert "Losing Trades:" in output


def test_json_range_and_trade_timestamps_use_utc_z(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    monkeypatch.setattr("sys.argv", ["strategy-backtest", "--demo", "--json"])
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["start_time"].endswith("Z")
    assert payload["end_time"].endswith("Z")
    assert all(
        t["entry_time"].endswith("Z") and t["exit_time"].endswith("Z") for t in payload["trades"]
    )
