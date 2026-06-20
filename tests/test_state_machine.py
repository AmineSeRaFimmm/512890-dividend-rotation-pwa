import pandas as pd

from strategy.data_loader import load_sample_data
from strategy.state_machine import evaluate_strategy
from strategy.models import StrategyState


def test_evaluate_strategy_returns_valid_result():
    df = load_sample_data()
    result = evaluate_strategy(df, current_position=0.0, capital=100000)
    assert result.total_score >= 0
    assert result.target_state in list(StrategyState)
    assert len(result.cards) == 4


def test_no_buy_when_r_above_absorb_threshold():
    df = load_sample_data().tail(25).copy().reset_index(drop=True)
    # Force latest row into extreme tech absorption and weak dividend close.
    df.loc[df.index[-1], 'close_588000'] = 2.10
    df.loc[df.index[-1], 'close_512890'] = 1.10
    df.loc[df.index[-1], 'high_512890'] = 1.13
    df.loc[df.index[-1], 'low_512890'] = 1.09
    df.loc[df.index[-1], 'open_512890'] = 1.12
    result = evaluate_strategy(df, current_position=0.0, capital=100000)
    assert result.target_state == StrategyState.S0
