import pandas as pd

from strategy.backtest import run_backtest
from strategy.data_loader import load_sample_data


def test_backtest_respects_start_date_filter():
    df = load_sample_data()
    all_result = run_backtest(df, initial_capital=100000)
    latest_date = pd.to_datetime(df["date"]).max()
    start_date = latest_date - pd.DateOffset(months=3)
    filtered_result = run_backtest(df, initial_capital=100000, start_date=start_date, end_date=latest_date)

    if not filtered_result.equity_curve.empty:
        first_equity_date = pd.to_datetime(filtered_result.equity_curve["date"]).min()
        assert first_equity_date >= start_date
    assert len(filtered_result.equity_curve) <= len(all_result.equity_curve)
