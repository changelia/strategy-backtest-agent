"""Grid-independent finite indicator seeds, using only prior history and Train."""

from collections.abc import Sequence

from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import Context, indicator_warmup, prepare_context
from strategy_backtest_agent.rules.models import Indicator
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
    cache: dict[tuple[str, int], list[float]] = {}
    initializations = []
    for name, period in sorted(indicator_dependencies):
        indicator = Indicator.model_validate({"name": name, "period": period})
        required = indicator_warmup(name, period)
        if evaluation_start < required:
            raise ValueError(
                f"insufficient {name}({period}) prior history: need {required} candles"
            )
        start = evaluation_start - required
        key = (name, period)
        local = prepare_context(candles[start:], {key})
        cache[key] = [float("nan")] * start + local.indicators[key]
        initializations.append(
            IndicatorInitialization(
                indicator=indicator,
                prior_candle_count=required,
                history_start=candles[start].timestamp,
            )
        )
    return Context([c.close for c in candles], cache), initializations
