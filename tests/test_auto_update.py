from strategy.auto_portfolio import PortfolioState, apply_pending_order_if_due, create_pending_order
from strategy.data_loader import load_sample_data
from strategy.indicators import add_indicators
from strategy.signal_io import signal_to_dict
from strategy.state_machine import evaluate_strategy


def test_pending_buy_executes_on_following_trade_day():
    state = PortfolioState(capital=100000, cash=100000)
    state.pending_order = {
        "signal_date": "2026-06-18",
        "side": "BUY_512890",
        "planned_amount": 20000,
        "signal_close": 1.100,
    }
    trade = apply_pending_order_if_due(state, trade_date="2026-06-19", open_price=1.105)
    assert trade is not None
    assert trade["side"] == "BUY"
    assert trade["shares"] > 0
    assert state.pending_order is None
    assert state.shares_512890 == trade["shares"]


def test_pending_order_is_not_executed_same_signal_day():
    state = PortfolioState(capital=100000, cash=100000)
    state.pending_order = {
        "signal_date": "2026-06-19",
        "side": "BUY_512890",
        "planned_amount": 20000,
        "signal_close": 1.100,
    }
    trade = apply_pending_order_if_due(state, trade_date="2026-06-19", open_price=1.105)
    assert trade is None
    assert state.pending_order is not None
    assert state.shares_512890 == 0


def test_signal_serialization_is_json_safe():
    df = add_indicators(load_sample_data())
    result = evaluate_strategy(df, current_position=0.0, capital=100000)
    payload = signal_to_dict(result)
    assert payload["target_state"].startswith("S")
    assert payload["cards"]
    pending = create_pending_order(result, signal_close=float(df.iloc[-1]["close_512890"]))
    assert pending is None or pending["asset"] == "512890"
