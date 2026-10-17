from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from strategy_backtest_agent.models import Candle


def make_candles(closes: list[float], opens: list[float] | None = None) -> list[Candle]:
    opens = opens if opens is not None else closes
    return [
        Candle(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i),
            open=o,
            high=max(o, c),
            low=min(o, c),
            close=c,
            volume=1,
        )
        for i, (o, c) in enumerate(zip(opens, closes, strict=True))
    ]


@pytest.fixture
def native_results() -> dict[str, dict[str, Any]]:
    from report_fixtures import make_native_results

    return make_native_results()
