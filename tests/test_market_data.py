import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from strategy_backtest_agent.market_data import BinanceMarketData, MarketDataError

START = datetime(2024, 1, 1, tzinfo=UTC)
BASE = int(START.timestamp() * 1000)


def row(hour: int) -> list[int | str]:
    return [
        BASE + hour * 3600000,
        "10",
        "12",
        "9",
        "11",
        "5",
        BASE + (hour + 1) * 3600000 - 1,
        "0",
        1,
        "0",
        "0",
        "0",
    ]


def test_pagination_sorting_and_incomplete_exclusion() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.url.path == "/api/v3/klines"
        assert "Authorization" not in request.headers
        assert request.url.params["symbol"] == "BTCUSDT"
        calls += 1
        if calls == 1:
            assert request.url.params["startTime"] == str(BASE)
            return httpx.Response(200, json=[row(1), row(0)])
        assert request.url.params["startTime"] == str(BASE + (calls - 1) * 3600000 + 1)
        return httpx.Response(200, json=[row(2)]) if calls == 2 else httpx.Response(200, json=[])

    provider = BinanceMarketData(httpx.MockTransport(handler))
    candles = asyncio.run(
        provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(hours=2, minutes=30))
    )
    assert [c.timestamp for c in candles] == [START, START + timedelta(hours=1)]
    assert calls == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "bad"},
        [[1]],
        [[BASE, "nan", "12", "9", "11", "5", BASE + 1, "0", 1, "0", "0", "0"]],
    ],
)
def test_invalid_responses(payload: object) -> None:
    provider = BinanceMarketData(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with pytest.raises(MarketDataError):
        asyncio.run(provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(days=1)))


@pytest.mark.parametrize("status", [429, 451, 500])
def test_http_errors(status: int) -> None:
    provider = BinanceMarketData(httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(MarketDataError):
        asyncio.run(provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(days=1)))


def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(MarketDataError):
        asyncio.run(
            BinanceMarketData(httpx.MockTransport(handler)).fetch_candles(
                "BTCUSDT", "1h", START, START + timedelta(days=1)
            )
        )


def test_nonadvancing_pagination_rejected() -> None:
    provider = BinanceMarketData(httpx.MockTransport(lambda _: httpx.Response(200, json=[row(0)])))
    with pytest.raises(MarketDataError, match="did not advance"):
        asyncio.run(provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(days=1)))


def test_conflicting_duplicates_rejected() -> None:
    changed = row(0)
    changed[5] = "20"
    provider = BinanceMarketData(
        httpx.MockTransport(lambda _: httpx.Response(200, json=[row(0), changed]))
    )
    with pytest.raises(MarketDataError, match="duplicate"):
        asyncio.run(provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(days=1)))


def test_180_days_paginates_beyond_provider_limit() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        first = (int(request.url.params["startTime"]) - BASE + 3599999) // 3600000
        return httpx.Response(200, json=[row(i) for i in range(first, min(first + 1000, 4320))])

    candles = asyncio.run(
        BinanceMarketData(httpx.MockTransport(handler)).fetch_candles(
            "BTCUSDT", "1h", START, START + timedelta(days=180)
        )
    )
    assert len(candles) == 4320
    assert calls == 6


def test_empty_response() -> None:
    provider = BinanceMarketData(httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    assert (
        asyncio.run(provider.fetch_candles("BTCUSDT", "1h", START, START + timedelta(days=1))) == []
    )


@pytest.mark.parametrize("minutes, expected", [(0, 720), (30, 719)])
def test_30_day_boundaries_keep_every_completed_hour(minutes: int, expected: int) -> None:
    start = START + timedelta(minutes=minutes)
    end = start + timedelta(days=30)

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = int(request.url.params["startTime"])
        assert request.url.params["endTime"] == str(int(end.timestamp() * 1000) - 1)
        rows = [row(i) for i in range(721) if int(row(i)[0]) >= cursor]
        return httpx.Response(200, json=rows[:1000])

    candles = asyncio.run(
        BinanceMarketData(httpx.MockTransport(handler)).fetch_candles("BTCUSDT", "1h", start, end)
    )
    assert len(candles) == expected
    assert candles[0].timestamp == START + timedelta(hours=bool(minutes))
    assert candles[-1].timestamp == START + timedelta(hours=719)
    assert all(
        b.timestamp - a.timestamp == timedelta(hours=1)
        for a, b in zip(candles, candles[1:], strict=False)
    )
