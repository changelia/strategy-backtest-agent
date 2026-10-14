"""Descriptive grid statistics and declared-grid adjacency, without ranking."""

from statistics import median

from strategy_backtest_agent.sensitivity.models import (
    MIN_OBSERVATION_TRADES,
    SIMILARITY_TOLERANCE_PP,
    NeighborComparison,
    Observation,
    ParameterDefinition,
    ParameterVariant,
    ReturnMatrix,
    SensitivitySummary,
    SeriesPoint,
    VariantResult,
)


def describe_grid(
    parameters: list[ParameterDefinition],
    variants: list[ParameterVariant],
    results: list[VariantResult],
) -> tuple[
    SensitivitySummary, list[NeighborComparison], list[SeriesPoint] | None, ReturnMatrix | None
]:
    returns = [row.train.result.total_return_percent for row in results]
    summary = SensitivitySummary(
        variant_count=len(results),
        minimum_return_percent=min(returns),
        median_return_percent=median(returns),
        maximum_return_percent=max(returns),
        return_range_pp=max(returns) - min(returns),
        positive_return_percent=sum(value > 0 for value in returns) / len(results) * 100,
        outperforming_buy_and_hold_percent=(
            sum(
                row.train.excess_return_pp is not None and row.train.excess_return_pp > 0
                for row in results
            )
            / len(results)
            * 100
        )
        if all(row.train.excess_return_pp is not None for row in results)
        else None,
        insufficient_trade_variant_ids=[
            row.variant_id
            for row in results
            if row.train.result.total_trades < MIN_OBSERVATION_TRADES
        ],
    )
    lookup = {
        tuple(variant.coordinates): (variant, result)
        for variant, result in zip(variants, results, strict=True)
    }
    neighbors = []
    adjacency: dict[str, list[VariantResult]] = {row.variant_id: [] for row in results}
    for variant, result in zip(variants, results, strict=True):
        for dimension, parameter in enumerate(parameters):
            coordinate = list(variant.coordinates)
            coordinate[dimension] += 1
            if tuple(coordinate) not in lookup:
                continue
            other, other_result = lookup[tuple(coordinate)]
            adjacency[variant.id].append(other_result)
            adjacency[other.id].append(result)
            neighbors.append(
                NeighborComparison(
                    first_variant_id=variant.id,
                    second_variant_id=other.id,
                    parameter_path=parameter.path,
                    return_difference_pp=other_result.train.result.total_return_percent
                    - result.train.result.total_return_percent,
                    sufficient_trades=min(
                        result.train.result.total_trades, other_result.train.result.total_trades
                    )
                    >= MIN_OBSERVATION_TRADES,
                )
            )
    for index, row in enumerate(results):
        adjacent = adjacency[row.variant_id]
        observation: Observation
        if row.train.result.total_trades < MIN_OBSERVATION_TRADES:
            observation = "insufficient_trades"
        elif not adjacent:
            observation = "no_neighbors"
        elif any(item.train.result.total_trades < MIN_OBSERVATION_TRADES for item in adjacent):
            observation = "insufficient_neighbor_trades"
        else:
            differences = [
                row.train.result.total_return_percent - item.train.result.total_return_percent
                for item in adjacent
            ]
            if all(abs(value) <= SIMILARITY_TOLERANCE_PP for value in differences):
                observation = "similar_to_all_neighbors"
            elif len(adjacent) >= 2 and all(
                value > SIMILARITY_TOLERANCE_PP for value in differences
            ):
                observation = "isolated_positive_spike"
            else:
                observation = "mixed_neighbors"
        results[index] = VariantResult(
            variant_id=row.variant_id, train=row.train, observation=observation
        )
    series = None
    matrix = None
    if len(parameters) == 1:
        series = [
            SeriesPoint(
                value=parameters[0].values[variant.coordinates[0]],
                variant_id=variant.id,
                return_percent=row.train.result.total_return_percent,
                total_trades=row.train.result.total_trades,
            )
            for variant, row in zip(variants, results, strict=True)
        ]
    elif len(parameters) == 2:
        rows = [
            [lookup[(i, j)] for j in range(len(parameters[1].values))]
            for i in range(len(parameters[0].values))
        ]
        matrix = ReturnMatrix(
            row_parameter=parameters[0].path,
            column_parameter=parameters[1].path,
            row_values=parameters[0].values,
            column_values=parameters[1].values,
            variant_ids=[[variant.id for variant, _ in row] for row in rows],
            returns_percent=[
                [result.train.result.total_return_percent for _, result in row] for row in rows
            ],
            trade_counts=[[result.train.result.total_trades for _, result in row] for row in rows],
        )
    return summary, neighbors, series, matrix
