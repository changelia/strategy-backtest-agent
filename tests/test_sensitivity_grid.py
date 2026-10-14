"""Validated structural mutation and bounded Cartesian grids, without market data."""

import math

import pytest
from pydantic import ValidationError
from test_comparison_engine import END
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent.rules.models import Comparison, Indicator, RuleStrategy, Value
from strategy_backtest_agent.sensitivity.grid import expand_grid, locate_parameter
from strategy_backtest_agent.sensitivity.models import (
    NearbyValues,
    ParameterSpec,
    SensitivityConfig,
)

PRICE = {"type": "price"}
ZERO = {"type": "value", "value": 0}
RSI = strategy(
    comparison(indicator("rsi", 2)),
    comparison(indicator("rsi", 2), ">", {"type": "value", "value": 70}),
)


def spec(path: str = "entry.right.value", **updates: object) -> ParameterSpec:
    return ParameterSpec.model_validate({"path": path, "values": [25, 30, 35], **updates})


def settings(**updates: object) -> SensitivityConfig:
    return SensitivityConfig.model_validate(
        {
            "symbol": "BTCUSDT",
            "period_days": 1,
            "evaluation_end": END,
            "base_strategy": RSI,
            "parameters": [spec()],
            **updates,
        }
    )


def test_explicit_values_stable_ids_order_and_unmutated_base() -> None:
    before = RSI.model_dump_json()
    parameters = [spec(values=[35, 25, 30]), spec("exit.right.value", values=[65, 75])]
    definitions, variants = expand_grid(RSI, parameters)
    assert definitions[0].values == [35, 25, 30]
    assert [item.id for item in variants] == [f"variant-{i:03d}" for i in range(1, 7)]
    assert [item.coordinates for item in variants] == [
        [0, 0],
        [0, 1],
        [1, 0],
        [1, 1],
        [2, 0],
        [2, 1],
    ]
    assert [list(item.parameter_values.values()) for item in variants] == [
        [35, 65],
        [35, 75],
        [25, 65],
        [25, 75],
        [30, 65],
        [30, 75],
    ]
    assert expand_grid(RSI, parameters) == (definitions, variants)
    assert RSI.model_dump_json() == before
    assert isinstance(RSI.entry, Comparison) and isinstance(RSI.exit, Comparison)
    for variant in variants:
        assert isinstance(variant.strategy.entry, Comparison)
        assert isinstance(variant.strategy.exit, Comparison)
        assert isinstance(variant.strategy.entry.right, Value)
        assert variant.strategy.entry.left == RSI.entry.left
        assert variant.strategy.exit.left == RSI.exit.left
        assert variant.strategy.entry.operator == "<"
        assert variant.strategy.exit.operator == ">"
        assert variant.strategy.entry.right.value == variant.parameter_values["entry.right.value"]


@pytest.mark.parametrize(
    "path", ["entry.left.period", "entry.right.value", "exit.left.period", "exit.right.value"]
)
def test_valid_paths(path: str) -> None:
    assert locate_parameter(RSI, path).value in (2, 30, 70)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "rsi",
        "period",
        "entry.period",
        "entry.left.name",
        "entry.operator",
        "entry.left.value",
        "entry.right.period",
        "entry.right.value.foo",
        "Entry.right.value",
        "entry.conditions.0.right.value",
        "exit",
        "entry.__class__",
    ],
)
def test_invalid_paths(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        locate_parameter(RSI, path)


def nested() -> RuleStrategy:
    return strategy(
        {
            "type": "and",
            "conditions": [
                comparison(indicator("rsi", 2)),
                {
                    "type": "or",
                    "conditions": [
                        comparison(PRICE, ">", indicator("ema", 20)),
                        comparison(indicator("sma", 20), ">", indicator("sma", 50)),
                    ],
                },
            ],
        }
    )


def test_nested_and_or_mutates_only_exact_path() -> None:
    base = nested()
    path = "entry.conditions.1.conditions.1.left.period"
    _, variants = expand_grid(base, [spec(path, values=[10, 15])])
    for item, value in zip(variants, [10, 15], strict=True):
        expected = base.model_dump()
        expected["entry"]["conditions"][1]["conditions"][1]["left"]["period"] = value
        assert item.strategy.model_dump() == expected
        assert (
            locate_parameter(item.strategy, "exit.conditions.1.conditions.1.left.period").value
            == 20
        )
        assert (
            locate_parameter(item.strategy, "entry.conditions.1.conditions.0.right.period").value
            == 20
        )


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "conditions",
        "conditions.-1.left.period",
        "conditions.01.left.period",
        "conditions.3.left.period",
        "conditions.x.left.period",
        "conditions.١.left.period",
    ],
)
def test_ambiguous_or_invalid_nested_references(suffix: str) -> None:
    with pytest.raises(ValueError, match="path"):
        locate_parameter(nested(), "entry." + suffix)


@pytest.mark.parametrize("name", ["sma", "ema", "rsi"])
def test_coupled_and_independent_periods(name: str) -> None:
    base = strategy(comparison(indicator(name, 20)), comparison(indicator(name, 20)))
    _, independent = expand_grid(base, [spec("entry.left.period", values=[10, 15])])
    _, coupled = expand_grid(
        base, [spec("entry.left.period", values=[10, 15], coupled_paths=["exit.left.period"])]
    )
    assert locate_parameter(independent[0].strategy, "entry.left.period").value == 10
    assert locate_parameter(independent[0].strategy, "exit.left.period").value == 20
    assert locate_parameter(coupled[0].strategy, "exit.left.period").value == 10


@pytest.mark.parametrize("kind", ["name", "value", "type", "overlap", "same"])
def test_invalid_coupling(kind: str) -> None:
    base = strategy(
        comparison(indicator("sma", 20)),
        comparison(indicator("ema" if kind == "name" else "sma", 30 if kind == "value" else 20)),
    )
    paths = (
        ["entry.left.period"]
        if kind == "same"
        else ["entry.right.value"]
        if kind == "type"
        else ["exit.left.period"]
    )
    with pytest.raises(ValueError):
        parameters = [spec("entry.left.period", values=[10], coupled_paths=paths)]
        if kind == "overlap":
            parameters.append(spec("exit.left.period", values=[10]))
        expand_grid(base, parameters)


def test_explicit_equal_numeric_values_are_not_coupled() -> None:
    base = strategy(comparison(PRICE, "<", {"type": "value", "value": 30}))
    _, variants = expand_grid(base, [spec(values=[20])])
    assert isinstance(variants[0].strategy.exit, Comparison)
    assert isinstance(variants[0].strategy.exit.right, Value)
    assert variants[0].strategy.exit.right.value == 30


@pytest.mark.parametrize(
    "path,source,expected",
    [
        ("entry.right.value", {"range": {"start": 25, "stop": 35, "step": 5}}, [25, 30, 35]),
        ("entry.right.value", {"nearby": {}}, [25, 30, 35]),
        ("entry.left.period", {"nearby": {"step": 2, "steps": 1}}, [12, 14, 16]),
        ("entry.left.period", {"nearby": {}}, [13, 14, 15]),
        ("entry.left.period", {"range": {"start": 10, "stop": 14, "step": 2}}, [10, 12, 14]),
    ],
)
def test_ranges_and_nearby(path: str, source: dict[str, object], expected: list[int]) -> None:
    base = strategy(
        comparison(indicator("rsi", 14)),
        comparison(indicator("rsi", 14), ">", {"type": "value", "value": 70}),
    )
    definitions, _ = expand_grid(base, [ParameterSpec.model_validate({"path": path, **source})])
    assert definitions[0].values == expected


def test_decimal_range_expansion_and_constant_nearby() -> None:
    base = strategy(comparison(PRICE, ">", {"type": "value", "value": 0.2}))
    definition, _ = expand_grid(
        base,
        [
            ParameterSpec.model_validate(
                {"path": "entry.right.value", "range": {"start": 0.1, "stop": 0.3, "step": 0.1}}
            )
        ],
    )
    assert definition[0].values == [0.1, 0.2, 0.3]
    definition, _ = expand_grid(
        base, [ParameterSpec.model_validate({"path": "entry.right.value", "nearby": {"step": 0.1}})]
    )
    assert definition[0].values == [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="explicit step"):
        expand_grid(base, [ParameterSpec(path="entry.right.value", nearby=NearbyValues())])


@pytest.mark.parametrize(
    "values", [[], [30, 30], [30, 30.0], [True], ["30"], [math.inf], [math.nan]]
)
def test_invalid_values(values: object) -> None:
    with pytest.raises(ValidationError):
        spec(values=values)


@pytest.mark.parametrize("values", [[1], [501], [2.0], [2.5]])
def test_invalid_rsi_periods(values: list[float]) -> None:
    with pytest.raises(ValueError, match="integer|variant"):
        settings(parameters=[spec("entry.left.period", values=values)])


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"values": [30], "nearby": {}},
        {"values": [30], "range": {"start": 20, "stop": 30, "step": 5}},
        {"range": {"start": 35, "stop": 25, "step": 5}},
        {"range": {"start": 25, "stop": 35, "step": 0}},
        {"range": {"start": 25, "stop": 35, "step": -1}},
        {"range": {"start": 25, "stop": 35, "step": 3}},
        {"range": {"start": 0, "stop": 100, "step": 1}},
        {"nearby": {"steps": 0}},
        {"nearby": {"steps": 13}},
    ],
)
def test_invalid_sources(source: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        settings(parameters=[ParameterSpec.model_validate({"path": "entry.right.value", **source})])


@pytest.mark.parametrize(
    "source",
    [
        {"range": {"start": 2, "stop": 3, "step": 0.5}},
        {"nearby": {"step": 0.5}},
        {"nearby": {}},
    ],
)
def test_integer_period_ranges_and_nearby_are_not_clipped(source: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="integer|variant"):
        settings(parameters=[ParameterSpec.model_validate({"path": "entry.left.period", **source})])


@pytest.mark.parametrize(
    "source",
    [{"values": [-1, 30]}, {"values": [30, 101]}, {"nearby": {"step": 50}}, {"values": [30, 70]}],
)
def test_invalid_threshold_combinations_fail_entire_grid(source: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="threshold"):
        settings(parameters=[ParameterSpec.model_validate({"path": "entry.right.value", **source})])


def test_reversed_rsi_operand_threshold_bounds() -> None:
    base = strategy(comparison({"type": "value", "value": 30}, ">", indicator("rsi", 2)))
    with pytest.raises(ValueError, match="threshold"):
        expand_grid(base, [spec("entry.left.value", values=[101])])


def test_unsafe_constant_comparison_rejected() -> None:
    with pytest.raises(ValueError, match="constant-to-constant"):
        expand_grid(strategy(comparison(ZERO)), [spec("entry.left.value")])


def test_grid_size_and_dimension_caps() -> None:
    assert len(expand_grid(RSI, [spec(values=list(range(20, 45)))])[1]) == 25
    with pytest.raises(ValueError, match="25 variants"):
        settings(
            parameters=[
                spec(values=list(range(20, 26))),
                spec("exit.right.value", values=list(range(70, 75))),
            ]
        )
    with pytest.raises(ValidationError):
        settings(parameters=[spec(), spec(), spec(), spec()])
    with pytest.raises(ValueError, match="unique"):
        settings(parameters=[spec(), spec()])


def test_three_dimensional_product() -> None:
    config = settings(
        parameters=[
            spec(values=[25, 35]),
            spec("exit.right.value", values=[65, 75]),
            spec("entry.left.period", values=[2, 3], coupled_paths=["exit.left.period"]),
        ]
    )
    _, variants = expand_grid(config.base_strategy, config.parameters)
    assert len(variants) == 8
    assert variants[-1].coordinates == [1, 1, 1]


def test_revalidates_mutated_specs_and_dsl_complexity() -> None:
    parameter = spec()
    assert parameter.values is not None
    parameter.values.append(30)
    with pytest.raises(ValueError, match="duplicate"):
        expand_grid(RSI, [parameter])
    base = RSI.model_dump()
    base["entry"] = {"type": "and", "conditions": [base["entry"]] * 20}
    with pytest.raises(ValueError, match="comparisons"):
        settings(base_strategy=base)


@pytest.mark.parametrize("name", ["sma", "ema"])
def test_period_limits(name: str) -> None:
    base = strategy(comparison(indicator(name, 20)))
    _, variants = expand_grid(base, [spec("entry.left.period", values=[1000])])
    assert isinstance(variants[0].strategy.entry, Comparison)
    assert isinstance(variants[0].strategy.entry.left, Indicator)
    assert variants[0].strategy.entry.left.period == 1000
    with pytest.raises(ValueError, match="invalid variant"):
        expand_grid(base, [spec("entry.left.period", values=[1001])])


@pytest.mark.parametrize("ratio", [0.5, 0.7, 0.9])
def test_train_ratio_and_json_roundtrip(ratio: float) -> None:
    config = settings(train_ratio=ratio)
    assert SensitivityConfig.model_validate_json(config.model_dump_json()) == config


@pytest.mark.parametrize("ratio", [0.49, 0.91, True, "0.7", math.nan])
def test_invalid_train_ratio(ratio: object) -> None:
    with pytest.raises(ValidationError):
        settings(train_ratio=ratio)


def test_generated_duplicates_rejected_without_discarding_values() -> None:
    base = strategy(comparison(PRICE, ">", {"type": "value", "value": 1e100}))
    with pytest.raises(ValueError, match="duplicate"):
        settings(
            base_strategy=base,
            parameters=[ParameterSpec(path="entry.right.value", nearby=NearbyValues(step=1))],
        )
