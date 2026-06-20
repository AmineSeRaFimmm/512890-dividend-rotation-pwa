from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable

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

FetchFunc = Callable[[str, date, date], pd.DataFrame]


def fetch_daily_market_data(end_date: date | None = None, config: FetchConfig | None = None) -> pd.DataFrame:
    """Fetch recent daily bars for 512890 and 588000.

    Production tries several independent public daily-bar sources. Eastmoney remains
    preferred because it provides official amount directly; Tencent/Sina/Yahoo are
    defensive fallbacks for GitHub Actions network blocks.
    """
    config = config or FetchConfig()
    end = end_date or date.today()
    start = end - timedelta(days=config.lookback_days)

    trade_raw = _fetch_etf_daily(config.trade_symbol, start, end)
    tech_raw = _fetch_etf_daily(config.tech_symbol, start, end)
    trade = trade_raw.add_suffix("_512890")
    tech = tech_raw.add_suffix("_588000")
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

    merged = merged.sort_values("date").reset_index(drop=True)
    merged.attrs["source"] = f"512890:{trade_raw.attrs.get('source', 'unknown')};588000:{tech_raw.attrs.get('source', 'unknown')}"
    merged.attrs["amount_basis"] = f"512890:{trade_raw.attrs.get('amount_basis', 'unknown')};588000:{tech_raw.attrs.get('amount_basis', 'unknown')}"
    return merged


def _fetch_etf_daily(symbol: str, start: date, end: date) -> pd.DataFrame:
    errors: list[str] = []
    fetchers: tuple[tuple[str, FetchFunc], ...] = (
        ("eastmoney_direct", _fetch_etf_daily_eastmoney_direct),
        ("tencent_direct", _fetch_etf_daily_tencent_direct),
        ("sina_direct", _fetch_etf_daily_sina_direct),
        ("yahoo_chart", _fetch_etf_daily_yahoo_chart),
        ("akshare_eastmoney", _fetch_etf_daily_akshare),
    )
    for name, fetcher in fetchers:
        try:
            df = fetcher(symbol, start, end)
            if df is not None and not df.empty:
                df.attrs["source"] = name
                return df
            errors.append(f"{name}: empty")
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{name}: {exc}")
    raise RuntimeError(f"未获取到ETF {symbol} 的真实行情数据。" + " | ".join(errors))


def _fetch_etf_daily_eastmoney_direct(symbol: str, start: date, end: date) -> pd.DataFrame:
    payload = _request_json_with_retries(
        url="https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": f"1.{symbol}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "0",
            "beg": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "lmt": "1000000",
        },
        host="push2his.eastmoney.com",
        referer="https://quote.eastmoney.com/",
        label=f"东方财富ETF {symbol} K线接口",
    )
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
    out = _normalize_ohlcv(pd.DataFrame(rows))
    out.attrs["amount_basis"] = "reported_amount"
    return out


def _fetch_etf_daily_tencent_direct(symbol: str, start: date, end: date) -> pd.DataFrame:
    sec = f"sh{symbol}"
    payload = _request_json_with_retries(
        url="https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": f"{sec},day,{start:%Y-%m-%d},{end:%Y-%m-%d},1000"},
        host="web.ifzq.gtimg.cn",
        referer="https://gu.qq.com/",
        label=f"腾讯证券ETF {symbol} K线接口",
    )
    node = ((payload or {}).get("data") or {}).get(sec) or {}
    klines = node.get("day") or node.get("qfqday") or node.get("hfqday") or []
    if not klines:
        raise RuntimeError(f"腾讯证券接口未返回ETF {symbol} 的K线。")
    rows = []
    for row in klines:
        if len(row) < 6:
            continue
        close = row[2]
        volume = row[5]
        amount = row[6] if len(row) >= 7 else _estimate_amount(close, volume)
        rows.append({"date": row[0], "open": row[1], "close": close, "high": row[3], "low": row[4], "volume": volume, "amount": amount})
    if not rows:
        raise RuntimeError(f"腾讯证券接口返回ETF {symbol} 的K线格式异常。")
    out = _normalize_ohlcv(pd.DataFrame(rows))
    out.attrs["amount_basis"] = "reported_or_close_times_volume"
    return out


def _fetch_etf_daily_sina_direct(symbol: str, start: date, end: date) -> pd.DataFrame:
    text = _request_text_with_retries(
        url="https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": f"sh{symbol}", "scale": "240", "ma": "no", "datalen": "1000"},
        host="money.finance.sina.com.cn",
        referer="https://finance.sina.com.cn/",
        label=f"新浪财经ETF {symbol} K线接口",
    )
    rows_raw = json.loads(text)
    rows = []
    for row in rows_raw:
        row_date = pd.to_datetime(row.get("day") or row.get("date")).date()
        if row_date < start or row_date > end:
            continue
        close = row.get("close")
        volume = row.get("volume")
        rows.append(
            {
                "date": row_date,
                "open": row.get("open"),
                "close": close,
                "high": row.get("high"),
                "low": row.get("low"),
                "volume": volume,
                "amount": row.get("amount") or _estimate_amount(close, volume),
            }
        )
    if not rows:
        raise RuntimeError(f"新浪财经接口未返回ETF {symbol} 的有效K线。")
    out = _normalize_ohlcv(pd.DataFrame(rows))
    out.attrs["amount_basis"] = "reported_or_close_times_volume"
    return out


def _fetch_etf_daily_yahoo_chart(symbol: str, start: date, end: date) -> pd.DataFrame:
    period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    payload = _request_json_with_retries(
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.SS",
        params={"period1": period1, "period2": period2, "interval": "1d", "events": "history", "includeAdjustedClose": "false"},
        host="query1.finance.yahoo.com",
        referer="https://finance.yahoo.com/",
        label=f"Yahoo Finance ETF {symbol}.SS 日线接口",
    )
    result = (((payload or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo接口未返回ETF {symbol}.SS 的K线。")
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
    rows = []
    for idx, ts in enumerate(timestamps):
        try:
            row_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            close = quote.get("close", [])[idx]
            volume = quote.get("volume", [])[idx]
            rows.append(
                {
                    "date": row_date,
                    "open": quote.get("open", [])[idx],
                    "close": close,
                    "high": quote.get("high", [])[idx],
                    "low": quote.get("low", [])[idx],
                    "volume": volume,
                    "amount": _estimate_amount(close, volume),
                }
            )
        except Exception:
            continue
    if not rows:
        raise RuntimeError(f"Yahoo接口返回ETF {symbol}.SS 的K线格式异常。")
    out = _normalize_ohlcv(pd.DataFrame(rows))
    out.attrs["amount_basis"] = "close_times_volume"
    return out


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
    out = _normalize_ohlcv(raw)
    out.attrs["amount_basis"] = "reported_amount"
    return out


def _request_json_with_retries(url: str, params: dict, host: str, referer: str, label: str) -> dict:
    text = _request_text_with_retries(url=url, params=params, host=host, referer=referer, label=label)
    return json.loads(text)


def _request_text_with_retries(url: str, params: dict, host: str, referer: str, label: str) -> str:
    import requests

    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "close",
        "Host": host,
        "Pragma": "no-cache",
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    }
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            with requests.Session() as session:
                response = session.get(url, params=params, headers=headers, timeout=(8, 35))
                response.raise_for_status()
                return response.text
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < 5:
                time.sleep(min(2 * attempt, 8))
    raise RuntimeError(f"{label}连续重试失败: {last_error}")


def _estimate_amount(close, volume) -> float:
    close_num = pd.to_numeric(pd.Series([close]), errors="coerce").iloc[0]
    volume_num = pd.to_numeric(pd.Series([volume]), errors="coerce").iloc[0]
    if pd.isna(close_num) or pd.isna(volume_num):
        return float("nan")
    return float(close_num) * float(volume_num)


def _normalize_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
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
