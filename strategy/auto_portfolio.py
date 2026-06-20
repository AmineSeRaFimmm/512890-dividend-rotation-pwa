from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .execution import estimate_shares, t_plus_1_buy_execution, t_plus_1_sell_execution
from .state_machine import state_from_position


DEFAULT_CAPITAL = 100_000.0


@dataclass
class PortfolioState:
    capital: float = DEFAULT_CAPITAL
    cash: float = DEFAULT_CAPITAL
    shares_512890: int = 0
    average_cost: float | None = None
    pending_order: dict[str, Any] | None = None
    last_update: str | None = None
    signal_state: str | None = None
    state_days_held: int = 0
    trade_log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None, capital: float = DEFAULT_CAPITAL) -> "PortfolioState":
        if not payload:
            return cls(capital=capital, cash=capital)
        return cls(
            capital=float(payload.get("capital", capital)),
            cash=float(payload.get("cash", capital)),
            shares_512890=int(payload.get("shares_512890", 0)),
            average_cost=payload.get("average_cost"),
            pending_order=payload.get("pending_order"),
            last_update=payload.get("last_update"),
            signal_state=payload.get("signal_state"),
            state_days_held=int(payload.get("state_days_held", 0)),
            trade_log=list(payload.get("trade_log", [])),
        )

    def to_dict(self, latest_close: float | None = None) -> dict[str, Any]:
        position_value = 0.0 if latest_close is None else self.shares_512890 * latest_close
        return {
            "capital": self.capital,
            "cash": round(self.cash, 2),
            "shares_512890": self.shares_512890,
            "average_cost": self.average_cost,
            "position_value": round(position_value, 2),
            "current_position_ratio": 0.0 if latest_close is None else position_value / self.capital,
            "pending_order": self.pending_order,
            "last_update": self.last_update,
            "signal_state": self.signal_state,
            "state_days_held": self.state_days_held,
            "trade_log": self.trade_log[-200:],
        }

    def current_position_ratio(self, latest_close: float) -> float:
        return (self.shares_512890 * latest_close) / self.capital

    def update_state_days_held(self, latest_close: float) -> int:
        current_state = state_from_position(self.current_position_ratio(latest_close)).value
        if current_state == self.signal_state:
            self.state_days_held += 1
        else:
            self.signal_state = current_state
            self.state_days_held = 1
        return self.state_days_held


def apply_pending_order_if_due(state: PortfolioState, trade_date: str, open_price: float) -> dict[str, Any] | None:
    order = state.pending_order
    if not order:
        return None
    if str(order.get("signal_date")) >= str(trade_date):
        return None

    side = order.get("side")
    planned_amount = float(order.get("planned_amount", 0.0))
    signal_close = float(order.get("signal_close", open_price))

    if side == "BUY_512890":
        plan = t_plus_1_buy_execution(planned_amount, signal_close, open_price)
        amount = min(plan.executable_amount, state.cash)
        shares = estimate_shares(amount, open_price)
        cost = round(shares * open_price, 2)
        if shares > 0:
            previous_cost = 0.0 if state.average_cost is None else state.average_cost * state.shares_512890
            state.cash -= cost
            state.shares_512890 += shares
            state.average_cost = (previous_cost + cost) / state.shares_512890
        trade = {
            "signal_date": order.get("signal_date"),
            "trade_date": trade_date,
            "side": "BUY",
            "open_price": open_price,
            "planned_amount": planned_amount,
            "executed_amount": cost,
            "shares": shares,
            "execution_status": plan.status,
            "execution_reason": plan.reason,
        }
    elif side == "SELL_512890":
        plan = t_plus_1_sell_execution(planned_amount, open_price)
        shares = min(state.shares_512890, estimate_shares(plan.executable_amount, open_price))
        proceeds = round(shares * open_price, 2)
        if shares > 0:
            state.cash += proceeds
            state.shares_512890 -= shares
            if state.shares_512890 == 0:
                state.average_cost = None
        trade = {
            "signal_date": order.get("signal_date"),
            "trade_date": trade_date,
            "side": "SELL",
            "open_price": open_price,
            "planned_amount": planned_amount,
            "executed_amount": proceeds,
            "shares": shares,
            "execution_status": plan.status,
            "execution_reason": plan.reason,
        }
    else:
        trade = {
            "signal_date": order.get("signal_date"),
            "trade_date": trade_date,
            "side": "NONE",
            "open_price": open_price,
            "planned_amount": planned_amount,
            "executed_amount": 0.0,
            "shares": 0,
            "execution_status": "NO_ACTION",
            "execution_reason": "未知或空订单。",
        }

    state.trade_log.append(trade)
    state.pending_order = None
    return trade


def create_pending_order(signal_result, signal_close: float) -> dict[str, Any] | None:
    if signal_result.action not in {"BUY_512890", "SELL_512890"} or signal_result.action_amount <= 0:
        return None
    return {
        "signal_date": signal_result.date,
        "side": signal_result.action,
        "asset": "512890",
        "planned_amount": round(float(signal_result.action_amount), 2),
        "signal_close": float(signal_close),
        "estimated_shares_at_signal_close": signal_result.action_shares_estimate,
        "status": "PENDING_NEXT_OPEN",
        "execution_rule": "T日收盘后出信号，下一交易日开盘执行；买入高开>0.8%降额，高开>1.5%暂缓；卖出直接执行。",
    }
