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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _auto_position_inputs(df: pd.DataFrame, capital: float) -> tuple[float, float | None, dict]:
    portfolio = _read_json(AUTO_PORTFOLIO)
    latest_close = float(df.iloc[-1]["close_512890"])
    shares = int(portfolio.get("shares_512890", 0))
    position_ratio = (shares * latest_close) / float(portfolio.get("capital", capital) or capital)
    average_cost = portfolio.get("average_cost")
    return position_ratio, average_cost, portfolio


if live_data_exists():
    df = load_live_data()
    data_mode = "自动更新数据"
else:
    df = load_sample_data()
    data_mode = "示例数据"

enriched = add_indicators(df)
latest_signal = _read_json(LATEST_SIGNAL)
current_position, average_cost, portfolio = _auto_position_inputs(enriched, CAPITAL) if data_mode == "自动更新数据" else (0.0, None, {})

result = evaluate_strategy(
    enriched,
    current_position=current_position,
    average_cost=average_cost,
    capital=CAPITAL,
    cooldown_days_left=0,
)

hero(result)
st.write("")
top_metrics(result)
st.write("")
signal_cards(result)

if data_mode == "自动更新数据" and latest_signal:
    auto = latest_signal.get("auto_update", {})
    pending = auto.get("next_execution")
    executed = auto.get("executed_trade_from_previous_signal")
    st.markdown("### 自动更新状态")
    c1, c2, c3 = st.columns(3)
    c1.info(f"信号日期：{auto.get('signal_date', latest_signal.get('date', result.date))}")
    c2.info(f"数据源：{auto.get('source', 'N/A')}")
    c3.info(f"下一步：{pending.get('side', 'HOLD') if pending else 'HOLD'}")
    if pending:
        st.caption(f"待执行计划：{pending.get('side')}，计划金额 ¥{pending.get('planned_amount', 0):,.0f}，下一交易日开盘执行。")
    if executed:
        st.caption(f"上一信号执行记录：{executed.get('side')} {executed.get('shares')}份，金额 ¥{executed.get('executed_amount', 0):,.0f}，状态 {executed.get('execution_status')}。")

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
    st.markdown("### 当日原始指标")
    st.json(result.raw)
    st.markdown("### 硬性标记")
    st.json(result.hard_flags)
    st.markdown("### 四信号得分")
    st.dataframe(pd.DataFrame([c.__dict__ for c in result.cards]), use_container_width=True, hide_index=True)
    if data_mode == "自动更新数据":
        st.markdown("### 自动组合状态")
        st.json(portfolio)
        st.markdown("### 最新信号JSON")
        st.json(latest_signal)

with backtest_tab:
    st.markdown("### 策略回测")
    st.caption("回测严格使用T日收盘后信号、T+1开盘执行。买入有高开降额/暂缓规则，卖出不设低开保护。")
    bt = run_backtest(enriched, initial_capital=CAPITAL)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("最终权益", f"¥{bt.metrics.get('final_equity', CAPITAL):,.0f}")
    m2.metric("累计收益", f"{bt.metrics.get('total_return', 0)*100:.2f}%")
    m3.metric("最大回撤", f"{bt.metrics.get('max_drawdown', 0)*100:.2f}%")
    m4.metric("交易次数", f"{bt.metrics.get('trade_count', 0)}")
    if not bt.equity_curve.empty:
        import plotly.graph_objects as go

        fig = go.Figure(go.Scatter(x=bt.equity_curve["date"], y=bt.equity_curve["equity"], mode="lines", name="权益曲线"))
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.4)")
        st.plotly_chart(fig, use_container_width=True)
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
