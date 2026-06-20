from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .execution import estimate_shares, t_plus_1_buy_execution, t_plus_1_sell_execution
from .indicators import add_indicators
from .models import STATE_POSITION
from .state_machine import evaluate_strategy, state_from_position


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100_000,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> BacktestResult:
    data = add_indicators(df)
    start_ts = pd.to_datetime(start_date) if start_date is not None else None
    end_ts = pd.to_datetime(end_date) if end_date is not None else None

    cash = initial_capital
    shares = 0
    avg_cost = None
    trades: List[dict] = []
    equity: List[dict] = []

    for i in range(20, len(data) - 1):
        signal_date = pd.to_datetime(data.iloc[i]["date"])
        trade_date = pd.to_datetime(data.iloc[i + 1]["date"])
        if start_ts is not None and signal_date < start_ts:
            continue
        if end_ts is not None and trade_date > end_ts:
            continue

        history = data.iloc[: i + 1].copy()
        close = float(data.iloc[i]["close_512890"])
        position_value = shares * close
        current_position = position_value / initial_capital
        result = evaluate_strategy(history, current_position=current_position, average_cost=avg_cost, capital=initial_capital)
        next_open = float(data.iloc[i + 1]["open_512890"])

        if result.action == "BUY_512890":
            plan = t_plus_1_buy_execution(result.action_amount, close, next_open)
            amount = min(plan.executable_amount, cash)
            buy_shares = estimate_shares(amount, next_open)
            cost = buy_shares * next_open
            if buy_shares > 0:
                previous_cost = 0 if avg_cost is None else avg_cost * shares
                shares += buy_shares
                cash -= cost
                avg_cost = (previous_cost + cost) / shares
                trades.append({"signal_date": result.date, "trade_date": str(trade_date.date()), "side": "BUY", "price": next_open, "shares": buy_shares, "amount": cost, "state": result.target_state.value})
        elif result.action == "SELL_512890":
            plan = t_plus_1_sell_execution(result.action_amount, next_open)
            sell_shares = min(shares, estimate_shares(plan.executable_amount, next_open))
            proceeds = sell_shares * next_open
            if sell_shares > 0:
                shares -= sell_shares
                cash += proceeds
                if shares == 0:
                    avg_cost = None
                trades.append({"signal_date": result.date, "trade_date": str(trade_date.date()), "side": "SELL", "price": next_open, "shares": sell_shares, "amount": proceeds, "state": result.target_state.value})

        mark_price = float(data.iloc[i + 1]["close_512890"])
        total_equity = cash + shares * mark_price
        equity.append({"date": str(trade_date.date()), "cash": cash, "shares": shares, "close": mark_price, "equity": total_equity, "return": total_equity / initial_capital - 1})

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity)
    metrics = _metrics(equity_df, trades_df, initial_capital)
    return BacktestResult(trades_df, equity_df, metrics)


def _metrics(equity: pd.DataFrame, trades: pd.DataFrame, initial_capital: float) -> dict:
    if equity.empty:
        return {"total_return": 0, "max_drawdown": 0, "trade_count": 0, "final_equity": initial_capital}
    returns = equity["equity"] / initial_capital - 1
    peak = equity["equity"].cummax()
    drawdown = equity["equity"] / peak - 1
    return {
        "total_return": float(returns.iloc[-1]),
        "max_drawdown": float(drawdown.min()),
        "trade_count": int(len(trades)),
        "final_equity": float(equity["equity"].iloc[-1]),
    }
