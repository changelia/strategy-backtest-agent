"""Structural path resolution and bounded deterministic DSL mutation, without prices."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from math import prod
from typing import Any

from pydantic import ValidationError

from strategy_backtest_agent.rules.models import Comparison, Group, Indicator, RuleStrategy, Value
from strategy_backtest_agent.sensitivity.models import (
    MAX_DIMENSIONS,
    MAX_VARIANTS,
    Number,
    ParameterDefinition,
    ParameterSpec,
    ParameterVariant,
)


@dataclass(frozen=True)
class Location:
    operand: Indicator | Value
    comparison: Comparison

    @property
    def value(self) -> Number:
        return self.operand.period if isinstance(self.operand, Indicator) else self.operand.value

    @property
    def is_rsi_threshold(self) -> bool:
        return isinstance(self.operand, Value) and any(
            isinstance(item, Indicator) and item.name == "rsi"
            for item in (self.comparison.left, self.comparison.right)
        )


def locate_parameter(strategy: RuleStrategy, path: str) -> Location:
    """Only entry/exit(.conditions.N)*.(left|right).(period|value) are mutable."""
    parts = path.split(".")
    if not parts or parts[0] not in ("entry", "exit"):
        raise ValueError(f"invalid parameter path {path!r}: start with entry or exit")
    node = strategy.entry if parts[0] == "entry" else strategy.exit
    cursor = 1
    while isinstance(node, Group):
        if cursor + 1 >= len(parts) or parts[cursor] != "conditions":
            raise ValueError(f"ambiguous parameter path {path!r}: specify conditions.<index>")
        index = parts[cursor + 1]
        if not index.isascii() or not index.isdigit() or str(int(index)) != index:
            raise ValueError(f"invalid parameter path {path!r}: use canonical zero-based indices")
        if int(index) >= len(node.conditions):
            raise ValueError(f"invalid parameter path {path!r}: condition index out of range")
        node = node.conditions[int(index)]
        cursor += 2
    if len(parts) != cursor + 2 or parts[cursor] not in ("left", "right"):
        raise ValueError(f"invalid parameter path {path!r}: select a numeric operand field")
    operand = node.left if parts[cursor] == "left" else node.right
    field = parts[cursor + 1]
    if isinstance(operand, Indicator) and field == "period":
        return Location(operand, node)
    if isinstance(operand, Value) and field == "value":
        other = node.right if parts[cursor] == "left" else node.left
        if isinstance(other, Value):
            raise ValueError(f"unsafe parameter path {path!r}: constant-to-constant comparison")
        return Location(operand, node)
    raise ValueError(f"invalid parameter path {path!r}: only indicator period or constant value")


def _number(value: Decimal, location: Location, path: str) -> Number:
    if isinstance(location.operand, Indicator):
        if value != value.to_integral_value():
            raise ValueError(f"{path}: indicator periods must be integers")
        return int(value)
    return float(value)


def candidate_values(spec: ParameterSpec, location: Location) -> list[Number]:
    if spec.values is not None:
        if isinstance(location.operand, Indicator) and any(type(v) is not int for v in spec.values):
            raise ValueError(f"{spec.path}: explicit indicator periods must be integer values")
        return list(spec.values)
    if spec.range is not None:
        start, stop, step = map(
            lambda v: Decimal(str(v)), (spec.range.start, spec.range.stop, spec.range.step)
        )
        intervals = (stop - start) / step
        if intervals != intervals.to_integral_value():
            raise ValueError(f"{spec.path}: inclusive range stop must be reachable by the step")
        count = int(intervals) + 1
        if count > MAX_VARIANTS:
            raise ValueError(f"{spec.path}: range exceeds {MAX_VARIANTS} candidates")
        if isinstance(location.operand, Indicator) and any(
            v != v.to_integral_value() for v in (start, stop, step)
        ):
            raise ValueError(f"{spec.path}: indicator ranges require integer bounds and step")
        return [_number(start + step * i, location, spec.path) for i in range(count)]
    assert spec.nearby is not None
    step_value = spec.nearby.step
    if step_value is None:
        if isinstance(location.operand, Indicator):
            step_value = 1
        elif location.is_rsi_threshold:
            step_value = 5
        else:
            raise ValueError(f"{spec.path}: nearby constants require an explicit step")
    step = Decimal(str(step_value))
    if isinstance(location.operand, Indicator) and step != step.to_integral_value():
        raise ValueError(f"{spec.path}: nearby indicator step must be an integer")
    base = Decimal(str(location.value))
    return [
        _number(base + step * offset, location, spec.path)
        for offset in range(-spec.nearby.steps, spec.nearby.steps + 1)
    ]


def _set_value(tree: dict[str, Any], path: str, value: Number) -> None:
    node: Any = tree
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node[parts[-1]] = value


def _validate_rsi_order(strategy: RuleStrategy) -> None:
    # Preserve the existing legacy RSI threshold ordering for the equivalent simple
    # buy-below / sell-above DSL. Arbitrary compound rules retain their DSL semantics.
    entry, exit = strategy.entry, strategy.exit
    if not isinstance(entry, Comparison) or not isinstance(exit, Comparison):
        return
    if (
        isinstance(entry.left, Indicator)
        and entry.left.name == "rsi"
        and entry.left == exit.left
        and isinstance(entry.right, Value)
        and isinstance(exit.right, Value)
        and entry.operator in ("<", "<=")
        and exit.operator in (">", ">=")
        and entry.right.value >= exit.right.value
    ):
        raise ValueError("simple RSI entry threshold must be below exit threshold")


def expand_grid(
    base_strategy: RuleStrategy, specs: list[ParameterSpec]
) -> tuple[list[ParameterDefinition], list[ParameterVariant]]:
    """Validate all combinations before any data fetch; declared order defines adjacency."""
    if not 1 <= len(specs) <= MAX_DIMENSIONS:
        raise ValueError(f"grid requires 1–{MAX_DIMENSIONS} dimensions")
    base = RuleStrategy.model_validate(base_strategy.model_dump(warnings=False))
    _validate_rsi_order(base)
    paths = [path for spec in specs for path in (spec.path, *spec.coupled_paths)]
    if len(paths) != len(set(paths)):
        raise ValueError("parameter paths must be unique across all dimensions and couplings")
    definitions = []
    for spec in specs:
        spec = ParameterSpec.model_validate(spec.model_dump(warnings=False))
        location = locate_parameter(base, spec.path)
        for path in spec.coupled_paths:
            other = locate_parameter(base, path)
            if type(location.operand) is not type(other.operand) or location.value != other.value:
                raise ValueError(f"{path}: coupled paths must have matching kinds and base values")
            if isinstance(location.operand, Indicator) and location.operand != other.operand:
                raise ValueError(f"{path}: coupled indicators must share the same name and period")
            if location.is_rsi_threshold != other.is_rsi_threshold:
                raise ValueError(f"{path}: cannot couple RSI thresholds with other constants")
        values = candidate_values(spec, location)
        if len(values) != len(set(values)):
            raise ValueError(f"{spec.path}: generated duplicate values; use a representable step")
        if location.is_rsi_threshold and any(not 0 <= value <= 100 for value in values):
            raise ValueError(f"{spec.path}: RSI thresholds must be between 0 and 100")
        definitions.append(
            ParameterDefinition(
                path=spec.path,
                coupled_paths=spec.coupled_paths,
                base_value=location.value,
                values=values,
            )
        )
    if prod(len(item.values) for item in definitions) > MAX_VARIANTS:
        raise ValueError(
            f"grid exceeds {MAX_VARIANTS} variants; reduce candidate sets or dimensions"
        )
    variants = []
    for number, coordinates in enumerate(
        product(*(range(len(item.values)) for item in definitions)), start=1
    ):
        tree = base.model_dump()
        values_by_path: dict[str, Number] = {}
        for definition, coordinate in zip(definitions, coordinates, strict=True):
            value = definition.values[coordinate]
            values_by_path[definition.path] = value
            for path in (definition.path, *definition.coupled_paths):
                _set_value(tree, path, value)
        try:
            strategy = RuleStrategy.model_validate(tree)
            _validate_rsi_order(strategy)
        except (ValidationError, ValueError) as exc:
            detail = (
                "; ".join(e["msg"] for e in exc.errors())
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            raise ValueError(
                f"invalid variant {values_by_path}: {detail}; adjust the grid"
            ) from None
        variants.append(
            ParameterVariant(
                id=f"variant-{number:03d}",
                coordinates=list(coordinates),
                parameter_values=values_by_path,
                strategy=strategy,
            )
        )
    return definitions, variants
