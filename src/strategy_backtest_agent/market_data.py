"""Public read-only historical data, isolated from the backtest engine."""

import asyncio
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import ValidationError

from strategy_backtest_agent.models import Candle

TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d")


class MarketDataError(RuntimeError):
    """A market-data request failed or returned invalid candles."""


class MarketDataProvider(Protocol):
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Fetch completed candles within the UTC range [start, end)."""
        ...


class BinanceMarketData:
    """Fetch paginated public klines without credentials or trading endpoints."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("start and end must be timezone-aware, with start before end")
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        cursor = start_ms
        candles: dict[int, Candle] = {}
        try:
            async with httpx.AsyncClient(timeout=20.0, transport=self._transport) as client:
                while cursor < end_ms:
                    response = await client.get(
                        "https://data-api.binance.vision/api/v3/klines",
                        params={
                            "symbol": symbol,
                            "interval": timeframe,
                            "startTime": cursor,
                            "endTime": end_ms - 1,
                            "limit": 1000,
                        },
                    )
                    if response.status_code in (418, 429):
                        retry = response.headers.get("Retry-After", "unspecified")
                        raise MarketDataError(
                            f"Provider rate limit: retry after {retry}; no automatic retries"
                        )
                    response.raise_for_status()
                    rows = response.json()
                    if not isinstance(rows, list):
                        raise ValueError("expected a list of klines")
                    if not rows:
                        break
                    latest = cursor - 1
                    for row in rows:
                        if not isinstance(row, list) or len(row) != 12:
                            raise ValueError("expected a 12-field kline")
                        timestamp, close_time = int(row[0]), int(row[6])
                        if close_time < timestamp:
                            raise ValueError("invalid candle close time")
                        latest = max(latest, timestamp)
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(timestamp / 1000, UTC),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[5]),
                        )
                        if start_ms <= timestamp < end_ms and close_time < end_ms:
                            if timestamp in candles and candles[timestamp] != candle:
                                raise ValueError("conflicting duplicate candle")
                            candles[timestamp] = candle
                    if latest < cursor:
                        raise ValueError("pagination did not advance")
                    cursor = latest + 1
                    if cursor < end_ms:
                        await asyncio.sleep(0.2)
        except (httpx.HTTPError, ValueError, TypeError, OverflowError, ValidationError) as exc:
            raise MarketDataError(f"Unable to fetch valid historical candles: {exc}") from exc
        return [candles[key] for key in sorted(candles)]
