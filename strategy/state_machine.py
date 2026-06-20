from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pandas as pd

from .indicators import add_indicators
from .config import load_strategy_thresholds
from .models import SignalCard, SignalResult, STATE_ORDER, STATE_POSITION, StrategyState
from .scoring import score_relative_strength, score_support, score_tech, score_trend


def state_from_position(position_ratio: float) -> StrategyState:
    if position_ratio >= 0.95:
        return StrategyState.S4
    if position_ratio >= 0.65:
        return StrategyState.S3
    if position_ratio >= 0.35:
        return StrategyState.S2
    if position_ratio >= 0.10:
        return StrategyState.S1
    return StrategyState.S0


def base_state_from_score(total_score: int) -> StrategyState:
    if total_score <= 3:
        return StrategyState.S0
    if total_score <= 5:
        return StrategyState.S1
    if total_score <= 7:
        return StrategyState.S2
    if total_score <= 9:
        return StrategyState.S3
    return StrategyState.S4


def evaluate_strategy(
    df: pd.DataFrame,
    current_position: float = 0.0,
    average_cost: float | None = None,
    capital: float = 100_000,
    cooldown_days_left: int = 0,
) -> SignalResult:
    data = add_indicators(df)
    row = data.iloc[-1]
    current_state = state_from_position(current_position)

    r_score, r_status, r_detail = score_relative_strength(row["r_tech_dividend"])
    trend_score, trend_status, trend_detail = score_trend(
        row["close_512890"], row["ma5_512890"], row["ma10_512890"], row["ma20_512890"]
    )
    support_score, support_status, support_detail = score_support(row["clv_512890"], int(row["strong_clv_streak_512890"]))
    tech_score, tech_status, tech_detail = score_tech(
        row["clv_588000"], row["close_588000"], row["ma5_588000"], bool(row["r_ma3_falling"]), row.get("market_up_ratio", math.nan)
    )

    total_score = r_score + trend_score + support_score + tech_score
    cards = [
        SignalCard("相对强弱 R", round(float(row["r_tech_dividend"]), 3), r_score, r_status, r_detail),
        SignalCard("512890趋势", round(float(row["close_512890"]), 3), trend_score, trend_status, trend_detail),
        SignalCard("512890承接 CLV", round(float(row["clv_512890"]), 3), support_score, support_status, support_detail),
        SignalCard("科技拥挤/钝化", round(float(row["clv_588000"]), 3), tech_score, tech_status, tech_detail),
    ]

    hard_flags = _hard_flags(row, average_cost)
    warnings: List[str] = []
    reasons: List[str] = []

    candidate_state = base_state_from_score(total_score)
    target_state = _apply_transition_rules(current_state, candidate_state, row, total_score, hard_flags, cooldown_days_left, reasons, warnings)

    current_pos = STATE_POSITION[current_state]
    target_pos = STATE_POSITION[target_state]

    action, action_amount = _action_from_positions(current_pos, target_pos, capital)
    est_shares = None
    if action_amount > 0:
        est_shares = int((action_amount // (float(row["close_512890"]) * 100)) * 100)

    if cooldown_days_left > 0:
        warnings.append(f"冷却期剩余{cooldown_days_left}个交易日：禁止新增买入，只允许持有或卖出。")

    return SignalResult(
        date=str(pd.to_datetime(row["date"]).date()),
        current_state=current_state,
        target_state=target_state,
        current_position=current_pos,
        target_position=target_pos,
        total_score=int(total_score),
        action=action,
        action_amount=float(action_amount),
        action_shares_estimate=est_shares,
        cards=cards,
        reasons=reasons,
        warnings=warnings,
        hard_flags=hard_flags,
        raw={k: _safe(row.get(k)) for k in [
            "r_tech_dividend", "r_ma3", "r_ma3_falling",
            "close_512890", "ma5_512890", "ma10_512890", "ma20_512890", "clv_512890",
            "close_588000", "ma5_588000", "clv_588000", "market_up_ratio"
        ]},
    )


def _apply_transition_rules(
    current_state: StrategyState,
    candidate_state: StrategyState,
    row: pd.Series,
    total_score: int,
    hard_flags: Dict[str, bool],
    cooldown_days_left: int,
    reasons: List[str],
    warnings: List[str],
) -> StrategyState:
    current_idx = STATE_ORDER.index(current_state)

    # 全局风控优先：异常下跌至少降低一档。
    if hard_flags["abnormal_drop"]:
        warnings.append("触发异常下跌规则：512890单日跌幅<=-3%且CLV<0.30。")
        return STATE_ORDER[max(0, current_idx - 1)]

    # 按仓位逐级卖出，避免总分高时掩盖破位风险。
    sell_state = _sell_transition(current_state, row, hard_flags, reasons)
    if STATE_ORDER.index(sell_state) < current_idx:
        return sell_state

    # 冷却期不允许新增买入。
    if cooldown_days_left > 0 and STATE_ORDER.index(candidate_state) > current_idx:
        return current_state

    # 买入必须逐级，不允许一次跳多档。
    max_buy_idx = min(current_idx + 1, len(STATE_ORDER) - 1)
    allowed_buy_state = STATE_ORDER[min(STATE_ORDER.index(candidate_state), max_buy_idx)]

    if STATE_ORDER.index(allowed_buy_state) <= current_idx:
        return current_state if current_idx > STATE_ORDER.index(allowed_buy_state) else allowed_buy_state

    if _buy_gate(current_state, allowed_buy_state, row, total_score, reasons):
        return allowed_buy_state

    return current_state


def _buy_gate(current_state: StrategyState, next_state: StrategyState, row: pd.Series, total_score: int, reasons: List[str]) -> bool:
    thresholds = load_strategy_thresholds()
    r = row["r_tech_dividend"]
    close = row["close_512890"]
    ma5 = row["ma5_512890"]
    ma10 = row["ma10_512890"]
    ma20 = row["ma20_512890"]
    clv = row["clv_512890"]
    k_clv = row["clv_588000"]
    tech_close = row["close_588000"]
    tech_ma5 = row["ma5_588000"]
    amount = row["amount_512890"]
    amount_ma5 = row["amount_ma5_512890"]

    if next_state == StrategyState.S1:
        ok = total_score >= 4 and r < thresholds.r_warning and clv >= thresholds.clv_support and not bool(row["new_5d_low_512890"]) and amount >= amount_ma5 * 0.8
        reasons.append(f"S0→S1：需要R<{thresholds.r_warning:.2f}、CLV≥{thresholds.clv_support:.2f}、未创5日新低、成交额不低于5日均额80%。")
        return ok
    if next_state == StrategyState.S2:
        ok = total_score >= 6 and r < thresholds.r_confirm and close > ma5 and (int(row["strong_clv_streak_512890"]) >= 2 or clv >= thresholds.s1_confirm_clv) and (k_clv < 0.50 or tech_close < tech_ma5)
        reasons.append(f"S1→S2：需要R<{thresholds.r_confirm:.2f}、512890站上MA5、承接增强、科技钝化或跌破MA5。")
        return ok
    if next_state == StrategyState.S3:
        ok = total_score >= 8 and r < thresholds.r_confirm and bool(row["r_ma3_falling"]) and close > ma10 and int(row["strong_clv_streak_512890"]) >= thresholds.s2_strong_clv_streak and (tech_close < tech_ma5 or k_clv < 0.40)
        reasons.append(f"S2→S3：需要R<{thresholds.r_confirm:.2f}且3日均线下行、512890站上MA10、连续{thresholds.s2_strong_clv_streak}日强承接、科技转弱。")
        return ok
    if next_state == StrategyState.S4:
        market_ok = True if pd.isna(row.get("market_up_ratio")) else row.get("market_up_ratio") >= 0.45
        ok = total_score >= 10 and r < thresholds.r_strong and close > ma20 and row["ma5_512890"] > row["ma10_512890"] and tech_close < tech_ma5 and k_clv < 0.40 and market_ok
        reasons.append(f"S3→S4：需要R<{thresholds.r_strong:.2f}、512890站上MA20、MA5>MA10、科技弱、市场宽度修复。")
        return ok
    return False


def _sell_transition(current_state: StrategyState, row: pd.Series, hard_flags: Dict[str, bool], reasons: List[str]) -> StrategyState:
    thresholds = load_strategy_thresholds()
    idx = STATE_ORDER.index(current_state)
    if idx == 0:
        return current_state

    r = row["r_tech_dividend"]
    close = row["close_512890"]
    ma5 = row["ma5_512890"]
    ma10 = row["ma10_512890"]
    ma20 = row["ma20_512890"]
    clv = row["clv_512890"]
    k_clv = row["clv_588000"]
    tech_close = row["close_588000"]
    tech_ma5 = row["ma5_588000"]

    if current_state == StrategyState.S4:
        count = sum([close < ma5, clv < thresholds.clv_weak, r > thresholds.r_strong, tech_close > tech_ma5, row["pct_512890"] < 0 and row["amount_512890"] > row["amount_ma5_512890"]])
        if count >= thresholds.sell_s4_condition_count:
            reasons.append(f"S4→S3：满仓优势减弱，至少{thresholds.sell_s4_condition_count}个减仓条件成立。")
            return StrategyState.S3

    if current_state == StrategyState.S3:
        count = sum([close < ma10, int(row["weak_clv_streak_512890"]) >= 2, r > thresholds.r_confirm, tech_close > tech_ma5 and k_clv > thresholds.clv_strong, row["ret3_512890"] < 0])
        if count >= thresholds.sell_s3_condition_count:
            reasons.append(f"S3→S2：主仓趋势修复失败，至少{thresholds.sell_s3_condition_count}个减仓条件成立。")
            return StrategyState.S2

    if current_state == StrategyState.S2:
        count = sum([close < ma5, r > thresholds.r_warning, clv < thresholds.clv_weak, bool(row["new_5d_low_512890"]), tech_close > tech_ma5 and k_clv > thresholds.clv_strong])
        if count >= thresholds.sell_s2_condition_count:
            reasons.append(f"S2→S1：初步确认失败，至少{thresholds.sell_s2_condition_count}个减仓条件成立。")
            return StrategyState.S1

    if current_state == StrategyState.S1:
        if r > thresholds.r_absorb or bool(row["new_10d_low_512890"]) or (close < ma10 and clv < thresholds.clv_weak) or hard_flags.get("stop_loss", False):
            reasons.append("S1→S0：观察仓失败，触发清仓条件。")
            return StrategyState.S0

    return current_state


def _hard_flags(row: pd.Series, average_cost: float | None) -> Dict[str, bool]:
    close = row["close_512890"]
    pnl = 0.0 if average_cost in (None, 0) else (close / average_cost - 1)
    return {
        "strong_rotation": bool(row["r_tech_dividend"] < 1.59),
        "trend_confirmed": bool(row["ma5_512890"] > row["ma10_512890"] > row["ma20_512890"]),
        "support_failed": bool(row["weak_clv_streak_512890"] >= 2),
        "abnormal_drop": bool(row["pct_512890"] <= -0.03 and row["clv_512890"] < 0.30),
        "stop_loss": bool(pnl <= -0.03),
    }


def _action_from_positions(current_pos: float, target_pos: float, capital: float) -> Tuple[str, float]:
    delta = target_pos - current_pos
    amount = abs(delta) * capital
    if abs(delta) < 1e-9:
        return "HOLD", 0.0
    if delta > 0:
        return "BUY_512890", amount
    return "SELL_512890", amount


def _safe(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        return value.item()
    return value
