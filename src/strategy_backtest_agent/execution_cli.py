"""Shared cost flags; explicit CLI values override parsed/config values and are revalidated."""

import argparse
from typing import TypeVar

from pydantic import BaseModel

ConfigT = TypeVar("ConfigT", bound=BaseModel)


def add_cost_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spread-bps", type=float, help="FULL illustrative bid/ask spread in bps")
    parser.add_argument(
        "--slippage-bps", type=float, help="Adverse illustrative slippage in bps per side"
    )


def override_execution(config: ConfigT, args: argparse.Namespace) -> ConfigT:
    if args.spread_bps is None and args.slippage_bps is None:
        return config
    # All supported configs expose normalized legacy fee aliases; avoid coupling
    # this CLI helper to the AI package or individual engine models.
    values = config.model_dump()
    raw = values.get("execution")
    execution = (
        dict(raw)
        if isinstance(raw, dict)
        else {"fee_rate": values.get("fee", values.get("trading_fee", 0.001))}
    )
    if args.spread_bps is not None:
        execution["spread_bps"] = args.spread_bps
    if args.slippage_bps is not None:
        execution["slippage_bps"] = args.slippage_bps
    return type(config).model_validate({**values, "execution": execution})
