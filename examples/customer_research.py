"""Run all six modes offline and save independent raw JSON and deterministic reports.

Prerequisite: installed strategy-backtest-agent. Run in a fresh working directory.
No OpenAI or Binance request is made. Synthetic outcomes do not show profitability.
"""

from datetime import UTC, datetime
from pathlib import Path

from strategy_backtest_agent import (
    BacktestClient,
    BacktestConfig,
    Comparison,
    ComparisonConfig,
    CostScenario,
    CostScenarioConfig,
    ExecutionConfig,
    Indicator,
    NamedStrategy,
    ParameterSpec,
    RSIStrategy,
    RuleStrategy,
    SensitivityConfig,
    ValidationConfig,
    Value,
    WalkForwardConfig,
    WalkForwardWindowConfig,
)


def rsi_strategy() -> RuleStrategy:
    return RuleStrategy(
        entry=Comparison(
            left=Indicator(name="rsi", period=14), operator="<", right=Value(value=30.0)
        ),
        exit=Comparison(
            left=Indicator(name="rsi", period=14), operator=">", right=Value(value=70.0)
        ),
    )


def main() -> None:
    client = BacktestClient()
    output = Path("six-mode-results")
    output.mkdir(exist_ok=False)
    named = NamedStrategy(id="rsi-30", name="RSI 14 30/70", strategy=RSIStrategy())
    alternate = NamedStrategy(
        id="rsi-25", name="RSI 14 25/70", strategy=RSIStrategy(entry_below=25.0)
    )
    execution = ExecutionConfig(fee_rate=0.001, spread_bps=10.0, slippage_bps=5.0)
    shared = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "period_days": 30,
        "initial_balance": 10000.0,
        "fee": 0.001,
        "evaluation_end": datetime(2024, 7, 1, tzinfo=UTC),
    }
    backtest = client.run(config=BacktestConfig(execution=execution), days=30, demo=True)
    comparison = client.compare(
        config=ComparisonConfig(**shared, execution=execution, strategies=[named, alternate]),
        demo=True,
    )
    validation = client.validate(
        config=ValidationConfig(**shared, execution=execution, strategies=[named], train_ratio=0.7),
        demo=True,
    )
    sensitivity = client.sensitivity(
        config=SensitivityConfig(
            **shared,
            execution=execution,
            base_strategy=rsi_strategy(),
            parameters=[ParameterSpec(path="entry.right.value", values=[25.0, 30.0, 35.0])],
        ),
        demo=True,
    )
    costs = client.costs(
        config=CostScenarioConfig(
            **shared,
            strategy=rsi_strategy(),
            scenarios=[
                CostScenario(id="baseline", name="Fee-only baseline"),
                CostScenario(
                    id="modeled", name="Illustrative costs", spread_bps=10.0, slippage_bps=5.0
                ),
            ],
        ),
        demo=True,
    )
    walk_forward = client.walk_forward(
        config=WalkForwardConfig(
            **{**shared, "period_days": 60},
            execution=execution,
            strategies=[named],
            windows=WalkForwardWindowConfig(
                train_days=30, test_days=10, step_days=10, max_folds=10
            ),
            stitch_oos=True,
        ),
        demo=True,
    )
    for result in (backtest, comparison, validation, sensitivity, costs, walk_forward):
        print(result.research_type)
        print(result.summary().splitlines()[0])
        with (output / f"{result.research_type}-raw.json").open("x", encoding="utf-8") as stream:
            stream.write(result.to_json())
        result.save_report(output / f"{result.research_type}.md")
        result.save_report(output / f"{result.research_type}-report.json", format="json")
    print("Saved all six raw results and reports in", output.resolve())


if __name__ == "__main__":
    main()
