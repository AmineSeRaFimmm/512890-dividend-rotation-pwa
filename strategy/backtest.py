from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .execution import estimate_shares, t_plus_1_buy_execution, t_plus_1_sell_execution
from .config import load_strategy_thresholds
from .indicators import add_indicators
from .models import StrategyState
from .state_machine import evaluate_strategy, state_from_position


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict
    benchmark_curve: pd.DataFrame
    diagnostics: dict
    state_history: pd.DataFrame
    s0_gate_failures: pd.DataFrame


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
    state_rows: List[dict] = []
    s0_failure_rows: List[dict] = []
    previous_state: StrategyState | None = None
    state_days_held = 0

    for i in range(20, len(data) - 1):
        signal_date = pd.to_datetime(data.iloc[i]["date"])
        trade_date = pd.to_datetime(data.iloc[i + 1]["date"])
        if start_ts is not None and signal_date < start_ts:
            continue
        if end_ts is not None and trade_date > end_ts:
            continue

        history = data.iloc[: i + 1].copy()
        row = data.iloc[i]
        close = float(row["close_512890"])
        position_value = shares * close
        total_equity_at_signal = cash + position_value
        current_position = position_value / total_equity_at_signal if total_equity_at_signal > 0 else 0.0
        current_state = state_from_position(current_position)
        if current_state == previous_state:
            state_days_held += 1
        else:
            previous_state = current_state
            state_days_held = 1
        result = evaluate_strategy(
            history,
            current_position=current_position,
            average_cost=avg_cost,
            capital=total_equity_at_signal,
            state_days_held=state_days_held,
        )
        next_open = float(data.iloc[i + 1]["open_512890"])

        state_rows.append(
            {
                "date": result.date,
                "current_state": result.current_state.value,
                "target_state": result.target_state.value,
                "current_position_actual": current_position,
                "target_position": result.target_position,
                "total_score": result.total_score,
                "action": result.action,
                "state_days_held": state_days_held,
            }
        )
        if result.current_state == StrategyState.S0:
            s0_failure_rows.append(_s0_gate_diagnostic_row(result.date, row, result.total_score))

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
        mark_position_value = shares * mark_price
        total_equity = cash + mark_position_value
        position_ratio = mark_position_value / total_equity if total_equity > 0 else 0.0
        equity.append(
            {
                "date": str(trade_date.date()),
                "cash": cash,
                "shares": shares,
                "close": mark_price,
                "position_value": mark_position_value,
                "position_ratio": position_ratio,
                "equity": total_equity,
                "return": total_equity / initial_capital - 1,
            }
        )

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity)
    state_history_df = pd.DataFrame(state_rows)
    s0_gate_failures_df = pd.DataFrame(s0_failure_rows)
    benchmark_curve = _buy_and_hold_512890(data, initial_capital, start_ts, end_ts)
    metrics = _metrics(equity_df, trades_df, benchmark_curve, initial_capital)
    diagnostics = _diagnostics(equity_df, state_history_df, s0_gate_failures_df)
    return BacktestResult(trades_df, equity_df, metrics, benchmark_curve, diagnostics, state_history_df, s0_gate_failures_df)


def _buy_and_hold_512890(data: pd.DataFrame, initial_capital: float, start_ts: pd.Timestamp | None, end_ts: pd.Timestamp | None) -> pd.DataFrame:
    mask = pd.Series(True, index=data.index)
    if start_ts is not None:
        mask &= pd.to_datetime(data["date"]) >= start_ts
    if end_ts is not None:
        mask &= pd.to_datetime(data["date"]) <= end_ts
    period = data.loc[mask].copy().reset_index(drop=True)
    if period.empty:
        return pd.DataFrame(columns=["date", "equity", "return"])

    entry_price = float(period.iloc[0]["open_512890"])
    shares = estimate_shares(initial_capital, entry_price)
    cash = initial_capital - shares * entry_price
    rows = []
    for _, row in period.iterrows():
        close = float(row["close_512890"])
        equity = cash + shares * close
        rows.append({"date": str(pd.to_datetime(row["date"]).date()), "equity": equity, "return": equity / initial_capital - 1})
    return pd.DataFrame(rows)


def _s0_gate_diagnostic_row(signal_date: str, row: pd.Series, total_score: int) -> dict:
    thresholds = load_strategy_thresholds()
    checks = {
        "总分>=4": total_score >= 4,
        f"R<{thresholds.r_warning:.2f}": float(row["r_tech_dividend"]) < thresholds.r_warning,
        f"CLV>={thresholds.clv_support:.2f}": float(row["clv_512890"]) >= thresholds.clv_support,
        "未创5日新低": not bool(row["new_5d_low_512890"]),
        "成交额>=5日均额80%": float(row["amount_512890"]) >= float(row["amount_ma5_512890"]) * 0.8,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "date": signal_date,
        "total_score": int(total_score),
        "r_tech_dividend": float(row["r_tech_dividend"]),
        "clv_512890": float(row["clv_512890"]),
        "new_5d_low_512890": bool(row["new_5d_low_512890"]),
        "amount_ratio_to_ma5": float(row["amount_512890"] / row["amount_ma5_512890"]) if float(row["amount_ma5_512890"]) else float("nan"),
        "passed_all": len(failed) == 0,
        "failed_count": len(failed),
        "failed_conditions": "、".join(failed),
    }


def _metrics(equity: pd.DataFrame, trades: pd.DataFrame, benchmark_curve: pd.DataFrame, initial_capital: float) -> dict:
    if equity.empty:
        strategy_return = 0.0
        strategy_drawdown = 0.0
        final_equity = initial_capital
    else:
        strategy_return = float(equity["equity"].iloc[-1] / initial_capital - 1)
        peak = equity["equity"].cummax()
        strategy_drawdown = float((equity["equity"] / peak - 1).min())
        final_equity = float(equity["equity"].iloc[-1])

    if benchmark_curve.empty:
        benchmark_return = 0.0
        benchmark_drawdown = 0.0
        benchmark_final_equity = initial_capital
    else:
        benchmark_return = float(benchmark_curve["equity"].iloc[-1] / initial_capital - 1)
        benchmark_peak = benchmark_curve["equity"].cummax()
        benchmark_drawdown = float((benchmark_curve["equity"] / benchmark_peak - 1).min())
        benchmark_final_equity = float(benchmark_curve["equity"].iloc[-1])

    return {
        "total_return": strategy_return,
        "max_drawdown": strategy_drawdown,
        "trade_count": int(len(trades)),
        "final_equity": final_equity,
        "benchmark_total_return": benchmark_return,
        "benchmark_max_drawdown": benchmark_drawdown,
        "benchmark_final_equity": benchmark_final_equity,
        "excess_return": strategy_return - benchmark_return,
    }


def _diagnostics(equity: pd.DataFrame, state_history: pd.DataFrame, s0_gate_failures: pd.DataFrame) -> dict:
    if equity.empty:
        avg_position = 0.0
        exposure_ratio = 0.0
    else:
        avg_position = float(equity["position_ratio"].mean())
        exposure_ratio = float((equity["position_ratio"] > 0.01).mean())

    if state_history.empty:
        state_counts = {}
        state_ratios = {}
        s0_ratio = 0.0
    else:
        counts = state_history["current_state"].value_counts().to_dict()
        total = len(state_history)
        state_counts = {str(k): int(v) for k, v in counts.items()}
        state_ratios = {str(k): float(v / total) for k, v in counts.items()}
        s0_ratio = float((state_history["current_state"] == StrategyState.S0.value).mean())

    if s0_gate_failures.empty:
        s0_failure_days = 0
    else:
        s0_failure_days = int((~s0_gate_failures["passed_all"]).sum())

    return {
        "average_position": avg_position,
        "exposure_ratio": exposure_ratio,
        "s0_ratio": s0_ratio,
        "s0_failure_days": s0_failure_days,
        "state_counts": state_counts,
        "state_ratios": state_ratios,
    }
