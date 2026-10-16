"""Complete, stable dependency identities and versioned finite initialization policies."""

import json
from collections.abc import Sequence

from pydantic import TypeAdapter

from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.models import (
    ATRIndicator,
    BollingerIndicator,
    Indicator,
    IndicatorInitialization,
    MACDIndicator,
    TechnicalIndicator,
)

# Preserve legacy (name, period) keys. Advanced identities encode every parameter and
# the fixed initialization convention in canonical JSON; the second slot is version 1.
# These are internal opaque identities, never user configuration or executable expressions.
INDICATOR_ADAPTER: TypeAdapter[TechnicalIndicator] = TypeAdapter(TechnicalIndicator)


def indicator_key(spec: TechnicalIndicator) -> tuple[str, int]:
    if isinstance(spec, Indicator):
        return spec.name, spec.period
    return json.dumps(spec.model_dump(), sort_keys=True, separators=(",", ":")), 1


def indicator_from_key(name: str, period: int) -> TechnicalIndicator:
    if name.startswith("{"):
        if period != 1:
            raise ValueError("unsupported indicator initialization version")
        return INDICATOR_ADAPTER.validate_json(name)
    return Indicator.model_validate({"name": name, "period": period})


def prior_candles(spec: TechnicalIndicator) -> int:
    if isinstance(spec, MACDIndicator):
        # Two sequential filters: allow ten slow spans for price EMAs, then ten
        # signal spans for the nested EMA. All components share this exact seed.
        return 10 * (spec.slow_period + spec.signal_period)
    if isinstance(spec, ATRIndicator):
        # Wilder decays more slowly than an EMA: twenty periods, not five spans.
        return 20 * spec.period
    if isinstance(spec, BollingerIndicator):
        return spec.period
    return 5 * spec.period if spec.name == "ema" else spec.period + (spec.name == "rsi")


def input_fields(spec: TechnicalIndicator) -> list[str]:
    return ["high", "low", "close"] if isinstance(spec, ATRIndicator) else ["close"]


def initialization_policy(spec: TechnicalIndicator) -> str:
    if isinstance(spec, MACDIndicator):
        return (
            "v1: first-close price EMAs; first available MACD signal seed; 10*(slow+signal) prior"
        )
    if isinstance(spec, ATRIndicator):
        return "v1: first TR high-low; SMA TR seed then Wilder; 20*period prior"
    if isinstance(spec, BollingerIndicator):
        return "v1: SMA and population std(ddof=0); period prior"
    return "legacy: RSI SMA/Wilder; SMA rolling; EMA first-close; configured history anchor"


def initialization_profiles(
    candles: Sequence[Candle],
    boundary: int,
    keys: set[tuple[str, int]],
    *,
    local_seeds: bool = True,
) -> list[IndicatorInitialization]:
    """Describe the exact anchors used by prepare_context, including OHLC requirements."""
    specs = [indicator_from_key(*key) for key in sorted(keys)]
    legacy_required = max(
        (prior_candles(spec) for spec in specs if isinstance(spec, Indicator)), default=0
    )
    profiles = []
    for spec in specs:
        required = (
            legacy_required
            if isinstance(spec, Indicator) and not local_seeds
            else prior_candles(spec)
        )
        if not 0 <= boundary < len(candles) or boundary < required:
            raise ValueError(f"insufficient {spec.name} prior history: need {required} candles")
        profiles.append(
            IndicatorInitialization(
                indicator=spec,
                prior_candle_count=required,
                history_start=candles[boundary - required].timestamp,
                input_fields=input_fields(spec),
                seed_policy=initialization_policy(spec),
            )
        )
    return profiles
