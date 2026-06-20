from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATEGY_CONFIG = PROJECT_ROOT / "config" / "strategy.json"


@dataclass(frozen=True)
class StrategyThresholds:
    r_absorb: float = 1.75
    r_warning: float = 1.70
    r_confirm: float = 1.64
    r_strong: float = 1.59
    clv_weak: float = 0.30
    clv_support: float = 0.60
    clv_strong: float = 0.70
    s1_confirm_clv: float = 0.70
    s2_strong_clv_streak: int = 3
    sell_s2_condition_count: int = 2
    sell_s3_condition_count: int = 3
    sell_s4_condition_count: int = 2


def _coerce_thresholds(raw: dict[str, Any]) -> StrategyThresholds:
    defaults = StrategyThresholds()
    values = {field: getattr(defaults, field) for field in defaults.__dataclass_fields__}
    values.update({k: v for k, v in raw.items() if k in values})
    return StrategyThresholds(**values)


@lru_cache(maxsize=1)
def load_strategy_thresholds() -> StrategyThresholds:
    if not STRATEGY_CONFIG.exists():
        return StrategyThresholds()
    with STRATEGY_CONFIG.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return _coerce_thresholds(payload.get("thresholds", {}))
