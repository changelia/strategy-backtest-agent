import pandas as pd
import pytest

from strategy_backtest_agent.indicators import ema, rsi, sma


def test_sma() -> None:
    result = sma(pd.Series([1, 2, 3, 4]), 3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2:].tolist() == [2, 3]


def test_ema() -> None:
    result = ema(pd.Series([1, 2, 3, 4]), 3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2:].tolist() == [2.25, 3.125]


def test_wilder_rsi_known_reference() -> None:
    prices = pd.Series(
        [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
        ]
    )
    result = rsi(prices, 14)
    assert result.iloc[:14].isna().all()
    assert result.iloc[14] == pytest.approx(70.464135, abs=1e-6)
    assert result.iloc[15] == pytest.approx(66.249619, abs=1e-6)


@pytest.mark.parametrize("prices, expected", [([1, 2, 3], 100), ([3, 2, 1], 0), ([2, 2, 2], 50)])
def test_rsi_edges(prices: list[int], expected: int) -> None:
    assert rsi(pd.Series(prices), 2).iloc[-1] == expected


def test_insufficient_and_empty() -> None:
    for indicator in (sma, ema, rsi):
        assert indicator(pd.Series([1.0]), 3).isna().all()
        assert indicator(pd.Series([], dtype=float), 3).empty
        with pytest.raises(ValueError):
            indicator(pd.Series([1.0]), 0)
        with pytest.raises(ValueError):
            indicator(pd.Series([float("nan")]), 2)


def test_index_and_prefix_invariance() -> None:
    prices = pd.Series([3, 2, 1, 4, 5], index=[10, 20, 30, 40, 50])
    for indicator in (sma, ema, rsi):
        pd.testing.assert_series_equal(indicator(prices, 2).iloc[:4], indicator(prices.iloc[:4], 2))


def test_wilder_rsi_hand_calculated_seed_and_smoothing() -> None:
    # Changes: +2, -1, +3, -2, 0, +3. Seed gain=5/3, loss=1/3.
    # Next gain=10/9, loss=8/9; flat step preserves their ratio.
    # Final gain=121/81, loss=32/81. These fractions are independent of the implementation.
    values = rsi(pd.Series([10, 12, 11, 14, 12, 12, 15]), 3)
    assert values.iloc[:3].isna().all()
    assert values.iloc[3:].tolist() == pytest.approx(
        [100 * 5 / 6, 100 * 10 / 18, 100 * 10 / 18, 100 * 121 / 153], rel=1e-12
    )
