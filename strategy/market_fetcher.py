from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class FetchConfig:
    trade_symbol: str = "512890"
    tech_symbol: str = "588000"
    lookback_days: int = 120


COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "date": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}


def fetch_daily_market_data(end_date: date | None = None, config: FetchConfig | None = None) -> pd.DataFrame:
    """Fetch recent daily bars for 512890 and 588000.

    The production fetcher uses AKShare's Eastmoney ETF history endpoint. The function
    intentionally returns the same normalized schema as the app's CSV loader so the
    strategy engine remains data-source agnostic.
    """
    config = config or FetchConfig()
    end = end_date or date.today()
    start = end - timedelta(days=config.lookback_days)

    trade = _fetch_etf_daily(config.trade_symbol, start, end).add_suffix("_512890")
    tech = _fetch_etf_daily(config.tech_symbol, start, end).add_suffix("_588000")
    trade = trade.rename(columns={"date_512890": "date"})
    tech = tech.rename(columns={"date_588000": "date"})
    merged = pd.merge(trade, tech, on="date", how="inner")
    width = _fetch_market_width_by_date(merged["date"].dt.date.tolist())
    if not width.empty:
        merged = pd.merge(merged, width, on="date", how="left")
    else:
        merged["advancers"] = pd.NA
        merged["decliners"] = pd.NA
    return merged.sort_values("date").reset_index(drop=True)


def _fetch_etf_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime dependency
        raise RuntimeError("缺少akshare，无法自动拉取A股ETF行情。请运行 pip install -r requirements.txt。") from exc

    raw = ak.fund_etf_hist_em(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"未获取到ETF {symbol} 的行情数据。")
    normalized = _normalize_akshare_ohlcv(raw)
    required = ["date", "open", "high", "low", "close", "volume", "amount"]
    missing = [c for c in required if c not in normalized.columns]
    if missing:
        raise RuntimeError(f"ETF {symbol} 行情缺少字段: {missing}")
    return normalized[required]


def _normalize_akshare_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df = df.rename(columns={c: COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)


def _fetch_market_width_by_date(dates: Iterable[date]) -> pd.DataFrame:
    """Best-effort market breadth fetch.

    The strategy can run without breadth. This function therefore fails soft and returns
    an empty frame if a live market-width endpoint changes or is temporarily unavailable.
    """
    try:
        import akshare as ak  # type: ignore

        spot = ak.stock_zh_a_spot_em()
        if spot is None or spot.empty or "涨跌幅" not in spot.columns:
            return pd.DataFrame()
        pct = pd.to_numeric(spot["涨跌幅"], errors="coerce")
        advancers = int((pct > 0).sum())
        decliners = int((pct < 0).sum())
        if advancers + decliners <= 0:
            return pd.DataFrame()
        latest_date = max(dates)
        return pd.DataFrame([{"date": pd.to_datetime(latest_date), "advancers": advancers, "decliners": decliners}])
    except Exception:
        return pd.DataFrame()
