from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy.auto_portfolio import PortfolioState, apply_pending_order_if_due, create_pending_order
from strategy.data_loader import load_csv, load_sample_data
from strategy.indicators import add_indicators, validate_price_frame
from strategy.market_fetcher import FetchConfig, fetch_daily_market_data
from strategy.signal_io import read_json, signal_to_dict, write_json, write_signal_json
from strategy.state_machine import evaluate_strategy

DATA_DIR = PROJECT_ROOT / "data"
LIVE_DATA = DATA_DIR / "live_prices.csv"
LATEST_SIGNAL = DATA_DIR / "latest_signal.json"
PORTFOLIO_STATE = DATA_DIR / "auto_portfolio.json"
SIGNAL_HISTORY = DATA_DIR / "signal_history.csv"
UPDATE_LOG = DATA_DIR / "update_log.json"
DAILY_INCREMENTAL_LOOKBACK_DAYS = 15
HISTORY_BOOTSTRAP_LOOKBACK_DAYS = 820


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update 512890 daily data and signal snapshot after market close.")
    parser.add_argument("--offline-sample", action="store_true", help="Use bundled sample data only for local tests, never for production Actions.")
    parser.add_argument("--bootstrap-history", action="store_true", help="Rebuild the stored real market history with a long lookback window.")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD, mostly for reproducible tests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    lookback_days = _resolve_lookback_days(args)
    update_mode = _resolve_update_mode(args)

    if args.offline_sample:
        incoming = load_sample_data()
        source = "offline_sample"
        amount_basis = "sample"
    else:
        incoming = fetch_daily_market_data(end_date=end_date, config=FetchConfig(lookback_days=lookback_days))
        source = incoming.attrs.get("source") or "real_market_multi_source"
        amount_basis = incoming.attrs.get("amount_basis") or "reported_or_estimated_amount"

    merged = _merge_existing(LIVE_DATA, incoming, source=source, replace_existing=args.bootstrap_history)
    merged.to_csv(LIVE_DATA, index=False, encoding="utf-8-sig")

    enriched = add_indicators(merged)
    latest = enriched.iloc[-1]
    signal_date = str(pd.to_datetime(latest["date"]).date())

    portfolio = PortfolioState.from_dict(read_json(PORTFOLIO_STATE, default=None), capital=args.capital)
    executed_trade = apply_pending_order_if_due(portfolio, signal_date, float(latest["open_512890"]))
    current_position = portfolio.current_position_ratio(float(latest["close_512890"]))
    state_days_held = portfolio.update_state_days_held(float(latest["close_512890"]))

    result = evaluate_strategy(
        enriched,
        current_position=current_position,
        average_cost=portfolio.average_cost,
        capital=portfolio.capital,
        cooldown_days_left=0,
        state_days_held=state_days_held,
    )
    pending = create_pending_order(result, signal_close=float(latest["close_512890"]))
    portfolio.pending_order = pending
    portfolio.last_update = datetime.now().isoformat(timespec="seconds")

    extra = {
        "source": source,
        "amount_basis": amount_basis,
        "update_mode": update_mode,
        "updated_at": portfolio.last_update,
        "signal_date": signal_date,
        "next_execution": pending,
        "executed_trade_from_previous_signal": executed_trade,
        "portfolio": portfolio.to_dict(latest_close=float(latest["close_512890"])),
        "note": "GitHub Actions每天18:00后生成收盘信号；如有买卖信号，由用户在下一交易日开盘手动执行。自动组合仅用于PWA展示和回测跟踪。",
    }
    write_signal_json(result, LATEST_SIGNAL, extra=extra)
    write_json(PORTFOLIO_STATE, portfolio.to_dict(latest_close=float(latest["close_512890"])))
    _append_signal_history(result, extra)
    write_json(
        UPDATE_LOG,
        {
            "last_update": portfolio.last_update,
            "source": source,
            "amount_basis": amount_basis,
            "update_mode": update_mode,
            "rows": int(len(merged)),
            "latest_date": signal_date,
            "lookback_days": int(lookback_days),
            "data_policy": "bootstrap-history rebuilds the real historical archive once; daily Actions use short-window real-data incremental updates only. Offline sample is local-test only.",
        },
    )

    print(
        f"Updated {LIVE_DATA} rows={len(merged)} latest={signal_date} "
        f"source={source} amount_basis={amount_basis} mode={update_mode} lookback_days={lookback_days}"
    )
    print(f"Signal: {result.target_state.value} action={result.action} amount={result.action_amount:.2f}")


def _resolve_lookback_days(args: argparse.Namespace) -> int:
    if args.lookback_days is not None:
        return int(args.lookback_days)
    if args.bootstrap_history:
        return HISTORY_BOOTSTRAP_LOOKBACK_DAYS
    return DAILY_INCREMENTAL_LOOKBACK_DAYS


def _resolve_update_mode(args: argparse.Namespace) -> str:
    if args.offline_sample:
        return "offline_sample"
    if args.bootstrap_history:
        return "bootstrap_history"
    return "daily_incremental"


def _merge_existing(path: Path, incoming: pd.DataFrame, source: str, replace_existing: bool = False) -> pd.DataFrame:
    incoming = validate_price_frame(incoming)
    if path.exists():
        existing = load_csv(path)
        if source != "offline_sample":
            existing_dates = set(pd.to_datetime(existing["date"]).dt.date)
            incoming_dates = set(pd.to_datetime(incoming["date"]).dt.date)
            if replace_existing or _existing_archive_is_offline_sample() or (existing_dates and existing_dates.issubset(incoming_dates)):
                merged = incoming
            else:
                merged = pd.concat([existing, incoming], ignore_index=True)
        else:
            merged = pd.concat([existing, incoming], ignore_index=True)
    else:
        merged = incoming
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    return merged


def _existing_archive_is_offline_sample() -> bool:
    if not UPDATE_LOG.exists():
        return False
    try:
        info = read_json(UPDATE_LOG, default={})
    except Exception:
        return False
    return info.get("source") == "offline_sample" or info.get("update_mode") == "offline_sample"


def _append_signal_history(result, extra: dict) -> None:
    payload = signal_to_dict(result)
    row = {
        "date": payload["date"],
        "total_score": payload["total_score"],
        "current_state": payload["current_state"],
        "target_state": payload["target_state"],
        "current_position": payload["current_position"],
        "target_position": payload["target_position"],
        "action": payload["action"],
        "action_amount": payload["action_amount"],
        "r_tech_dividend": payload["raw"].get("r_tech_dividend"),
        "clv_512890": payload["raw"].get("clv_512890"),
        "clv_588000": payload["raw"].get("clv_588000"),
        "updated_at": extra.get("updated_at"),
    }
    df_new = pd.DataFrame([row])
    if SIGNAL_HISTORY.exists():
        old = pd.read_csv(SIGNAL_HISTORY)
        out = pd.concat([old, df_new], ignore_index=True)
        out = out.drop_duplicates(subset=["date"], keep="last")
    else:
        out = df_new
    out.sort_values("date").to_csv(SIGNAL_HISTORY, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
