from __future__ import annotations

import math
from typing import Tuple

import pandas as pd


def _fmt(value: float, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{digits}f}"


def score_relative_strength(r: float) -> Tuple[int, str, str]:
    if r >= 1.75:
        return 0, "科技吸血", f"R={_fmt(r)}，高于1.75，科技相对红利仍强。"
    if r >= 1.70:
        return 1, "吸血减弱", f"R={_fmt(r)}，科技强势开始松动，但尚未进入买入区。"
    if r >= 1.64:
        return 2, "风格预警", f"R={_fmt(r)}，跌入第一转折区，可观察512890承接。"
    return 3, "红利确认", f"R={_fmt(r)}，跌破1.64，科技相对红利优势明显收缩。"


def score_trend(close: float, ma5: float, ma10: float, ma20: float) -> Tuple[int, str, str]:
    if close < ma5:
        return 0, "红利弱势", f"512890收盘{_fmt(close)}低于MA5={_fmt(ma5)}。"
    if close > ma5 and close < ma10:
        return 1, "红利止跌", f"512890站上MA5，但未站上MA10。"
    if close > ma10 and close < ma20:
        return 2, "红利修复", f"512890站上MA10，但未站上MA20。"
    if close > ma20 and ma5 > ma10:
        return 3, "红利转强", f"512890站上MA20，且MA5>MA10。"
    return 1, "趋势中性", "512890价格结构未形成明确多头排列。"


def score_support(clv: float, strong_streak: int) -> Tuple[int, str, str]:
    if clv < 0.30:
        return 0, "尾盘弱势", f"CLV={_fmt(clv)}，收盘接近日内低位。"
    if clv < 0.60:
        return 1, "中性震荡", f"CLV={_fmt(clv)}，承接不强。"
    if strong_streak < 3:
        return 2, "有承接", f"CLV={_fmt(clv)}，出现强承接，但连续性不足。"
    return 3, "强承接", f"CLV={_fmt(clv)}，且连续{strong_streak}日强承接。"


def score_tech(k_clv: float, tech_close: float, tech_ma5: float, r_falling: bool, market_up_ratio: float) -> Tuple[int, str, str]:
    if tech_close > tech_ma5 and k_clv > 0.70:
        if not pd.isna(market_up_ratio) and market_up_ratio < 0.45:
            return 1, "科技吸血", "588000收盘强，但市场宽度差，科技对其他板块形成虹吸。"
        return 0, "科技仍强", "588000站上MA5且K_CLV>0.70，科技未钝化。"
    if tech_close > tech_ma5 and k_clv <= 0.70:
        return 1, "科技放缓", "588000仍在MA5上方，但日内强度下降。"
    if k_clv < 0.40:
        return 2, "科技钝化", "588000 K_CLV<0.40，出现高位钝化迹象。"
    if tech_close < tech_ma5 and r_falling:
        return 3, "科技转弱", "588000跌破MA5且R均线下行，有利于红利切换。"
    return 1, "科技中性", "科技未确认转弱。"
