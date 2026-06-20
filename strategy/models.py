from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyState(str, Enum):
    S0 = "S0 空仓等待"
    S1 = "S1 观察仓"
    S2 = "S2 初步确认"
    S3 = "S3 主仓持有"
    S4 = "S4 满仓持有"


STATE_ORDER = [StrategyState.S0, StrategyState.S1, StrategyState.S2, StrategyState.S3, StrategyState.S4]
STATE_POSITION = {
    StrategyState.S0: 0.0,
    StrategyState.S1: 0.20,
    StrategyState.S2: 0.40,
    StrategyState.S3: 0.70,
    StrategyState.S4: 1.00,
}
STATE_CAPTION = {
    StrategyState.S0: "空仓等待",
    StrategyState.S1: "观察买入",
    StrategyState.S2: "初步确认",
    StrategyState.S3: "主仓持有",
    StrategyState.S4: "满仓持有",
}


@dataclass(frozen=True)
class SignalCard:
    name: str
    value: Any
    score: int
    status: str
    detail: str


@dataclass(frozen=True)
class SignalResult:
    date: str
    current_state: StrategyState
    target_state: StrategyState
    current_position: float
    target_position: float
    total_score: int
    action: str
    action_amount: float
    action_shares_estimate: Optional[int]
    cards: List[SignalCard]
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    hard_flags: Dict[str, bool] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def target_position_pct(self) -> int:
        return int(round(self.target_position * 100))

    @property
    def current_position_pct(self) -> int:
        return int(round(self.current_position * 100))

