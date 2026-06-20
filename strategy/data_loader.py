from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .indicators import validate_price_frame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA = PROJECT_ROOT / "data" / "sample_prices.csv"
LIVE_DATA = PROJECT_ROOT / "data" / "live_prices.csv"
LATEST_SIGNAL = PROJECT_ROOT / "data" / "latest_signal.json"
AUTO_PORTFOLIO = PROJECT_ROOT / "data" / "auto_portfolio.json"


def load_sample_data() -> pd.DataFrame:
    return load_csv(SAMPLE_DATA)


def live_data_exists() -> bool:
    return LIVE_DATA.exists()


def load_live_data() -> pd.DataFrame:
    return load_csv(LIVE_DATA)


def load_csv(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer)
    return validate_price_frame(df)


def normalize_uploaded_csv(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {c: c.strip().lower() for c in df.columns}
    df = df.rename(columns=rename_map)
    return validate_price_frame(df)
