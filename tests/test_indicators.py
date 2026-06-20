import pandas as pd

from strategy.indicators import add_indicators, clv


def test_clv_mid_when_high_equals_low():
    assert clv(1.0, 1.0, 1.0) == 0.5


def test_add_indicators_required_columns():
    df = pd.read_csv('data/sample_prices.csv')
    enriched = add_indicators(df)
    assert 'r_tech_dividend' in enriched.columns
    assert 'clv_512890' in enriched.columns
    assert enriched['r_tech_dividend'].notna().all()
