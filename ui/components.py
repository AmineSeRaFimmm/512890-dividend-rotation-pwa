from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from strategy.models import SignalResult


def hero(result: SignalResult) -> None:
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="status-pill">{result.target_state.value}</div>
          <div class="hero-title">512890 红利低波信号系统</div>
          <div class="hero-subtitle">T日收盘后计算信号，下一交易日开盘执行。当前目标仓位 <b>{result.target_position_pct}%</b>，动作：<b>{action_cn(result.action)}</b>。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def action_cn(action: str) -> str:
    return {
        "BUY_512890": "买入512890",
        "SELL_512890": "卖出512890",
        "HOLD": "持有/等待",
    }.get(action, action)


def top_metrics(result: SignalResult) -> None:
    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("总分", f"{result.total_score}/12", "四类信号综合评分"),
        ("目标仓位", f"{result.target_position_pct}%", "只允许512890+现金"),
        ("执行金额", f"¥{result.action_amount:,.0f}", "按10万元本金换算"),
        ("预估份额", f"{result.action_shares_estimate or 0:,}", "按信号日收盘价估算"),
    ]
    for col, (label, value, note) in zip([c1, c2, c3, c4], metrics):
        with col:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div><div class='metric-note'>{note}</div></div>", unsafe_allow_html=True)


def signal_cards(result: SignalResult) -> None:
    cols = st.columns(4)
    for col, card in zip(cols, result.cards):
        with col:
            st.markdown(
                f"""
                <div class="signal-card">
                  <div class="signal-name">{card.name}</div>
                  <div class="signal-value">{card.value}</div>
                  <div class="signal-status">{card.status} · {card.score}分</div>
                  <div class="signal-detail">{card.detail}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def score_gauge(result: SignalResult) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=result.total_score,
        number={"suffix": "/12"},
        gauge={
            "axis": {"range": [0, 12]},
            "bar": {"thickness": 0.18},
            "steps": [
                {"range": [0, 3], "color": "rgba(217,140,140,0.26)"},
                {"range": [3, 6], "color": "rgba(217,181,109,0.26)"},
                {"range": [6, 9], "color": "rgba(122,156,198,0.26)"},
                {"range": [9, 12], "color": "rgba(122,174,159,0.28)"},
            ],
        },
        title={"text": "策略总分"},
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def price_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["close_512890"], mode="lines", name="512890"))
    if "ma5_512890" in df.columns:
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma5_512890"], mode="lines", name="MA5"))
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma10_512890"], mode="lines", name="MA10"))
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma20_512890"], mode="lines", name="MA20"))
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.4)", legend=dict(orientation="h"))
    return fig


def r_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["r_tech_dividend"], mode="lines", name="R=588000/512890"))
    for y, name in [(1.75, "科技吸血"), (1.70, "预警"), (1.64, "确认"), (1.59, "强确认")]:
        fig.add_hline(y=y, line_dash="dash", annotation_text=name, annotation_position="top left")
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.4)", legend=dict(orientation="h"))
    return fig


def explain_list(title: str, items: Iterable[str]) -> None:
    items = list(items)
    if not items:
        return
    st.markdown(f"#### {title}")
    for item in items:
        st.markdown(f"- {item}")
