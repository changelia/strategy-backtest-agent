"""Run all six research modes against deterministic synthetic demo candles."""

from strategy_backtest_agent import (
    BacktestClient,
    Comparison,
    CostScenario,
    CostScenarioConfig,
    Indicator,
    ParameterSpec,
    RuleStrategy,
    SensitivityConfig,
    Value,
)


def rsi_strategy(entry: float = 30, exit: float = 70) -> RuleStrategy:
    return RuleStrategy(
        entry=Comparison(
            left=Indicator(name="rsi", period=14), operator="<", right=Value(value=entry)
        ),
        exit=Comparison(
            left=Indicator(name="rsi", period=14), operator=">", right=Value(value=exit)
        ),
    )


def main() -> None:
    client = BacktestClient()
    backtest = client.run(config=client.template("backtest"), days=3, demo=True)
    comparison = client.compare(config=client.template("compare"), demo=True)
    validation = client.validate(config=client.template("validate"), demo=True)
    walk_forward = client.walk_forward(config=client.template("walk-forward"), demo=True)

    shared = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "period_days": 30,
        "initial_balance": 10000,
        "fee": 0.001,
    }
    sensitivity_config = SensitivityConfig(
        **shared,
        base_strategy=rsi_strategy(),
        parameters=[ParameterSpec(path="entry.right.value", values=[25, 30])],
    )
    sensitivity = client.sensitivity(config=sensitivity_config, demo=True)

    costs_config = CostScenarioConfig(
        **shared,
        strategy=rsi_strategy(),
        scenarios=[
            CostScenario(id="baseline", name="Baseline"),
            CostScenario(id="modeled", name="Illustrative costs", spread_bps=10, slippage_bps=5),
        ],
    )
    costs = client.costs(config=costs_config, demo=True)

    for label, result in (
        ("backtest", backtest),
        ("comparison", comparison),
        ("validation", validation),
        ("sensitivity", sensitivity),
        ("cost scenarios", costs),
        ("walk-forward", walk_forward),
    ):
        print(f"{label}: {result.research_type}")
        print(result.summary().splitlines()[0])


if __name__ == "__main__":
    main()
