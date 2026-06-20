from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "open_512890", "high_512890", "low_512890", "close_512890", "volume_512890", "amount_512890",
    "open_588000", "high_588000", "low_588000", "close_588000", "volume_588000", "amount_588000",
}


def validate_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_COLUMNS.difference(df.columns))
    if missing:
        raise ValueError(f"缺少必要列: {', '.join(missing)}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    numeric_cols = [c for c in out.columns if c != "date"]
    out[numeric_cols] = out[numeric_cols].apply(pd.to_numeric, errors="coerce")
    return out


def clv(close: float, high: float, low: float) -> float:
    if pd.isna(close) or pd.isna(high) or pd.isna(low):
        return np.nan
    if high == low:
        return 0.5
    return float((close - low) / (high - low))


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = validate_price_frame(df)
    out["r_tech_dividend"] = out["close_588000"] / out["close_512890"]
    out["r_ma3"] = out["r_tech_dividend"].rolling(3, min_periods=1).mean()
    out["r_ma3_prev"] = out["r_ma3"].shift(1)
    out["r_ma3_falling"] = out["r_ma3"] < out["r_ma3_prev"]

    for symbol in ["512890", "588000"]:
        close_col = f"close_{symbol}"
        high_col = f"high_{symbol}"
        low_col = f"low_{symbol}"
        open_col = f"open_{symbol}"
        out[f"ma5_{symbol}"] = out[close_col].rolling(5, min_periods=1).mean()
        out[f"ma10_{symbol}"] = out[close_col].rolling(10, min_periods=1).mean()
        out[f"ma20_{symbol}"] = out[close_col].rolling(20, min_periods=1).mean()
        out[f"pct_{symbol}"] = out[close_col].pct_change().fillna(0.0)
        out[f"ret3_{symbol}"] = out[close_col].pct_change(3).fillna(0.0)
        out[f"clv_{symbol}"] = [clv(c, h, l) for c, h, l in zip(out[close_col], out[high_col], out[low_col])]
        out[f"amount_ma5_{symbol}"] = out[f"amount_{symbol}"].rolling(5, min_periods=1).mean()
        out[f"new_5d_low_{symbol}"] = out[close_col] <= out[close_col].rolling(5, min_periods=1).min()
        out[f"new_10d_low_{symbol}"] = out[close_col] <= out[close_col].rolling(10, min_periods=1).min()
        out[f"gap_open_{symbol}"] = (out[open_col] / out[close_col].shift(1)) - 1

    out["strong_clv_512890"] = out["clv_512890"] >= 0.60
    out["weak_clv_512890"] = out["clv_512890"] < 0.30
    out["strong_clv_streak_512890"] = _streak(out["strong_clv_512890"])
    out["weak_clv_streak_512890"] = _streak(out["weak_clv_512890"])

    if {"advancers", "decliners"}.issubset(out.columns):
        total = out["advancers"] + out["decliners"]
        out["market_up_ratio"] = np.where(total > 0, out["advancers"] / total, np.nan)
    else:
        out["market_up_ratio"] = np.nan
    return out


def _streak(condition: pd.Series) -> pd.Series:
    streaks = []
    current = 0
    for value in condition.fillna(False):
        if bool(value):
            current += 1
        else:
            current = 0
        streaks.append(current)
    return pd.Series(streaks, index=condition.index, dtype="int64")


def latest_with_indicators(df: pd.DataFrame) -> pd.Series:
    enriched = add_indicators(df)
    if enriched.empty:
        raise ValueError("数据为空，无法计算信号")
    return enriched.iloc[-1]
