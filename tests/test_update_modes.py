from argparse import Namespace

import pandas as pd

import scripts.update_daily_snapshot as update_daily_snapshot


REQUIRED_ROW = {
    "date": "2026-06-18",
    "open_512890": 1.0,
    "high_512890": 1.1,
    "low_512890": 0.9,
    "close_512890": 1.0,
    "volume_512890": 100,
    "amount_512890": 100,
    "open_588000": 1.5,
    "high_588000": 1.6,
    "low_588000": 1.4,
    "close_588000": 1.5,
    "volume_588000": 100,
    "amount_588000": 150,
}


def test_daily_mode_defaults_to_short_incremental_window():
    args = Namespace(lookback_days=None, bootstrap_history=False, offline_sample=False)
    assert update_daily_snapshot._resolve_lookback_days(args) == 15
    assert update_daily_snapshot._resolve_update_mode(args) == "daily_incremental"


def test_bootstrap_mode_defaults_to_full_history_window():
    args = Namespace(lookback_days=None, bootstrap_history=True, offline_sample=False)
    assert update_daily_snapshot._resolve_lookback_days(args) == 820
    assert update_daily_snapshot._resolve_update_mode(args) == "bootstrap_history"


def test_real_data_replaces_existing_offline_sample_archive(tmp_path, monkeypatch):
    live_path = tmp_path / "live_prices.csv"
    update_log = tmp_path / "update_log.json"
    update_log.write_text('{"source":"offline_sample"}', encoding="utf-8")
    monkeypatch.setattr(update_daily_snapshot, "UPDATE_LOG", update_log)

    existing = pd.DataFrame([{**REQUIRED_ROW, "date": "2026-06-17", "close_512890": 0.99}])
    incoming = pd.DataFrame([REQUIRED_ROW])
    existing.to_csv(live_path, index=False)

    merged = update_daily_snapshot._merge_existing(
        live_path,
        incoming,
        source="512890:tencent_direct;588000:tencent_direct",
        replace_existing=False,
    )
    assert len(merged) == 1
    assert str(pd.to_datetime(merged.iloc[0]["date"]).date()) == "2026-06-18"
