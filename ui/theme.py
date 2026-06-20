from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


def set_page() -> None:
    st.set_page_config(
        page_title="静澜红利",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
        menu_items={
            "About": "静澜红利：512890红利低波风格轮动信号系统。仅用于研究和可视化，不构成投资建议。"
        },
    )


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ios-bg: #F7F8FB;
            --ios-card: rgba(255,255,255,0.82);
            --ios-stroke: rgba(31,41,55,0.08);
            --ios-text: #1F2937;
            --ios-muted: #6B7280;
            --ios-blue: #7A9CC6;
            --ios-green: #7AAE9F;
            --ios-red: #D98C8C;
            --ios-amber: #D9B56D;
            --ios-purple: #B8A4D9;
        }
        .stApp { background: radial-gradient(circle at top left, #FFFFFF 0, #F7F8FB 42%, #EEF3F8 100%); }
        section[data-testid="stSidebar"] { display: none; }
        button[kind="header"] { display: none; }
        .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1280px; }
        .hero-card, .ios-card {
            border: 1px solid var(--ios-stroke);
            background: var(--ios-card);
            border-radius: 28px;
            box-shadow: 0 18px 50px rgba(31,41,55,0.08);
            padding: 24px 26px;
            backdrop-filter: blur(20px);
        }
        .hero-title { font-size: 38px; font-weight: 760; letter-spacing: -0.04em; color: var(--ios-text); line-height: 1.12; margin-bottom: 8px; }
        .hero-subtitle { color: var(--ios-muted); font-size: 15px; line-height: 1.65; }
        .status-pill {
            display: inline-flex; align-items: center; gap: 8px; padding: 8px 13px; border-radius: 999px;
            background: rgba(122,156,198,0.13); color: #405D7C; font-weight: 650; font-size: 13px;
            border: 1px solid rgba(122,156,198,0.18); white-space: nowrap;
        }
        .metric-card {
            border: 1px solid var(--ios-stroke); background: rgba(255,255,255,0.78); border-radius: 24px;
            padding: 18px 18px; min-height: 126px; box-shadow: 0 10px 28px rgba(31,41,55,0.055);
        }
        .metric-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .metric-label { color: var(--ios-muted); font-size: 13px; font-weight: 560; }
        .metric-value { color: var(--ios-text); font-size: 30px; font-weight: 760; letter-spacing: -0.035em; margin-top: 8px; }
        .metric-note { color: var(--ios-muted); font-size: 12px; margin-top: 10px; line-height: 1.45; }
        .signal-card {
            border-radius: 22px; border: 1px solid var(--ios-stroke); padding: 18px 18px; background: rgba(255,255,255,0.72);
            min-height: 170px;
        }
        .signal-name { color: #111827; font-size: 15px; font-weight: 700; }
        .signal-value { font-size: 28px; font-weight: 780; margin-top: 8px; color: #1F2937; }
        .signal-status { margin-top: 8px; font-size: 13px; color: #405D7C; font-weight: 660; }
        .signal-detail { margin-top: 10px; font-size: 12.5px; color: #6B7280; line-height: 1.5; }
        .danger { color: var(--ios-red); }
        .good { color: var(--ios-green); }
        .warn { color: var(--ios-amber); }
        div[data-testid="stMetric"] { background: rgba(255,255,255,0.65); border: 1px solid rgba(31,41,55,0.08); padding: 14px 16px; border-radius: 20px; }
        .stButton>button { border-radius: 18px; border: 1px solid rgba(31,41,55,0.08); background: white; color: #1F2937; box-shadow: 0 8px 18px rgba(31,41,55,0.06); }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] { border-radius: 999px; padding: 8px 16px; background: rgba(255,255,255,0.52); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_pwa_tags() -> None:
    components.html(
        """
        <script>
        const parentDoc = window.parent.document;
        function upsertLink(rel, href, attrs = {}) {
          let el = parentDoc.querySelector(`link[rel="${rel}"][href="${href}"]`);
          if (!el) {
            el = parentDoc.createElement('link');
            el.rel = rel;
            el.href = href;
            Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k,v));
            parentDoc.head.appendChild(el);
          }
        }
        function upsertMeta(name, content) {
          let el = parentDoc.querySelector(`meta[name="${name}"]`);
          if (!el) {
            el = parentDoc.createElement('meta');
            el.name = name;
            parentDoc.head.appendChild(el);
          }
          el.content = content;
        }
        upsertLink('manifest', 'app/static/manifest.json');
        upsertLink('apple-touch-icon', 'app/static/icon.svg');
        upsertMeta('apple-mobile-web-app-capable', 'yes');
        upsertMeta('apple-mobile-web-app-title', '静澜红利');
        upsertMeta('apple-mobile-web-app-status-bar-style', 'default');
        upsertMeta('theme-color', '#F7F8FB');
        </script>
        """,
        height=0,
    )
