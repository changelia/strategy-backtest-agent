"""Offline chronological, accounting, initialization and protocol regression oracles."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

import httpx2
import pandas as pd
import pytest
from conftest import make_candles
from test_ai_parser import install_transport, response_payload
from test_comparison_ai import extraction
from test_comparison_engine import Provider, named
from test_rules import comparison, indicator, strategy
from test_validation_engine import ALWAYS, PRICE, ZERO

from strategy_backtest_agent import indicators
from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.comparison.engine import required_warmup
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.walk_forward.engine import fetch_and_walk_forward, run_walk_forward
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

START = datetime(2024, 1, 1, tzinfo=UTC)


def settings(**updates: object) -> WalkForwardConfig:
    return WalkForwardConfig.model_validate(
        {
            "symbol": "BTCUSDT",
            "period_days": 4,
            "timeframe": "12h",
            "evaluation_end": START + timedelta(days=4),
            "strategies": [named("always", ALWAYS)],
            "initial_balance": 1000,
            "fee": 0,
            "windows": {"train_days": 1, "test_days": 1},
            **updates,
        }
    )


def history(config: WalkForwardConfig, closes: list[float] | None = None) -> list[Candle]:
    warmup = required_warmup(config)
    count = config.period_days * 2 + warmup
    values = closes or [10.0] * count
    assert len(values) == count
    return [
        c.model_copy(update={"timestamp": START + timedelta(hours=12 * (i - warmup))})
        for i, c in enumerate(make_candles(values))
    ]


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_window_counts_boundaries_utc_and_isolation(mode: str) -> None:
    config = settings(windows={"mode": mode, "train_days": 1, "test_days": 1})
    report = run_walk_forward(history(config), config)
    assert len(report.folds) == 3
    assert report.unused_trailing_candles == 0
    for i, (fold, row) in enumerate(zip(report.folds, report.results, strict=True)):
        assert fold.id == f"fold-{i + 1:03d}"
        assert fold.train_start == START + timedelta(days=i if mode == "rolling" else 0)
        assert fold.train_end == fold.test_start == START + timedelta(days=i + 1)
        assert fold.test_end == START + timedelta(days=i + 2)
        assert fold.train_candle_count == (2 if mode == "rolling" else 2 * (i + 1))
        assert fold.test_candle_count == 2
        for segment in (row.train, row.test):
            result = segment.result
            assert result.initial_balance == result.final_balance == 1000
            assert result.total_trades == 1
            trade = result.trades[0]
            assert segment.start < trade.entry_time <= trade.exit_time < segment.end
            assert trade.exit_execution is not None and trade.exit_execution.forced
    assert report.configuration.strategies == config.strategies
    assert report == run_walk_forward(history(config), config)


@pytest.mark.parametrize(
    "updates",
    [
        {"period_days": 2},
        {"windows": {"train_days": 1, "test_days": 2, "step_days": 1}},
        {"windows": {"train_days": 1, "test_days": 1, "max_folds": 2}},
        {"windows": {"train_days": 0, "test_days": 1}},
        {"windows": {"train_days": 1, "test_days": 1, "step_days": 0}},
        {"timeframe": "1d"},
        {
            "stitch_oos": True,
            "period_days": 6,
            "windows": {"train_days": 1, "test_days": 1, "step_days": 2},
        },
        {"initial_balance": float("nan")},
        {"fee": float("inf")},
    ],
)
def test_invalid_protocol(updates: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        settings(**updates)


def test_trailing_incomplete_fold_and_gapped_tests() -> None:
    config = settings(
        period_days=5,
        evaluation_end=START + timedelta(days=5),
        windows={"train_days": 1, "test_days": 1, "step_days": 2},
    )
    report = run_walk_forward(history(config), config)
    assert len(report.folds) == 2 and report.unused_trailing_candles == 2
    assert report.folds[0].test_end < report.folds[1].test_start
    assert report.summaries[0].stitched_oos_index is None


@pytest.mark.parametrize("kind", ["empty", "short", "gap", "unfinished"])
def test_invalid_history(kind: str) -> None:
    config = settings()
    source = history(config)
    source = {
        "empty": [],
        "short": source[:3],
        "gap": source[:3] + source[4:],
        "unfinished": [
            c.model_copy(update={"timestamp": c.timestamp + timedelta(minutes=1)}) for c in source
        ],
    }[kind]
    with pytest.raises(ValueError):
        run_walk_forward(source, config)


def test_hand_calculated_execution_benchmark_and_stitch() -> None:
    config = settings(stitch_oos=True, fee=0.01, execution={"spread_bps": 20, "slippage_bps": 10})
    source = history(config, [10, 20, 10, 30, 10, 5, 10, 15])
    source = [
        c.model_copy(update={"open": 10, "high": max(10, c.close), "low": min(10, c.close)})
        for c in source
    ]
    report = run_walk_forward(source, config)
    returns = []
    index = 100.0
    for i, row in enumerate(report.results):
        for segment, last in ((row.train, i * 2 + 1), (row.test, i * 2 + 3)):
            # Two candles: only first close can signal, fill at final open, liquidate final close.
            buy_reference = source[last].open
            sell_reference = source[last].close
            quantity = 1000 / (buy_reference * 1.002 * 1.01)
            final = quantity * sell_reference * 0.998 * 0.99
            result = segment.result
            assert result.final_balance == pytest.approx(final)
            assert result.trades[0].pnl == pytest.approx(final - 1000)
            assert result.costs.fees == pytest.approx(
                quantity * (buy_reference * 1.002 + sell_reference * 0.998) * 0.01
            )
            assert result.costs.modeled_spread_cost == pytest.approx(
                quantity * (buy_reference + sell_reference) * 0.001
            )
            assert result.costs.modeled_slippage_cost == pytest.approx(
                quantity * (buy_reference + sell_reference) * 0.001
            )
            expected_benchmark = (
                sell_reference * 0.998 * 0.99 / (source[last - 1].open * 1.002 * 1.01) - 1
            ) * 100
            assert result.buy_and_hold_return_percent == pytest.approx(expected_benchmark)
        returns.append(row.test.result.total_return_percent)
        index *= row.test.result.final_balance / 1000
    summary = report.summaries[0]
    assert summary.stitched_oos_index is not None
    assert summary.stitched_oos_index[-1].value == pytest.approx(index)
    assert summary.median_test_return_percent == median(returns)
    assert summary.minimum_test_return_percent == min(returns)
    assert summary.maximum_test_return_percent == max(returns)
    assert summary.total_test_trades == 3
    assert summary.positive_test_folds == sum(v > 0 for v in returns)
    assert summary.positive_test_fraction == sum(v > 0 for v in returns) / 3


def test_last_train_signal_cannot_execute_in_test_and_zero_trades() -> None:
    rules = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 15}), comparison(PRICE, "<", ZERO)
    )
    config = settings(strategies=[named("boundary", rules)])
    row = run_walk_forward(history(config, [10, 20, 10, 10, 10, 10, 10, 10]), config).results[0]
    for segment in (row.train, row.test):
        assert segment.result.total_trades == 0
        assert segment.result.win_rate is None
        assert segment.result.profit_factor is None
        assert segment.result.final_balance == 1000


@pytest.mark.parametrize("name,period", [("rsi", 2), ("ema", 2), ("sma", 2)])
def test_future_changes_and_added_strategy_do_not_move_seeds(name: str, period: int) -> None:
    rule = strategy(comparison(indicator(name, period), ">", ZERO), comparison(PRICE, "<", ZERO))
    config = settings(strategies=[named("a", rule)])
    source = history(config)
    first = run_walk_forward(source, config)
    boundary = required_warmup(config)
    changed = [
        c
        if i < boundary + 4
        else c.model_copy(update={"open": 100, "high": 100, "low": 100, "close": 100})
        for i, c in enumerate(source)
    ]
    assert run_walk_forward(changed, config).results[0] == first.results[0]
    changed_earlier = [
        c
        if i < boundary + 2
        else c.model_copy(update={"open": 100, "high": 100, "low": 100, "close": 100})
        for i, c in enumerate(source)
    ]
    assert run_walk_forward(changed_earlier, config).results[0].train == first.results[0].train
    longer = settings(
        strategies=[named("a", rule), named("b", strategy(comparison(indicator("ema", 10))))]
    )
    expanded = run_walk_forward(history(longer), longer)
    for added, original in zip(
        [r for r in expanded.results if r.strategy_id == "a"], first.results, strict=True
    ):
        assert added.train.result == original.train.result
        assert added.test.result == original.test.result
    assert expanded.shared_data.indicator_initializations[0].history_start is not None
    fewer = settings(
        period_days=3, evaluation_end=START + timedelta(days=3), strategies=[named("a", rule)]
    )
    assert run_walk_forward(history(fewer), fewer).results == first.results[:2]


def test_fetch_and_indicator_cache_once(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(
        strategies=[
            named("a", strategy(comparison(indicator("ema", 2)))),
            named("b", strategy(comparison(indicator("ema", 2)))),
        ]
    )
    calls = []
    original = indicators.ema

    def counted(series: pd.Series, period: int) -> pd.Series:
        calls.append(period)
        return original(series, period)

    monkeypatch.setattr(indicators, "ema", counted)
    provider = Provider(history(config))
    report = asyncio.run(fetch_and_walk_forward(provider, config))
    assert len(provider.requests) == 1 and calls == [2]
    assert len(report.results) == 6
    assert provider.requests[0][2] == START - timedelta(hours=120)


@pytest.mark.parametrize("mode", ["config", "ai"])
@pytest.mark.parametrize("as_json", [False, True])
def test_cli(
    mode: str,
    as_json: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = settings()

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        return history(config)

    def parse(text: str) -> WalkForwardConfig:
        assert mode == "ai"
        return config

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.setattr(parser, "parse_walk_forward", parse)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    path = tmp_path / "walk-forward.json"
    path.write_text(config.model_dump_json())
    args = ["--config", str(path)] if mode == "config" else ["Walk-forward BTCUSDT"]
    monkeypatch.setattr(
        "sys.argv", ["strategy-backtest", "walk-forward", *args, *(["--json"] if as_json else [])]
    )
    main()
    output = capsys.readouterr()
    assert output.err == ""
    if as_json:
        data = json.loads(output.out)
        assert len(data["folds"]) == 3
        assert data["results"][0]["train"]["result"]["initial_balance"] == 1000
        assert "NaN" not in output.out and "Infinity" not in output.out
    else:
        assert "Walk-Forward Analysis" in output.out and "Aggregate OOS" in output.out


def test_sdk_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    values = extraction(1)
    values.pop("sort_by")
    values.update(
        period_days=360,
        windows={
            "mode": "rolling",
            "train_days": 120,
            "test_days": 30,
            "step_days": None,
            "max_folds": None,
        },
        stitch_oos=None,
        execution=None,
    )
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        return httpx2.Response(
            200, json=response_payload({"configuration": values, "rejection": None})
        )

    install_transport(monkeypatch, handler)
    config = parser.parse_walk_forward("Walk-forward RSI on BTCUSDT over 360 days")
    assert len(requests) == 1 and config.windows.train_days == 120
    assert config.windows.step_days is None
    assert len(config.strategies) == 1


@pytest.mark.parametrize(
    "text", ["Optimize BTCUSDT", "Choose best BTCUSDT", "Adaptive BTCUSDT", "Predict BTCUSDT", ""]
)
def test_ai_rejects_unsupported(text: str) -> None:
    with pytest.raises(parser.StrategyParseError):
        parser.parse_walk_forward(text)


@pytest.mark.parametrize("name", ["rsi", "ema"])
def test_nonconstant_indicator_seed_invariance(name: str) -> None:
    rule = strategy(comparison(indicator(name, 2)), comparison(indicator(name, 2), ">"))
    solo = settings(strategies=[named("a", rule)])
    combined = settings(
        strategies=[named("a", rule), named("b", strategy(comparison(indicator("ema", 10))))]
    )

    def prices(config: WalkForwardConfig) -> list[Candle]:
        source = history(config)
        return [
            c.model_copy(update={"open": value, "close": value, "high": value, "low": value})
            for c in source
            for value in [10.0 + (int((c.timestamp - START).total_seconds() / 43200) % 7)]
        ]

    a = run_walk_forward(prices(solo), solo)
    b = run_walk_forward(prices(combined), combined)
    for first, second in zip(a.results, b.results[::2], strict=True):
        assert first.train.result == second.train.result
        assert first.test.result == second.test.result
    solo_seed = a.shared_data.indicator_initializations[0]
    assert solo_seed in b.shared_data.indicator_initializations


def test_test_indicator_uses_prior_train_close_without_train_signal_execution() -> None:
    rule = strategy(
        comparison(indicator("sma", 2), ">", {"type": "value", "value": 15}),
        comparison(PRICE, "<", ZERO),
    )
    config = settings(strategies=[named("sma", rule)])
    report = run_walk_forward(history(config, [10, 10, 10, 30, 10, 10, 10, 10, 10, 10]), config)
    row = report.results[0]
    assert row.train.result.total_trades == 0
    assert row.test.result.trades[0].entry_time == START + timedelta(hours=36)
    assert row.test.result.trades[0].exit_time < row.test.end


@pytest.mark.parametrize("count", [1, 5])
def test_strategy_count_limits_valid(count: int) -> None:
    config = settings(strategies=[named(f"s-{i}", ALWAYS) for i in range(count)])
    report = run_walk_forward(history(config), config)
    assert len(report.summaries) == count


@pytest.mark.parametrize("count", [0, 6])
def test_strategy_count_limits_invalid(count: int) -> None:
    with pytest.raises(ValueError):
        settings(strategies=[named(f"s-{i}", ALWAYS) for i in range(count)])


@pytest.mark.parametrize(
    "payload",
    [
        {"windows": {"train_days": "1", "test_days": 1}},
        {"windows": {"train_days": True, "test_days": 1}},
        {"windows": {"train_days": 1, "test_days": 1, "max_folds": 101}},
        {"windows": {"train_days": 1, "test_days": 1, "optimize": True}},
        {"unexpected": "field"},
    ],
)
def test_strict_configuration(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        settings(**payload)


def test_summary_exact_statistics() -> None:
    config = settings(stitch_oos=True)
    source = history(config, [10, 10, 10, 20, 10, 5, 10, 10])
    # Independent Test folds return +100%, -50%, 0% with the same starting capital.
    source = [
        c.model_copy(update={"open": 10, "high": max(10, c.close), "low": min(10, c.close)})
        for c in source
    ]
    summary = run_walk_forward(source, config).summaries[0]
    assert summary.median_test_return_percent == 0
    assert summary.minimum_test_return_percent == -50
    assert summary.maximum_test_return_percent == 100
    assert summary.positive_test_folds == 1
    assert summary.positive_test_fraction == 1 / 3
    assert summary.median_test_max_drawdown_percent == 0
    assert summary.median_test_excess_return_pp == 0
    assert summary.outperforming_test_folds == 0
    assert summary.stitched_oos_index is not None
    assert [point.value for point in summary.stitched_oos_index] == [100, 200, 100, 100]


@pytest.mark.parametrize("kind", ["missing_file", "invalid_json", "invalid_protocol"])
def test_cli_helpful_errors(kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from strategy_backtest_agent.walk_forward.cli import main as command

    path = tmp_path / "bad.json"
    if kind != "missing_file":
        path.write_text("{" if kind == "invalid_json" else '{"symbol":"BTCUSDT"}')
    with pytest.raises(SystemExit) as error:
        command(["--config", str(path), "--json"])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "Error:" in output.err


@pytest.mark.parametrize("reason", ["unsupported", "ambiguous", "inconsistent_settings"])
def test_ai_structured_rejection(reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda _: httpx2.Response(
            200, json=response_payload({"configuration": None, "rejection": reason})
        ),
    )
    with pytest.raises(parser.StrategyParseError, match="Request rejected"):
        parser.parse_walk_forward("Walk-forward BTCUSDT")
