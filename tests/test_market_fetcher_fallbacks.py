import pandas as pd

from strategy.market_fetcher import _normalize_ohlcv


def test_normalize_ohlcv_accepts_fallback_schema():
    raw = pd.DataFrame(
        [
            {
                "date": "2026-06-18",
                "open": "1.001",
                "close": "1.002",
                "high": "1.003",
                "low": "1.000",
                "volume": "100000",
                "amount": "100200",
            }
        ]
    )
    out = _normalize_ohlcv(raw)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume", "amount"]
    assert out.iloc[0]["close"] == 1.002
    assert out.iloc[0]["amount"] == 100200
