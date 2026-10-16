"""Grid-independent finite indicator seeds, using only prior history and Train."""

from collections.abc import Sequence

from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import Context, prepare_context
from strategy_backtest_agent.rules.indicator_specs import initialization_profiles
from strategy_backtest_agent.sensitivity.models import IndicatorInitialization


def prepare_train_context(
    candles: Sequence[Candle],
    evaluation_start: int,
    indicator_dependencies: set[tuple[str, int]],
) -> tuple[Context, list[IndicatorInitialization]]:
    """Anchor each unique dependency to its own warm-up before first Train open.

    Extra candles fetched for longer grid periods cannot change shorter-period seeds.
    Prefix NaNs align each locally prepared series with the shared candle sequence;
    no prefix is evaluated and the existing indicator formulas remain unchanged.
    """
    if not 0 <= evaluation_start < len(candles):
        raise ValueError("invalid Train evaluation_start")
    context = prepare_context(
        candles, indicator_dependencies, evaluation_start=evaluation_start, local_seeds=True
    )
    return context, initialization_profiles(candles, evaluation_start, indicator_dependencies)
