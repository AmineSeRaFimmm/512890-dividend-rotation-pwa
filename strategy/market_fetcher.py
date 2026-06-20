from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class FetchConfig:
    trade_symbol: str = "512890"
    tech_symbol: str = "588000"
    lookback_days: int = 820


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

    Production uses Eastmoney's public ETF daily K-line endpoint directly. AKShare is
    kept as a secondary fallback only. The returned schema matches the app's CSV
    loader, so the strategy engine remains data-source agnostic.
    """
    config = config or FetchConfig()
    end = end_date or date.today()
    start = end - timedelta(days=config.lookback_days)

    trade = _fetch_etf_daily(config.trade_symbol, start, end).add_suffix("_512890")
    tech = _fetch_etf_daily(config.tech_symbol, start, end).add_suffix("_588000")
    trade = trade.rename(columns={"date_512890": "date"})
    tech = tech.rename(columns={"date_588000": "date"})
    merged = pd.merge(trade, tech, on="date", how="inner")
    if merged.empty:
        raise RuntimeError("真实行情抓取后没有可合并日期：512890 与 588000 的日线数据为空或日期不匹配。")

    width = _fetch_market_width_by_date(merged["date"].dt.date.tolist())
    if not width.empty:
        merged = pd.merge(merged, width, on="date", how="left")
    else:
        merged["advancers"] = pd.NA
        merged["decliners"] = pd.NA
    return merged.sort_values("date").reset_index(drop=True)


def _fetch_etf_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    errors: list[str] = []
    for fetcher in (_fetch_etf_daily_eastmoney_direct, _fetch_etf_daily_akshare):
        try:
            df = fetcher(symbol, start, end)
            if df is not None and not df.empty:
                return df
            errors.append(f"{fetcher.__name__}: empty")
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{fetcher.__name__}: {exc}")
    raise RuntimeError(f"未获取到ETF {symbol} 的真实行情数据。" + " | ".join(errors))


def _fetch_etf_daily_eastmoney_direct(symbol: str, start: date, end: date) -> pd.DataFrame:
    payload = _request_eastmoney_kline_payload(symbol=symbol, start=start, end=end)
    klines = (((payload or {}).get("data") or {}).get("klines") or [])
    if not klines:
        raise RuntimeError(f"东方财富接口未返回ETF {symbol} 的K线。")

    rows = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 7:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
                "amount": parts[6],
            }
        )
    if not rows:
        raise RuntimeError(f"东方财富接口返回ETF {symbol} 的K线格式异常。")
    return _normalize_akshare_ohlcv(pd.DataFrame(rows))


def _request_eastmoney_kline_payload(symbol: str, start: date, end: date) -> dict:
    import requests

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"1.{symbol}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "lmt": "1000000",
    }
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
        "Host": "push2his.eastmoney.com",
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    }
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with requests.Session() as session:
                response = session.get(url, params=params, headers=headers, timeout=(8, 35))
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < 5:
                time.sleep(min(2 * attempt, 8))
    raise RuntimeError(f"东方财富ETF {symbol} K线接口连续重试失败: {last_error}")


def _fetch_etf_daily_akshare(symbol: str, start: date, end: date) -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime dependency
        raise RuntimeError("缺少akshare，无法使用备用行情接口。") from exc

    raw = ak.fund_etf_hist_em(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"AKShare未获取到ETF {symbol} 的行情数据。")
    return _normalize_akshare_ohlcv(raw)


def _normalize_akshare_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df = df.rename(columns={c: COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    required = ["date", "open", "high", "low", "close", "volume", "amount"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"行情缺少字段: {missing}")
    return df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)[required]


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
