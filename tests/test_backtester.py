import pytest
from conftest import make_candles

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig
from strategy_backtest_agent.strategy import rsi_signals


def test_entry_exit_next_open_fees_and_pnl() -> None:
    candles = make_candles([10, 9, 8, 12, 13], [10, 9, 8, 7, 15])
    config = BacktestConfig(initial_balance=1000, trading_fee=0.01, rsi_period=2)
    result = run_backtest(candles, config)
    assert result.total_trades == 1
    trade = result.trades[0]
    assert trade.entry_time == candles[3].timestamp
    assert trade.exit_time == candles[4].timestamp
    assert trade.entry_price == 7
    assert trade.exit_price == 15
    assert trade.quantity == pytest.approx(1000 / (7 * 1.01))
    final = 1000 / (7 * 1.01) * 15 * 0.99
    assert result.final_balance == pytest.approx(final)
    assert trade.pnl == pytest.approx(final - 1000)
    assert trade.pnl_percent == pytest.approx((final / 1000 - 1) * 100)
    assert result.winning_trades == 1
    assert result.win_rate == 100


def test_forced_close_and_only_one_position() -> None:
    candles = make_candles([10, 9, 8, 7, 6])
    result = run_backtest(candles, BacktestConfig(rsi_period=2, trading_fee=0))
    assert result.total_trades == 1
    assert result.trades[0].entry_price == 7
    assert result.trades[0].exit_price == 6
    assert result.trades[0].exit_time == candles[-1].timestamp
    assert result.final_balance == pytest.approx(10000 * 6 / 7)
    assert result.losing_trades == 1
    assert result.profit_factor == 0


def test_final_signal_cannot_execute() -> None:
    result = run_backtest(make_candles([10, 9, 8]), BacktestConfig(rsi_period=2))
    assert result.total_trades == 0
    assert result.final_balance == 10000


@pytest.mark.parametrize("closes", [[], [10], [10, 10], [10] * 20, list(range(1, 21))])
def test_no_trade_and_insufficient(closes: list[float]) -> None:
    result = run_backtest(make_candles(closes), BacktestConfig())
    assert result.total_trades == 0
    assert result.final_balance == 10000
    assert result.win_rate is None
    assert result.profit_factor is None
    assert result.max_drawdown_percent == 0
    if not closes:
        assert result.buy_and_hold_return_percent is None


def test_strict_signal_thresholds() -> None:
    candles = make_candles([10, 9, 10])  # RSI exactly 50 at period 2
    assert rsi_signals(candles, BacktestConfig(rsi_period=2, entry_rsi=50, exit_rsi=70)) == [0] * 3
    assert rsi_signals(candles, BacktestConfig(rsi_period=2, entry_rsi=30, exit_rsi=50)) == [0] * 3


def test_future_prices_do_not_change_entry() -> None:
    first = make_candles([10, 9, 8, 12, 13], [10, 9, 8, 7, 15])
    second = make_candles([10, 9, 8, 100, 200], [10, 9, 8, 7, 150])
    config = BacktestConfig(rsi_period=2)
    a, b = run_backtest(first, config).trades[0], run_backtest(second, config).trades[0]
    assert (a.entry_time, a.entry_price, a.quantity) == (b.entry_time, b.entry_price, b.quantity)


def test_unsorted_and_duplicate_rejected() -> None:
    candles = make_candles([10, 9])
    for invalid in (candles[::-1], [candles[0], candles[0]]):
        with pytest.raises(ValueError, match="strictly increasing"):
            run_backtest(invalid, BacktestConfig())


def test_equity_drawdown_and_benchmark_fees() -> None:
    result = run_backtest(
        make_candles([10, 9, 8, 7, 3.5]), BacktestConfig(rsi_period=2, trading_fee=0)
    )
    assert result.max_drawdown_percent == pytest.approx(-50)
    result = run_backtest(make_candles([10, 10]), BacktestConfig(trading_fee=0.01))
    assert result.buy_and_hold_return_percent == pytest.approx((0.99 / 1.01 - 1) * 100)


def test_multiple_trades_compound_available_balance() -> None:
    candles = make_candles([10, 9, 8, 12, 13, 5, 4, 8, 9])
    config = BacktestConfig(rsi_period=2, trading_fee=0.01, initial_balance=1000)
    result = run_backtest(candles, config)
    assert result.total_trades == 2
    first, second = result.trades
    first_proceeds = first.quantity * first.exit_price * 0.99
    assert second.quantity * second.entry_price * 1.01 == pytest.approx(first_proceeds)
    assert result.final_balance == pytest.approx(1000 + first.pnl + second.pnl)


def test_equity_marks_unrealized_loss_before_recovery() -> None:
    result = run_backtest(
        make_candles([10, 9, 8, 7, 3.5, 7]),
        BacktestConfig(rsi_period=2, trading_fee=0),
    )
    assert result.final_balance == 10000
    assert result.max_drawdown_percent == pytest.approx(-50)


def test_entry_exit_fees_at_unchanged_price() -> None:
    result = run_backtest(
        make_candles([10, 9, 8, 7, 7]),
        BacktestConfig(rsi_period=2, trading_fee=0.01, initial_balance=1000),
    )
    trade = result.trades[0]
    assert trade.quantity * trade.entry_price == pytest.approx(1000 / 1.01)
    assert result.final_balance == pytest.approx(1000 / 1.01 * 0.99)
    assert trade.pnl == pytest.approx(result.final_balance - 1000)
    # No hypothetical exit fee at earlier marks, only the actual final liquidation.
    assert result.max_drawdown_percent == pytest.approx((0.99 / 1.01 - 1) * 100)


@pytest.mark.parametrize("fee", [0, 0.001, 0.01, 0.25])
def test_full_balance_sizing_and_each_trade_reconciliation(fee: float) -> None:
    config = BacktestConfig(rsi_period=2, trading_fee=fee, initial_balance=10000)
    candles = make_candles([10, 9, 8, 12, 13, 5, 4, 8, 9])
    result = run_backtest(candles, config)
    available = config.initial_balance
    assert result.total_trades == 2
    for trade in result.trades:
        entry_notional = trade.quantity * trade.entry_price
        entry_fee = entry_notional * fee
        exit_notional = trade.quantity * trade.exit_price
        exit_fee = exit_notional * fee
        assert trade.quantity == pytest.approx(available / (trade.entry_price * (1 + fee)))
        assert entry_notional + entry_fee == pytest.approx(available, rel=1e-12)
        assert available - entry_notional - entry_fee >= -available * 1e-12
        net_pnl = exit_notional - exit_fee - entry_notional - entry_fee
        assert trade.pnl == pytest.approx(net_pnl, rel=1e-12, abs=1e-9)
        assert trade.pnl_percent == pytest.approx(net_pnl / available * 100)
        available = exit_notional - exit_fee
        assert available >= 0
    assert result.final_balance == pytest.approx(available, rel=1e-12)
    assert config.initial_balance + sum(t.pnl for t in result.trades) == pytest.approx(
        result.final_balance, rel=1e-12, abs=1e-9
    )
    assert result.winning_trades + result.losing_trades == result.total_trades


def test_sell_execution_independent_of_execution_candle_close() -> None:
    config = BacktestConfig(rsi_period=2, trading_fee=0)
    for final_close in [1, 13, 1000]:
        candles = make_candles([10, 9, 8, 12, final_close], [10, 9, 8, 7, 15])
        assert rsi_signals(candles, config)[:4] == [0, 0, 1, -1]
        trade = run_backtest(candles, config).trades[0]
        assert trade.entry_time == candles[3].timestamp
        assert trade.entry_price == candles[3].open == 7
        assert trade.exit_time == candles[4].timestamp
        assert trade.exit_price == candles[4].open == 15


def test_entry_on_last_open_is_liquidated_at_last_close() -> None:
    candles = make_candles([10, 9, 8, 6], [10, 9, 8, 7])
    trade = run_backtest(candles, BacktestConfig(rsi_period=2)).trades[0]
    assert trade.entry_time == trade.exit_time == candles[-1].timestamp
    assert trade.entry_price == 7
    assert trade.exit_price == 6


@pytest.mark.parametrize("fee", [0, 0.001, 0.1])
def test_buy_and_hold_first_open_last_close_includes_both_fees(fee: float) -> None:
    candles = make_candles([11, 12, 15], [10, 11, 12])
    initial = 10000
    quantity = initial / (10 + 10 * fee)
    proceeds = quantity * 15 - quantity * 15 * fee
    result = run_backtest(candles, BacktestConfig(trading_fee=fee))
    assert result.buy_and_hold_return_percent == pytest.approx((proceeds - initial) / initial * 100)


def test_every_equity_sample_uses_cash_plus_position_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from strategy_backtest_agent import metrics

    observed: list[float] = []
    original = metrics.max_drawdown

    def capture(equity: Sequence[float]) -> float:
        observed.extend(equity)
        return original(equity)

    monkeypatch.setattr(metrics, "max_drawdown", capture)
    config = BacktestConfig(rsi_period=2, trading_fee=0.01, initial_balance=1000)
    result = run_backtest(make_candles([10, 9, 8, 7, 3.5, 7]), config)
    quantity = 1000 / (7 * 1.01)
    assert observed == pytest.approx(
        [
            1000,
            1000,
            1000,
            1000,
            1000,
            1000,
            1000,
            quantity * 7,
            quantity * 7,
            quantity * 3.5,
            quantity * 3.5,
            quantity * 7,
            quantity * 7 * 0.99,
        ]
    )
    assert min(observed) >= 0
    assert result.max_drawdown_percent == pytest.approx((0.5 / 1.01 - 1) * 100)


def test_breakeven_trade_is_in_total_but_neither_winner_nor_loser() -> None:
    result = run_backtest(
        make_candles([10, 9, 8, 7, 7]), BacktestConfig(rsi_period=2, trading_fee=0)
    )
    assert result.trades[0].pnl == 0
    assert result.total_trades == 1
    assert result.winning_trades == result.losing_trades == 0
    assert result.win_rate == 0
