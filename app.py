from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from strategy.backtest import run_backtest
from strategy.data_loader import AUTO_PORTFOLIO, LATEST_SIGNAL, live_data_exists, load_live_data, load_sample_data
from strategy.indicators import add_indicators
from strategy.state_machine import evaluate_strategy
from ui.components import explain_list, hero, price_chart, r_chart, score_gauge, signal_cards, top_metrics
from ui.theme import inject_css, inject_pwa_tags, set_page


set_page()
inject_css()
inject_pwa_tags()

CAPITAL = 100_000.0
BACKTEST_PERIODS = {
    "两年": pd.DateOffset(years=2),
    "一年": pd.DateOffset(years=1),
    "六个月": pd.DateOffset(months=6),
    "三个月": pd.DateOffset(months=3),
}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _auto_position_inputs(df: pd.DataFrame, capital: float) -> tuple[float, float | None, int, dict]:
    portfolio = _read_json(AUTO_PORTFOLIO)
    latest_close = float(df.iloc[-1]["close_512890"])
    shares = int(portfolio.get("shares_512890", 0))
    position_ratio = (shares * latest_close) / float(portfolio.get("capital", capital) or capital)
    average_cost = portfolio.get("average_cost")
    state_days_held = int(portfolio.get("state_days_held", 0))
    return position_ratio, average_cost, state_days_held, portfolio


def _backtest_start_date(df: pd.DataFrame, period_label: str) -> pd.Timestamp:
    latest_date = pd.to_datetime(df["date"]).max()
    earliest_date = pd.to_datetime(df["date"]).min()
    offset = BACKTEST_PERIODS[period_label]
    return max(earliest_date, latest_date - offset)


def _s0_failure_summary(failures: pd.DataFrame) -> pd.DataFrame:
    if failures.empty or "failed_conditions" not in failures.columns:
        return pd.DataFrame(columns=["失败条件", "次数"])
    counts: dict[str, int] = {}
    for item in failures["failed_conditions"].dropna():
        for condition in str(item).split("、"):
            condition = condition.strip()
            if condition:
                counts[condition] = counts.get(condition, 0) + 1
    if not counts:
        return pd.DataFrame(columns=["失败条件", "次数"])
    return pd.DataFrame([{"失败条件": k, "次数": v} for k, v in counts.items()]).sort_values("次数", ascending=False)


@st.cache_data(show_spinner=False)
def _cached_backtest_with_diagnostics(csv_payload: str, start_date: str, end_date: str, capital: float):
    from io import StringIO

    cached_df = pd.read_csv(StringIO(csv_payload))
    return run_backtest(cached_df, initial_capital=capital, start_date=start_date, end_date=end_date)


if live_data_exists():
    df = load_live_data()
    data_mode = "自动更新数据"
else:
    df = load_sample_data()
    data_mode = "示例数据"

enriched = add_indicators(df)
latest_signal = _read_json(LATEST_SIGNAL)
current_position, average_cost, state_days_held, portfolio = _auto_position_inputs(enriched, CAPITAL) if data_mode == "自动更新数据" else (0.0, None, 0, {})

result = evaluate_strategy(
    enriched,
    current_position=current_position,
    average_cost=average_cost,
    capital=CAPITAL,
    cooldown_days_left=0,
    state_days_held=state_days_held,
)

hero(result)
st.write("")
top_metrics(result)
st.write("")
signal_cards(result)

main_tab, signal_tab, backtest_tab, data_tab, rules_tab = st.tabs(["总览", "信号细节", "回测", "数据", "规则说明"])

with main_tab:
    left, right = st.columns([0.38, 0.62])
    with left:
        st.plotly_chart(score_gauge(result), use_container_width=True)
        explain_list("触发原因", result.reasons)
        explain_list("风险提示", result.warnings)
    with right:
        st.plotly_chart(price_chart(enriched), use_container_width=True)
        st.plotly_chart(r_chart(enriched), use_container_width=True)

with signal_tab:
    st.markdown("### 四信号得分")
    st.dataframe(pd.DataFrame([c.__dict__ for c in result.cards]), use_container_width=True, hide_index=True)

with backtest_tab:
    st.markdown("### 策略回测")
    st.caption("回测严格使用T日收盘后信号、T+1开盘执行。买入有高开降额/暂缓规则，卖出不设低开保护。")
    period_label = st.radio("回测区间", list(BACKTEST_PERIODS.keys()), index=0, horizontal=True)
    start_date = _backtest_start_date(enriched, period_label)
    end_date = pd.to_datetime(enriched["date"]).max()
    st.caption(f"当前区间：{start_date.date()} 至 {end_date.date()}。区间前数据仅用于均线和信号预热。")
    if not st.button("运行回测", type="primary", use_container_width=True):
        st.info("为保证PWA首页快速打开，回测不会自动运行。选择区间后点击运行回测。")
    else:
        with st.spinner("正在运行回测、基准与诊断……"):
            bt = _cached_backtest_with_diagnostics(enriched.to_csv(index=False), str(start_date.date()), str(end_date.date()), CAPITAL)

        strategy_return = bt.metrics.get("total_return", 0.0)
        benchmark_return = bt.metrics.get("benchmark_total_return", 0.0)
        excess_return = bt.metrics.get("excess_return", strategy_return - benchmark_return)
        average_position = bt.diagnostics.get("average_position", 0.0)
        exposure_ratio = bt.diagnostics.get("exposure_ratio", 0.0)
        s0_ratio = bt.diagnostics.get("s0_ratio", 0.0)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("策略累计收益", f"{strategy_return*100:.2f}%")
        m2.metric("512890持有收益", f"{benchmark_return*100:.2f}%")
        m3.metric("超额收益", f"{excess_return*100:.2f}%")
        m4.metric("最终权益", f"¥{bt.metrics.get('final_equity', CAPITAL):,.0f}")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("策略最大回撤", f"{bt.metrics.get('max_drawdown', 0)*100:.2f}%")
        d2.metric("512890最大回撤", f"{bt.metrics.get('benchmark_max_drawdown', 0)*100:.2f}%")
        d3.metric("平均仓位", f"{average_position*100:.1f}%")
        d4.metric("交易次数", f"{bt.metrics.get('trade_count', 0)}")

        if not bt.equity_curve.empty:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=bt.equity_curve["date"], y=bt.equity_curve["equity"], mode="lines", name="策略权益"))
            if not bt.benchmark_curve.empty:
                fig.add_trace(go.Scatter(x=bt.benchmark_curve["date"], y=bt.benchmark_curve["equity"], mode="lines", name="512890买入持有"))
            fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.4)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("当前区间可用于回测的数据不足。请先完成两年真实历史数据建库，或选择更长区间。")

        st.markdown("#### 仓位与状态诊断")
        c1, c2, c3 = st.columns(3)
        c1.metric("持仓暴露率", f"{exposure_ratio*100:.1f}%")
        c2.metric("S0空仓状态占比", f"{s0_ratio*100:.1f}%")
        c3.metric("S0→S1失败天数", f"{bt.diagnostics.get('s0_failure_days', 0)}")

        state_counts = bt.diagnostics.get("state_counts", {})
        if state_counts:
            state_df = pd.DataFrame([{"状态": k, "天数": v, "占比": bt.diagnostics.get("state_ratios", {}).get(k, 0)} for k, v in state_counts.items()])
            state_df["占比"] = state_df["占比"].map(lambda x: f"{x*100:.1f}%")
            st.dataframe(state_df, use_container_width=True, hide_index=True)

        st.markdown("#### S0→S1失败条件统计")
        failure_summary = _s0_failure_summary(bt.s0_gate_failures)
        if failure_summary.empty:
            st.success("当前区间没有明显的S0→S1失败记录，或区间内未处于S0空仓状态。")
        else:
            st.dataframe(failure_summary, use_container_width=True, hide_index=True)
            with st.expander("查看逐日S0诊断明细"):
                st.dataframe(bt.s0_gate_failures, use_container_width=True, hide_index=True)

        st.markdown("#### 交易记录")
        st.dataframe(bt.trades, use_container_width=True, hide_index=True)

with data_tab:
    st.markdown("### 行情数据")
    st.caption("自动更新版本每天18:15（北京时间）由GitHub Actions写入 data/live_prices.csv 和 data/latest_signal.json。")
    st.dataframe(enriched, use_container_width=True, hide_index=True)
    st.download_button("下载当前指标数据CSV", enriched.to_csv(index=False).encode("utf-8-sig"), file_name="512890_signal_indicators.csv", mime="text/csv")

with rules_tab:
    st.markdown(
        """
        ### 核心规则

        1. 只交易512890，现金为唯一防守资产。
        2. 每天收盘后计算信号，下一交易日开盘执行。
        3. 自动版本的GitHub Actions在北京时间18:15运行，生成当天收盘后的信号快照。
        4. R=588000/512890。R不跌破1.70，不允许建立观察仓。
        5. 512890没有CLV强承接，不允许买入。
        6. 没有站上MA5，不允许升至40%；没有站上MA10，不允许升至70%；没有站上MA20且R没有跌破1.59，不允许满仓。
        7. 卖出信号优先于买入信号。异常下跌和止损信号优先级最高。
        8. 买入遇到T+1高开超过0.8%降额，超过1.5%暂缓；卖出不设低开保护。
        9. 连续误判后进入冷却期，冷却期内不新增买入。

        本系统仅用于研究和风格轮动可视化，不构成投资建议。
        """
    )
