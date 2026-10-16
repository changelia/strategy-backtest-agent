"""Advanced operands across the existing engines, with financial and causality oracles."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pandas as pd
import pytest
from conftest import make_candles
from pydantic import BaseModel
from test_ai_parser import extraction, install_transport, response_payload
from test_comparison_engine import Provider, named
from test_rules import comparison, strategy
from test_validation_engine import ALWAYS, PRICE, ZERO

from strategy_backtest_agent import indicators
from strategy_backtest_agent.ai import parser
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.cli import main
from strategy_backtest_agent.comparison.engine import fetch_and_compare, run_comparison
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.costs.engine import run_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig
from strategy_backtest_agent.market_data import BinanceMarketData
from strategy_backtest_agent.models import BacktestConfig, Candle, ExecutionConfig
from strategy_backtest_agent.rules.evaluator import dependencies, prepare_context, warmup_count
from strategy_backtest_agent.rules.indicator_specs import indicator_key, prior_candles
from strategy_backtest_agent.rules.models import (
    ATRIndicator,
    BollingerIndicator,
    Indicator,
    MACDIndicator,
    RuleStrategy,
    TechnicalIndicator,
)
from strategy_backtest_agent.sensitivity.cache import prepare_train_context
from strategy_backtest_agent.sensitivity.engine import run_sensitivity
from strategy_backtest_agent.sensitivity.grid import expand_grid
from strategy_backtest_agent.sensitivity.models import ParameterSpec, SensitivityConfig
from strategy_backtest_agent.validation.engine import run_validation
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.engine import run_walk_forward
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

START = datetime(2024, 1, 1, tzinfo=UTC)
SPECS: list[TechnicalIndicator] = [
    MACDIndicator(name="macd", fast_period=2, slow_period=4, signal_period=3),
    BollingerIndicator(name="bollinger", period=3, multiplier=1, component="lower"),
    ATRIndicator(name="atr", period=3),
]


def rule_for(spec: TechnicalIndicator) -> RuleStrategy:
    return strategy(comparison(spec, ">", ZERO), comparison(PRICE, "<", ZERO))


def history(required: int, days: int = 4) -> list[Candle]:
    return [
        Candle(
            timestamp=START + timedelta(hours=i),
            open=100 + (i % 7),
            close=100 + ((i + 1) % 7),
            high=110 + (i % 7),
            low=90 + (i % 7),
            volume=1,
        )
        for i in range(-required, days * 24)
    ]


def settings(rule: RuleStrategy) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "period_days": 4,
        "evaluation_end": START + timedelta(days=4),
        "initial_balance": 1000,
        "fee": 0.01,
        "execution": {"spread_bps": 20, "slippage_bps": 10},
        "strategies": [named("advanced", rule)],
    }


@pytest.mark.parametrize("spec", SPECS)
def test_shared_comparison_fetch_once_complete_metadata_and_replay(
    spec: TechnicalIndicator,
) -> None:
    rule = rule_for(spec)
    config = ComparisonConfig.model_validate(
        {**settings(rule), "strategies": [named("advanced", rule), named("other", rule)]}
    )
    source = history(warmup_count(rule))
    provider = Provider(source)
    report = asyncio.run(fetch_and_compare(provider, config))
    assert len(provider.requests) == 1
    assert provider.requests[0][2] == START - timedelta(hours=prior_candles(spec))
    assert report.results[0].result == report.results[1].result
    assert report.shared_data.indicators == [spec]
    anchor = report.shared_data.indicator_initializations[0]
    assert anchor.indicator == spec
    assert anchor.history_start == source[0].timestamp
    assert anchor.prior_candle_count == prior_candles(spec)
    assert anchor.input_fields == (["high", "low", "close"] if spec.name == "atr" else ["close"])
    assert report.model_dump_json() == run_comparison(source, config).model_dump_json()


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_validation_walk_forward_isolation_future_mutation_and_more_folds(
    spec: TechnicalIndicator, mode: str
) -> None:
    rule = rule_for(spec)
    config = WalkForwardConfig.model_validate(
        {
            **settings(rule),
            "windows": {"mode": mode, "train_days": 1, "test_days": 1, "step_days": 1},
        }
    )
    boundary = warmup_count(rule)
    source = history(boundary)
    report = run_walk_forward(source, config)
    changed = [
        c
        if i < boundary + 48
        else c.model_copy(update={"high": 2000, "low": 1, "open": 1000, "close": 1000})
        for i, c in enumerate(source)
    ]
    assert run_walk_forward(changed, config).results[0] == report.results[0]
    shorter = WalkForwardConfig.model_validate(
        {**config.model_dump(), "period_days": 3, "evaluation_end": START + timedelta(days=3)}
    )
    assert run_walk_forward(source[:-24], shorter).results == report.results[:2]
    assert run_walk_forward(source, config).model_dump_json() == report.model_dump_json()
    for row in report.results:
        for segment in (row.train, row.test):
            assert segment.result.initial_balance == 1000
            for trade in segment.result.trades:
                assert segment.start < trade.entry_time <= trade.exit_time < segment.end
    validation = ValidationConfig.model_validate({**settings(rule), "train_ratio": 0.5})
    a = run_validation(source, validation)
    b = run_validation(changed, validation)
    assert a.results[0].train == b.results[0].train
    assert a.results[0].test.result.initial_balance == 1000


@pytest.mark.parametrize("spec", SPECS)
def test_cached_independent_values_all_prefixes_and_insufficient_warmup(
    spec: TechnicalIndicator,
) -> None:
    boundary = prior_candles(spec)
    source = history(boundary)
    key = indicator_key(spec)
    context, anchors = prepare_train_context(source, boundary, {key})
    independent = prepare_context(source, {key})
    assert context.indicators[key] == pytest.approx(independent.indicators[key], nan_ok=True)
    for stop in [boundary + 1, boundary + 5, len(source)]:
        prefix, _ = prepare_train_context(source[:stop], boundary, {key})
        assert prefix.indicators[key] == pytest.approx(context.indicators[key][:stop], nan_ok=True)
    with pytest.raises(ValueError, match="insufficient"):
        prepare_train_context(source[1:], boundary - 1, {key})
    assert anchors[0].history_start == source[0].timestamp


@pytest.mark.parametrize("name", ["macd", "bollinger"])
def test_component_family_computed_once(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    members: list[TechnicalIndicator]
    if name == "macd":
        spec = MACDIndicator(name="macd", fast_period=2, slow_period=4, signal_period=3)
        members = [
            spec.model_copy(update={"component": c}) for c in ("macd", "signal", "histogram")
        ]
        count = []
        original = indicators.macd

        def capture(
            series: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
        ) -> dict[str, pd.Series]:
            count.append(1)
            return original(series, fast_period, slow_period, signal_period)

        monkeypatch.setattr(indicators, "macd", capture)
    else:
        band = BollingerIndicator(name="bollinger", period=3, component="upper")
        members = [band.model_copy(update={"component": c}) for c in ("upper", "middle", "lower")]
        count = []
        original_band = indicators.bollinger

        def capture_band(
            series: pd.Series, period: int = 20, multiplier: float = 2
        ) -> dict[str, pd.Series]:
            count.append(1)
            return original_band(series, period, multiplier)

        monkeypatch.setattr(indicators, "bollinger", capture_band)
    keys = {indicator_key(item) for item in members}
    boundary = max(prior_candles(item) for item in members)
    context, _ = prepare_train_context(history(boundary), boundary, keys)
    assert count == [1] and len(context.indicators) == 3


def test_atr_high_low_input_perturbation_and_future_ohlc_causality() -> None:
    spec = ATRIndicator(name="atr", period=3)
    source = history(prior_candles(spec))
    key = indicator_key(spec)
    a = prepare_context(source, {key})
    changed = [
        c if i < 70 else c.model_copy(update={"high": c.high + 50}) for i, c in enumerate(source)
    ]
    b = prepare_context(changed, {key})
    assert a.prices == b.prices
    assert a.indicators[key][:70] == pytest.approx(b.indicators[key][:70], nan_ok=True)
    assert b.indicators[key][70] > a.indicators[key][70]


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("legacy", ["rsi", "sma", "ema"])
def test_adding_longer_new_indicator_preserves_legacy_results(
    spec: TechnicalIndicator, legacy: str
) -> None:
    old = rule_for(Indicator.model_validate({"name": legacy, "period": 2}))
    first_config = ComparisonConfig.model_validate(
        {**settings(old), "strategies": [named("old", old), named("duplicate", old)]}
    )
    combined = ComparisonConfig.model_validate(
        {**settings(old), "strategies": [named("old", old), named("new", rule_for(spec))]}
    )
    first = run_comparison(history(warmup_count(old)), first_config)
    second = run_comparison(history(max(warmup_count(old), prior_candles(spec))), combined)
    assert first.results[0].result == second.results[0].result


@pytest.mark.parametrize(
    "spec,path,values",
    [
        (SPECS[0], "fast_period", [1, 2, 3]),
        (SPECS[0], "slow_period", [3, 4, 6]),
        (SPECS[0], "signal_period", [1, 2, 3]),
        (SPECS[1], "period", [2, 3, 4]),
        (SPECS[1], "multiplier", [0.5, 1.0, 1.5]),
        (SPECS[2], "period", [2, 3, 4]),
    ],
)
def test_sensitivity_numeric_fields_and_seed_stability(
    spec: TechnicalIndicator, path: str, values: list[int | float]
) -> None:
    base = rule_for(spec)
    parameter = ParameterSpec(path=f"entry.left.{path}", values=values)
    definitions, variants = expand_grid(base, [parameter])
    assert definitions[0].values == values
    config_values = settings(base)
    config_values.pop("strategies")
    config = SensitivityConfig.model_validate(
        {**config_values, "base_strategy": base, "parameters": [parameter], "train_ratio": 0.5}
    )
    required = max(warmup_count(v.strategy) for v in variants)
    report = run_sensitivity(history(required), config)
    assert len(report.results) == 3
    single = config.model_copy(
        update={"parameters": [ParameterSpec(path=parameter.path, values=[values[0]])]}
    )
    small_required = warmup_count(variants[0].strategy)
    assert (
        run_sensitivity(history(small_required), single).results[0].train.result
        == report.results[0].train.result
    )
    assert all(r.train.end == START + timedelta(days=2) for r in report.results)


@pytest.mark.parametrize(
    "parameter",
    [
        {"path": "entry.left.fast_period", "values": [4]},
        {"path": "entry.left.signal_period", "values": [0]},
        {"path": "entry.left.fast_period", "values": [1.5]},
        {"path": "entry.left.component", "values": [1]},
    ],
)
def test_invalid_macd_grid_rejected(parameter: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        expand_grid(rule_for(SPECS[0]), [ParameterSpec.model_validate(parameter)])


def test_multiplier_nearby_fractional_and_macd_component_coupling() -> None:
    base = rule_for(SPECS[1])
    specs = [
        ParameterSpec.model_validate({"path": "entry.left.multiplier", "nearby": {"step": 0.25}})
    ]
    definitions, _ = expand_grid(base, specs)
    assert definitions[0].values == [0.75, 1.0, 1.25]
    with pytest.raises(ValueError, match="explicit step"):
        expand_grid(
            base, [ParameterSpec.model_validate({"path": "entry.left.multiplier", "nearby": {}})]
        )
    spec = MACDIndicator(name="macd", fast_period=2, slow_period=4, signal_period=3)
    base = strategy(comparison(spec, ">", spec.model_copy(update={"component": "signal"})))
    _, variants = expand_grid(
        base,
        [
            ParameterSpec(
                path="entry.left.fast_period",
                coupled_paths=["entry.right.fast_period"],
                values=[1, 2, 3],
            )
        ],
    )
    for variant in variants:
        left = variant.strategy.model_dump()["entry"]["left"]
        right = variant.strategy.model_dump()["entry"]["right"]
        assert left["fast_period"] == right["fast_period"]
        assert left["component"] == "macd" and right["component"] == "signal"


@pytest.mark.parametrize("spec", SPECS)
def test_cost_scenarios_and_unchanged_benchmark_for_equivalent_signals(
    spec: TechnicalIndicator,
) -> None:
    # Compare against ALWAYS when the advanced operand is guaranteed positive.
    chosen = spec
    rule = (
        strategy(
            comparison(spec, ">", {"type": "value", "value": -1e9}), comparison(PRICE, "<", ZERO)
        )
        if isinstance(spec, MACDIndicator)
        else rule_for(spec)
    )
    values = settings(rule)
    values.pop("strategies")
    values.pop("execution")
    config = CostScenarioConfig.model_validate(
        {
            **values,
            "strategy": rule,
            "train_ratio": 0.5,
            "scenarios": [
                {"id": "baseline", "name": "baseline"},
                {"id": "costs", "name": "costs", "spread_bps": 20, "slippage_bps": 10},
            ],
        }
    )
    source = history(prior_candles(chosen))
    report = run_cost_scenarios(source, config)
    always_config = CostScenarioConfig.model_validate({**config.model_dump(), "strategy": ALWAYS})
    # Same source cannot be supplied to a zero-warmup config: evaluate each with its declared range.
    always = run_cost_scenarios(history(0), always_config)
    for advanced, plain in zip(report.results, always.results, strict=True):
        assert advanced.train.result == plain.train.result


@pytest.mark.parametrize("kind", ["macd", "bollinger", "atr"])
def test_hand_calculated_signals_next_open_trades_and_costs(kind: str) -> None:
    if kind == "macd":
        spec = MACDIndicator(name="macd", fast_period=1, slow_period=2, signal_period=1)
        rule = strategy(comparison(spec, ">", ZERO), comparison(spec, "<", ZERO))
        source = make_candles([10, 12, 8, 8, 14, 7], [10, 11, 15, 20, 5, 9])
        entries, exits = [2, 5], [3, 5]
        references = [(15, 20), (9, 7)]
    elif kind == "bollinger":
        band = BollingerIndicator(name="bollinger", period=2, multiplier=0.5, component="lower")
        middle = band.model_copy(update={"component": "middle"})
        rule = strategy(comparison(PRICE, "<", band), comparison(PRICE, ">", middle))
        source = make_candles([10, 8, 12, 5, 10], [10, 8, 15, 20, 7])
        entries, exits = [2, 4], [3, 4]
        references = [(15, 20), (7, 10)]
    else:
        atr_spec = ATRIndicator(name="atr", period=2)
        rule = strategy(
            comparison(atr_spec, ">", {"type": "value", "value": 3}),
            comparison(atr_spec, ">", {"type": "value", "value": 5}),
        )
        source = make_candles([10, 15, 7, 9], [10, 14, 8, 8])
        source = [
            c.model_copy(update={"high": h, "low": low})
            for c, h, low in zip(source, [11, 16, 9, 10], [9, 14, 6, 7], strict=True)
        ]
        entries, exits = [2], [3]
        references = [(8, 8)]
    portfolio = BacktestConfig(
        initial_balance=1000,
        trading_fee=0.01,
        execution=ExecutionConfig(fee_rate=0.01, spread_bps=20, slippage_bps=10),
    )
    result = run_backtest(source, portfolio, rule)
    cash = 1000.0
    expected_fees = 0.0
    expected_spread = 0.0
    for buy, sell in references:
        quantity = cash / (buy * 1.002 * 1.01)
        expected_fees += quantity * (buy * 1.002 + sell * 0.998) * 0.01
        expected_spread += quantity * (buy + sell) * 0.001
        cash = quantity * sell * 0.998 * 0.99
    assert [t.entry_time for t in result.trades] == [source[i].timestamp for i in entries]
    assert [t.exit_time for t in result.trades] == [source[i].timestamp for i in exits]
    assert result.final_balance == pytest.approx(cash)
    assert sum(t.pnl for t in result.trades) == pytest.approx(cash - 1000)
    assert result.costs.fees == pytest.approx(expected_fees)
    assert result.costs.modeled_spread_cost == pytest.approx(expected_spread)
    assert result.costs.modeled_slippage_cost == pytest.approx(expected_spread)
    assert result.buy_and_hold_return_percent == pytest.approx(
        (source[-1].close * 0.998 * 0.99 / (source[0].open * 1.002 * 1.01) - 1) * 100
    )


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("workflow", ["ai", "compare", "validate", "sensitivity", "walk-forward"])
def test_actual_sdk_advanced_operands_all_parsers(
    spec: TechnicalIndicator, workflow: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = rule_for(spec)
    configuration: dict[str, object] = dict(settings(rule))
    configuration["evaluation_end"] = "2024-01-05T00:00:00Z"
    configuration["execution"] = None
    configuration["strategies"] = [{"name": "advanced", "strategy": rule.model_dump()}]
    parse: Callable[[str], BaseModel]
    if workflow == "ai":
        configuration = extraction(strategy=rule.model_dump(), execution=None)
        parse = parser.parse_strategy
    elif workflow == "compare":
        configuration["strategies"] = [
            {"name": "advanced", "strategy": rule.model_dump()},
            {"name": "other", "strategy": ALWAYS.model_dump()},
        ]
        configuration["sort_by"] = None
        parse = parser.parse_comparison
    elif workflow == "validate":
        configuration["train_ratio"] = 0.5
        parse = parser.parse_validation
    elif workflow == "sensitivity":
        configuration.pop("strategies")
        configuration["base_strategy"] = rule.model_dump()
        field = "fast_period" if spec.name == "macd" else "period"
        configuration["parameters"] = [{"path": f"entry.left.{field}", "values": [1, 2]}]
        configuration["train_ratio"] = 0.5
        parse = parser.parse_sensitivity
    else:
        configuration["windows"] = {
            "mode": "rolling",
            "train_days": 1,
            "test_days": 1,
            "step_days": 1,
            "max_folds": None,
        }
        configuration["stitch_oos"] = None
        parse = parser.parse_walk_forward
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False and "tools" not in body
        assert "ddof" not in body["instructions"] or "Population" in body["instructions"]
        assert "fast_period" in body["instructions"]
        assert "Reject any crosses" in body["instructions"]
        return httpx2.Response(
            200, json=response_payload({"configuration": configuration, "rejection": None})
        )

    install_transport(monkeypatch, handler)
    config = parse(f"Analyze {spec.name} on BTCUSDT")
    assert len(calls) == 1
    assert spec.name in config.model_dump_json()


@pytest.mark.parametrize(
    "text",
    ["MACD crosses above signal on BTCUSDT", "Bollinger crossover BTCUSDT", "ATR crossing BTCUSDT"],
)
def test_crossing_rejected_before_any_api(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("crossing must reject before extraction")

    monkeypatch.setattr(parser, "create_client", forbidden)
    with pytest.raises(parser.StrategyParseError, match="Unsupported"):
        parser.parse_strategy(text)


@pytest.mark.parametrize(
    "workflow", ["compare", "validate", "sensitivity", "costs", "walk-forward"]
)
@pytest.mark.parametrize("spec", SPECS)
def test_config_only_cli_json_advanced_operands(
    workflow: str,
    spec: TechnicalIndicator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rule = rule_for(spec)
    configuration = settings(rule)
    if workflow == "compare":
        configuration["strategies"] = [
            named("a", rule).model_dump(),
            named("b", ALWAYS).model_dump(),
        ]
    else:
        configuration["strategies"] = [named("a", rule).model_dump()]
    if workflow == "sensitivity":
        configuration.pop("strategies")
        configuration["base_strategy"] = rule.model_dump()
        field = "fast_period" if spec.name == "macd" else "period"
        configuration["parameters"] = [{"path": f"entry.left.{field}", "values": [1, 2]}]
    elif workflow == "costs":
        configuration.pop("strategies")
        configuration.pop("execution")
        configuration["strategy"] = rule.model_dump()
        configuration["scenarios"] = [
            {"id": "baseline", "name": "baseline"},
            {"id": "costs", "name": "costs", "spread_bps": 20},
        ]
    elif workflow == "walk-forward":
        configuration["windows"] = {"train_days": 1, "test_days": 1, "mode": "expanding"}
    configuration["evaluation_end"] = "2024-01-05T00:00:00Z"
    path = tmp_path / "advanced.json"
    path.write_text(json.dumps(configuration))
    requests = []

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        requests.append((start, end))
        return history(int((START - start).total_seconds() / 3600))

    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv", ["strategy-backtest", workflow, "--config", str(path), "--json"]
    )
    main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert output.err == "" and len(requests) == 1
    assert spec.name in output.out
    assert report["shared_data"]["indicator_initializations"]
    assert "NaN" not in output.out and "Infinity" not in output.out


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("workflow", ["compare", "validate", "rolling", "expanding"])
def test_adding_longer_advanced_strategy_never_moves_existing_advanced_seed(
    spec: TechnicalIndicator, workflow: str
) -> None:
    rule = rule_for(spec)
    long = rule_for(ATRIndicator(name="atr", period=10))
    reports: list[BaseModel] = []
    for extra in (rule, long):
        values = {**settings(rule), "strategies": [named("fixed", rule), named("extra", extra)]}
        source = history(max(warmup_count(rule), warmup_count(extra)))
        if workflow == "compare":
            reports.append(run_comparison(source, ComparisonConfig.model_validate(values)))
        elif workflow == "validate":
            reports.append(
                run_validation(
                    source, ValidationConfig.model_validate({**values, "train_ratio": 0.5})
                )
            )
        else:
            reports.append(
                run_walk_forward(
                    source,
                    WalkForwardConfig.model_validate(
                        {**values, "windows": {"mode": workflow, "train_days": 1, "test_days": 1}}
                    ),
                )
            )
    first, second = [report.model_dump() for report in reports]

    def financial_rows(report: dict[str, object]) -> list[object]:
        # Ignore physical shared-prefix lengths, which legitimately grow when the
        # provider fetch includes another dependency. Financial reports must match.
        rows = report["results"]
        assert isinstance(rows, list)
        return [
            row["result"] if "result" in row else (row["train"]["result"], row["test"]["result"])
            for row in rows
            if row.get("strategy_id", row.get("id")) == "fixed"
        ]

    assert financial_rows(first) == financial_rows(second)
    first_seed = next(
        a
        for a in first["shared_data"]["indicator_initializations"]
        if a["indicator"] == spec.model_dump()
    )
    second_seed = next(
        a
        for a in second["shared_data"]["indicator_initializations"]
        if a["indicator"] == spec.model_dump()
    )
    assert first_seed == second_seed


@pytest.mark.parametrize(
    "name", ["comparison", "validation", "sensitivity", "walk-forward", "costs"]
)
def test_documented_configs_validate(name: str) -> None:
    models: dict[str, type[BaseModel]] = {
        "comparison": ComparisonConfig,
        "validation": ValidationConfig,
        "sensitivity": SensitivityConfig,
        "walk-forward": WalkForwardConfig,
        "costs": CostScenarioConfig,
    }
    model = models[name]
    model.model_validate_json(
        (Path(__file__).resolve().parents[1] / "examples" / f"advanced-{name}.json").read_text()
    )


@pytest.mark.parametrize("spec", SPECS)
def test_ai_cli_metadata_uses_advanced_parameters(
    spec: TechnicalIndicator, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from strategy_backtest_agent.ai.models import AIStrategyConfig

    config = AIStrategyConfig(
        symbol="BTCUSDT", timeframe="1h", period_days=4, strategy=rule_for(spec)
    )

    def parse(text: str) -> AIStrategyConfig:
        return config

    requests = []

    async def fetch(
        self: BinanceMarketData, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        requests.append((start, end))
        # Completed exchange-aligned candles only. The request may end within an hour.
        first = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        last = end.replace(minute=0, second=0, microsecond=0)
        return [
            Candle(
                timestamp=first + timedelta(hours=i),
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1,
            )
            for i in range(int((last - first).total_seconds() / 3600))
        ]

    monkeypatch.setattr(parser, "parse_strategy", parse)
    monkeypatch.setattr(BinanceMarketData, "fetch_candles", fetch)
    monkeypatch.setattr("sys.argv", ["strategy-backtest", "ai", "Backtest BTCUSDT", "--json"])
    main()
    output = capsys.readouterr()
    result = json.loads(output.out)["backtest_result"]
    assert output.err == "" and len(requests) == 1
    assert result["indicator_configuration"] == [spec.model_dump(mode="json")]
    assert result["indicator_initializations"][0]["indicator"] == spec.model_dump(mode="json")


@pytest.mark.parametrize("local_seeds", [False, True])
def test_mixed_legacy_cached_values_do_not_shift_when_advanced_history_is_added(
    local_seeds: bool,
) -> None:
    # Multiple legacy periods are deliberate: single-period tests miss accidental
    # switches between legacy common seeds and dependency-local seeds.
    old_specs = [
        Indicator(name="rsi", period=2),
        Indicator(name="ema", period=6),
        Indicator(name="sma", period=3),
    ]
    keys = {indicator_key(spec) for spec in old_specs}
    a = prepare_context(history(30), keys, evaluation_start=30, local_seeds=local_seeds)
    added = indicator_key(ATRIndicator(name="atr", period=10))
    b = prepare_context(history(200), keys | {added}, evaluation_start=200, local_seeds=local_seeds)
    for key in keys:
        assert a.indicators[key][30:] == pytest.approx(b.indicators[key][200:])


@pytest.mark.parametrize("workflow", ["compare", "validate"])
def test_research_rejects_missing_advanced_warmup_without_moving_boundaries(workflow: str) -> None:
    rule = rule_for(SPECS[0])
    source = history(prior_candles(SPECS[0]))[1:]
    with pytest.raises(ValueError, match="insufficient warm-up"):
        if workflow == "compare":
            run_comparison(
                source,
                ComparisonConfig.model_validate(
                    {**settings(rule), "strategies": [named("a", rule), named("b", rule)]}
                ),
            )
        else:
            run_validation(source, ValidationConfig.model_validate(settings(rule)))


def test_atr_rejects_stale_high_low_context_and_prefix_preserves_inputs() -> None:
    rule = rule_for(ATRIndicator(name="atr", period=3))
    source = history(60)
    context = prepare_context(source, dependencies(rule), evaluation_start=60)
    changed = [c.model_copy(update={"high": c.high + 1}) for c in source]
    portfolio = BacktestConfig(initial_balance=1000)
    with pytest.raises(ValueError, match="ATR context"):
        run_backtest(changed, portfolio, rule, evaluation_start=60, context=context)
    prefix = context.prefix(80)
    assert prefix.range_inputs == [(c.high, c.low, c.close) for c in source[:80]]
    assert run_backtest(
        source[:80], portfolio, rule, evaluation_start=60, context=prefix
    ) == run_backtest(source[:80], portfolio, rule, evaluation_start=60)
