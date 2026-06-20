from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPlan:
    side: str
    planned_amount: float
    executable_amount: float
    estimated_shares: int
    status: str
    reason: str


def estimate_shares(amount: float, price: float, lot_size: int = 100) -> int:
    if amount <= 0 or price <= 0:
        return 0
    return int(math.floor(amount / price / lot_size) * lot_size)


def t_plus_1_buy_execution(planned_amount: float, signal_close: float, next_open: float) -> ExecutionPlan:
    if planned_amount <= 0:
        return ExecutionPlan("BUY", planned_amount, 0.0, 0, "NO_ACTION", "无买入计划。")
    gap = next_open / signal_close - 1
    if gap <= 0.008:
        executable = planned_amount
        status = "NORMAL_EXECUTE"
        reason = "开盘价未高于信号日收盘价0.8%，正常执行。"
    elif gap <= 0.015:
        executable = planned_amount * 0.5
        status = "HALF_EXECUTE"
        reason = "高开超过0.8%但未超过1.5%，只执行计划金额50%。"
    else:
        executable = 0.0
        status = "DEFERRED"
        reason = "高开超过1.5%，暂缓买入，等待收盘后重新计算。"
    return ExecutionPlan("BUY", planned_amount, executable, estimate_shares(executable, next_open), status, reason)


def t_plus_1_sell_execution(planned_amount: float, next_open: float) -> ExecutionPlan:
    if planned_amount <= 0:
        return ExecutionPlan("SELL", planned_amount, 0.0, 0, "NO_ACTION", "无卖出计划。")
    return ExecutionPlan("SELL", planned_amount, planned_amount, estimate_shares(planned_amount, next_open), "NORMAL_EXECUTE", "卖出信号不设低开保护，T+1开盘执行。")
