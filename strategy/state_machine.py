from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pandas as pd

from .indicators import add_indicators
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
    # 单资产512890择时：总分只决定候选仓位，最终仍由买入门槛逐级确认。
    # 阈值采用稳定分层，不做历史样本参数搜索。
    if total_score <= 2:
        return StrategyState.S0
    if total_score <= 4:
        return StrategyState.S1
    if total_score <= 6:
        return StrategyState.S2
    if total_score <= 8:
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
    close = row["close_512890"]
    ma5 = row["ma5_512890"]
    ma10 = row["ma10_512890"]
    ma20 = row["ma20_512890"]
    clv = row["clv_512890"]
    amount = row["amount_512890"]
    amount_ma5 = row["amount_ma5_512890"]
    strong_streak = int(row["strong_clv_streak_512890"])
    liquidity_ok = amount >= amount_ma5 * 0.60
    external_caution = _external_caution(row)
    external_extreme = _external_extreme(row)

    if next_state == StrategyState.S1:
        own_turning = (close > ma5 or clv >= 0.60) and clv >= 0.45
        ok = total_score >= 3 and own_turning and not bool(row["new_5d_low_512890"]) and liquidity_ok and not (external_extreme and close < ma5)
        reasons.append("S0→S1：以512890自身转强为主，需总分≥3、站上MA5或CLV≥0.60、CLV不低于0.45、未创5日新低、成交额不低于5日均额60%；极端科技吸血且512890未站上MA5时暂缓。")
        return ok
    if next_state == StrategyState.S2:
        ok = total_score >= 5 and close > ma5 and (strong_streak >= 1 or clv >= 0.55) and liquidity_ok and not (external_extreme and clv < 0.70)
        reasons.append("S1→S2：512890站上MA5且出现承接，成交额不低于5日均额60%；极端科技吸血时要求更强CLV。")
        return ok
    if next_state == StrategyState.S3:
        own_trend_confirmed = close > ma10 and (ma5 >= ma10 or close > ma20)
        own_support_confirmed = strong_streak >= 2 or clv >= 0.65
        ok = total_score >= 7 and own_trend_confirmed and own_support_confirmed and not external_extreme
        reasons.append("S2→S3：512890站上MA10，MA5不弱于MA10或站上MA20，并且承接连续或CLV≥0.65；极端科技吸血时不升主仓。")
        return ok
    if next_state == StrategyState.S4:
        market_ok = True if pd.isna(row.get("market_up_ratio")) else row.get("market_up_ratio") >= 0.45
        ok = total_score >= 9 and close > ma20 and ma5 > ma10 and (strong_streak >= 3 or clv >= 0.70) and market_ok and not external_caution
        reasons.append("S3→S4：512890站上MA20、MA5>MA10、强承接确认且市场宽度不差；科技明显吸血时不升满仓。")
        return ok
    return False


def _sell_transition(current_state: StrategyState, row: pd.Series, hard_flags: Dict[str, bool], reasons: List[str]) -> StrategyState:
    idx = STATE_ORDER.index(current_state)
    if idx == 0:
        return current_state

    close = row["close_512890"]
    ma5 = row["ma5_512890"]
    ma10 = row["ma10_512890"]
    ma20 = row["ma20_512890"]
    clv = row["clv_512890"]
    external_caution = _external_caution(row)
    external_extreme = _external_extreme(row)

    if current_state == StrategyState.S4:
        count = sum([close < ma5, clv < 0.30, int(row["weak_clv_streak_512890"]) >= 2, external_caution, row["pct_512890"] < 0 and row["amount_512890"] > row["amount_ma5_512890"]])
        if count >= 2:
            reasons.append("S4→S3：满仓优势减弱，至少两个减仓条件成立。")
            return StrategyState.S3

    if current_state == StrategyState.S3:
        count = sum([close < ma10, int(row["weak_clv_streak_512890"]) >= 2, row["ret3_512890"] < 0, close < ma20 and clv < 0.50, external_extreme])
        if count >= 3:
            reasons.append("S3→S2：主仓趋势修复失败，至少三个减仓条件成立。")
            return StrategyState.S2

    if current_state == StrategyState.S2:
        count = sum([close < ma5, clv < 0.30, bool(row["new_5d_low_512890"]), row["ret3_512890"] < 0 and close < ma10, external_extreme])
        if count >= 2:
            reasons.append("S2→S1：初步确认失败，至少两个减仓条件成立。")
            return StrategyState.S1

    if current_state == StrategyState.S1:
        if bool(row["new_10d_low_512890"]) or (close < ma10 and clv < 0.30) or hard_flags.get("stop_loss", False) or (external_extreme and close < ma5):
            reasons.append("S1→S0：观察仓失败，触发清仓条件。")
            return StrategyState.S0

    return current_state


def _external_caution(row: pd.Series) -> bool:
    return bool(row["r_tech_dividend"] > 1.75 and row["close_588000"] > row["ma5_588000"] and row["clv_588000"] > 0.70)


def _external_extreme(row: pd.Series) -> bool:
    return bool(row["r_tech_dividend"] > 1.90 and row["close_588000"] > row["ma5_588000"] and row["clv_588000"] > 0.70)


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
