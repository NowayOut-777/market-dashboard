import sys
import traceback

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="시장 대시보드",
    page_icon="📊",
    layout="wide",
)

try:
    import config
    import data_fetch as dfetch
    import risk_interpreter as risk
except Exception as _e:
    st.error("⚠️ 모듈 import 실패")
    st.code(traceback.format_exc())
    st.stop()


if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False


def _safe_section(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        st.error(f"⚠️ '{label}' 섹션 렌더링 중 오류")
        st.code(traceback.format_exc())
        return None


LIGHT_VARS = """
    --bg: #f6f7f9;
    --surface: #ffffff;
    --surface-2: #f3f5f8;
    --border: #e5e8ee;
    --border-strong: #cdd2dc;
    --ink-1: #0e131c;
    --ink-2: #2b3140;
    --ink-3: #6b7280;
    --ink-4: #9aa0ad;
    --brand-500: #276EF1;
    --brand-600: #1a59d8;
    --brand-50:  #eaf1fe;
    --accent-500: #e8744f;
    --success: #1a8d4a;
    --warning: #d97706;
    --danger:  #d12d3a;
    --shadow-1: 0 1px 0 rgba(14,19,28,0.03), 0 1px 3px rgba(14,19,28,0.05);
    --shadow-2: 0 8px 24px rgba(14,19,28,0.08);
    --grid: #e5e8ee;
    --line: #276EF1;
    --line-muted: #9aa0ad;
"""

DARK_VARS = """
    --bg: #0d1117;
    --surface: #161b22;
    --surface-2: #1f2630;
    --border: #2b3140;
    --border-strong: #3a4150;
    --ink-1: #f3f5f8;
    --ink-2: #cdd2dc;
    --ink-3: #9aa0ad;
    --ink-4: #6b7280;
    --brand-500: #4d83f4;
    --brand-600: #7ba2f7;
    --brand-50:  rgba(77,131,244,0.16);
    --accent-500: #f4a382;
    --success: #4ade80;
    --warning: #fbbf24;
    --danger:  #f87171;
    --shadow-1: 0 1px 0 rgba(0,0,0,0.4), 0 1px 3px rgba(0,0,0,0.3);
    --shadow-2: 0 8px 24px rgba(0,0,0,0.5);
    --grid: #2b3140;
    --line: #7ba2f7;
    --line-muted: #6b7280;
"""


def render_theme_css():
    vars_block = DARK_VARS if st.session_state.dark_mode else LIGHT_VARS
    css = (
        "<style>"
        "@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.css');"
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');"
        ":root {" + vars_block + "}"
        """
        html, body, .stApp, [data-testid="stAppViewContainer"], .stMarkdown, .stMarkdown p,
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"],
        button, input, select, textarea, label {
            font-family: 'Pretendard Variable', Pretendard, Inter, -apple-system, BlinkMacSystemFont,
                         system-ui, 'Segoe UI', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif !important;
            letter-spacing: -0.01em;
            font-feature-settings: 'ss01', 'cv11', 'tnum';
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        .stApp { background: var(--bg) !important; color: var(--ink-2); }
        [data-testid="stAppViewContainer"] { background: var(--bg); }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1400px; }

        h1, h2, h3, h4, h5 {
            color: var(--ink-1) !important;
            font-weight: 700 !important;
            letter-spacing: -0.022em !important;
        }
        h1 { font-size: 1.85rem !important; }
        h2 { font-size: 1.32rem !important; }
        h3 { font-size: 1.08rem !important; }
        p, span, div, li { color: var(--ink-2); }

        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px 18px;
            box-shadow: var(--shadow-1);
        }
        [data-testid="stMetricValue"] {
            font-family: 'JetBrains Mono', ui-monospace, monospace !important;
            font-variant-numeric: tabular-nums;
            color: var(--ink-1) !important;
            font-weight: 600 !important;
        }
        [data-testid="stMetricLabel"] p {
            color: var(--ink-3) !important;
            font-size: 13px !important;
            font-weight: 500 !important;
        }
        [data-testid="stMetricDelta"] {
            font-family: 'JetBrains Mono', ui-monospace, monospace !important;
            font-size: 13px !important;
        }

        [data-testid="stCaptionContainer"] p, .stCaption, small {
            color: var(--ink-3) !important;
        }

        .stMarkdown code, .stMarkdown p code, .stMarkdown li code,
        [data-testid="stMarkdownContainer"] code {
            background: var(--brand-50) !important;
            color: var(--brand-500) !important;
            border: none !important;
            border-radius: 6px !important;
            padding: 2px 8px !important;
            font-family: 'JetBrains Mono', ui-monospace, monospace !important;
            font-size: 0.95em !important;
            font-weight: 600 !important;
            font-variant-numeric: tabular-nums;
        }

        .stButton > button {
            background: var(--brand-500);
            color: #ffffff !important;
            border: 1px solid var(--brand-500);
            border-radius: 10px;
            font-weight: 500;
            box-shadow: var(--shadow-1);
            transition: background 0.15s ease;
        }
        .stButton > button:hover {
            background: var(--brand-600);
            border-color: var(--brand-600);
            color: #ffffff !important;
        }

        [data-testid="stExpander"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: var(--shadow-1);
        }
        [data-testid="stExpander"] summary, [data-testid="stExpander"] p {
            color: var(--ink-2) !important;
        }

        [data-testid="stRadio"] label p, [data-testid="stSelectbox"] label p {
            color: var(--ink-2) !important;
            font-weight: 500 !important;
        }
        div[data-testid="stRadio"] > div { gap: 6px; }

        hr, [data-testid="stDivider"] {
            border-color: var(--border) !important;
            margin: 1.6rem 0 !important;
        }

        div[data-testid="stPlotlyChart"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            box-shadow: var(--shadow-1);
        }

        [data-baseweb="tab-list"] {
            background: var(--surface-2) !important;
            border-radius: 10px;
            padding: 4px;
            gap: 4px !important;
            border: 1px solid var(--border);
        }
        [data-baseweb="tab"] {
            background: transparent !important;
            color: var(--ink-3) !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            padding: 8px 14px !important;
        }
        [data-baseweb="tab"][aria-selected="true"] {
            background: var(--surface) !important;
            color: var(--ink-1) !important;
            box-shadow: var(--shadow-1);
        }
        [data-baseweb="tab-highlight"] { display: none !important; }
        [data-baseweb="tab-border"] { display: none !important; }

        [data-testid="stToggle"] label p { color: var(--ink-2) !important; }

        .kbh-section-title {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 0 0 14px 0;
        }
        .kbh-section-num {
            background: var(--brand-50);
            color: var(--brand-500);
            border-radius: 999px;
            width: 28px; height: 28px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 13px;
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            flex-shrink: 0;
        }
        .kbh-section-title h2 { margin: 0 !important; }
        .num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
        </style>
        """
    )
    st.markdown(css, unsafe_allow_html=True)


try:
    render_theme_css()
except Exception:
    st.error("⚠️ 테마 CSS 렌더링 실패")
    st.code(traceback.format_exc())


def section_title(num: int, title: str):
    st.markdown(
        f"<div class='kbh-section-title'>"
        f"<span class='kbh-section-num'>{num}</span>"
        f"<h2>{title}</h2></div>",
        unsafe_allow_html=True,
    )


def plotly_layout():
    is_dark = st.session_state.dark_mode
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Pretendard Variable, Pretendard, Inter, system-ui, sans-serif",
            color="#cdd2dc" if is_dark else "#2b3140",
            size=12,
        ),
        colorway=["#4d83f4" if is_dark else "#276EF1", "#f4a382" if is_dark else "#e8744f",
                  "#4ade80" if is_dark else "#1a8d4a", "#fbbf24" if is_dark else "#d97706",
                  "#7ba2f7", "#9aa0ad"],
    )


def grid_color() -> str:
    return "#2b3140" if st.session_state.dark_mode else "#e5e8ee"


def line_color() -> str:
    return "#7ba2f7" if st.session_state.dark_mode else "#276EF1"


def muted_color() -> str:
    return "#6b7280" if st.session_state.dark_mode else "#9aa0ad"


def password_gate() -> bool:
    pw = config.get_app_password()
    if not pw:
        return True
    if st.session_state.get("auth_ok"):
        return True
    entered = st.text_input("🔒 비밀번호", type="password")
    if entered:
        if entered == pw:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    return False


try:
    if not password_gate():
        st.stop()
except Exception:
    st.error("⚠️ 비밀번호 게이트 오류")
    st.code(traceback.format_exc())
    st.stop()


def index_card(name: str, ticker: str):
    df = dfetch.fetch_index_history(ticker)
    if df.empty or df["Close"].dropna().empty:
        st.warning(f"{name}: 데이터 없음")
        return

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else last_close
    change_pct = (last_close / prev_close - 1) * 100

    ma200 = df["MA200"].dropna()
    ma_value = float(ma200.iloc[-1]) if not ma200.empty else None
    vs_ma_pct = ((last_close / ma_value) - 1) * 100 if ma_value else None

    st.metric(
        label=name,
        value=f"{last_close:,.2f}",
        delta=f"{change_pct:+.2f}%",
    )
    if vs_ma_pct is not None:
        color = "🟢" if vs_ma_pct >= 0 else "🔴"
        st.caption(f"{color} 200일선 대비 {vs_ma_pct:+.2f}% (MA200: {ma_value:,.2f})")
    else:
        st.caption("200일선 산출에 데이터가 부족합니다.")

    chart_df = df.tail(260).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart_df["Date"], y=chart_df["Close"],
        name="Close", line=dict(width=2, color=line_color()),
    ))
    fig.add_trace(go.Scatter(
        x=chart_df["Date"], y=chart_df["MA200"],
        name="MA200", line=dict(width=1.5, dash="dash", color=muted_color()),
    ))
    fig.update_layout(
        **plotly_layout(),
        height=220, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True, legend=dict(orientation="h", y=-0.2),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=grid_color()),
    )
    st.plotly_chart(fig, use_container_width=True)


def fear_greed_gauge(score: float, rating: str):
    rating_kor = {
        "extreme fear": "극단적 공포",
        "fear": "공포",
        "neutral": "중립",
        "greed": "탐욕",
        "extreme greed": "극단적 탐욕",
    }.get(rating.lower(), rating)

    is_dark = st.session_state.dark_mode
    title_color = "#cdd2dc" if is_dark else "#2b3140"
    number_color = "#f3f5f8" if is_dark else "#0e131c"
    bar_color = "#f3f5f8" if is_dark else "#0e131c"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": f"공포탐욕지수: {rating_kor}", "font": {"size": 14, "color": title_color}},
        number={"font": {"family": "JetBrains Mono", "size": 36, "color": number_color}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": muted_color()},
            "bar": {"color": bar_color, "thickness": 0.25},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 25], "color": "#d12d3a"},
                {"range": [25, 45], "color": "#e8744f"},
                {"range": [45, 55], "color": "#fbc02d"},
                {"range": [55, 75], "color": "#7ba2f7"},
                {"range": [75, 100], "color": "#1a8d4a"},
            ],
        },
    ))
    fig.update_layout(**plotly_layout(), height=260, margin=dict(l=10, r=10, t=40, b=10))
    return fig


def vol_card(name: str, ticker: str, levels: dict, interpret_fn):
    df = dfetch.fetch_index_history(ticker, period="1y")
    if df.empty:
        st.warning(f"{name}: 데이터 없음")
        return
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else last
    sig = interpret_fn(last)

    st.metric(
        label=f"{sig.icon} {name}",
        value=f"{last:.2f}",
        delta=f"{(last - prev):+.2f}",
    )
    st.caption(sig.headline)

    chart_df = df.tail(180).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart_df["Date"], y=chart_df["Close"],
        name=name, line=dict(width=2, color=line_color()),
    ))
    threshold_colors = {"safe": "#1a8d4a", "warning": "#d97706", "danger": "#d12d3a"}
    for level_name, level_val in levels.items():
        fig.add_hline(
            y=level_val, line_dash="dot", line_width=1,
            line_color=threshold_colors.get(level_name, muted_color()),
            annotation_text=f"{level_name} {level_val:.0f}",
            annotation_position="right",
            opacity=0.55,
        )
    fig.update_layout(
        **plotly_layout(),
        height=200, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor=grid_color()),
    )
    st.plotly_chart(fig, use_container_width=True)


def commodity_metric(name: str, ticker: str):
    info = dfetch.fetch_latest_price(ticker)
    if info is None:
        st.metric(label=name, value="데이터 없음")
        return
    st.metric(
        label=name,
        value=f"{info['price']:,.2f}",
        delta=f"{info['change_pct']:+.2f}%",
    )
    st.caption(f"기준일: {info['as_of']}")


# =========================
# Header
# =========================
st.title("미국 시장 대시보드")
hcol1, hcol2, hcol3 = st.columns([4, 1.2, 1])
with hcol1:
    st.caption(f"마지막 갱신: {dfetch.now_kst_str()}  •  데이터 캐시 1시간")
with hcol2:
    new_dark = st.toggle(
        "🌙 다크 모드",
        value=st.session_state.dark_mode,
        key="dark_toggle",
    )
    if new_dark != st.session_state.dark_mode:
        st.session_state.dark_mode = new_dark
        st.rerun()
with hcol3:
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# =========================
# 1. Indices vs 200MA
# =========================
section_title(1, "미국 3대 지수 — 전일 종가 & 200일 이동평균")
cols = st.columns(3)
for col, (name, ticker) in zip(cols, config.INDICES.items()):
    with col:
        index_card(name, ticker)

st.divider()

# =========================
# 2. Fear & Greed
# =========================
section_title(2, "CNN 공포탐욕지수")
fg = dfetch.fetch_fear_greed()
if fg and "error" not in fg:
    cga, cgb = st.columns([1, 1])
    with cga:
        st.plotly_chart(fear_greed_gauge(fg["score"], fg["rating"]), use_container_width=True)
    with cgb:
        st.markdown(f"**현재**: `{fg['score']:.1f}` ({fg['rating']})")
        if fg.get("previous_close") is not None:
            st.markdown(f"- 전일: `{float(fg['previous_close']):.1f}`")
        if fg.get("previous_1_week") is not None:
            st.markdown(f"- 1주 전: `{float(fg['previous_1_week']):.1f}`")
        if fg.get("previous_1_month") is not None:
            st.markdown(f"- 1개월 전: `{float(fg['previous_1_month']):.1f}`")
        if fg.get("previous_1_year") is not None:
            st.markdown(f"- 1년 전: `{float(fg['previous_1_year']):.1f}`")
        st.caption("0~25 극단적 공포 / 25~45 공포 / 45~55 중립 / 55~75 탐욕 / 75~100 극단적 탐욕")
else:
    err = fg.get("error", "알 수 없는 오류") if fg else "응답 없음"
    st.warning(f"공포탐욕지수 조회 실패: {err}")

st.divider()

# =========================
# 3. Volatility Indices (VIX, MOVE)
# =========================
section_title(3, "변동성 지수 — VIX (주식) · MOVE (채권)")
vcols = st.columns(2)
with vcols[0]:
    vol_card("VIX", "^VIX", config.VIX_LEVELS, risk.interpret_vix)
with vcols[1]:
    vol_card("MOVE", "^MOVE", config.MOVE_LEVELS, risk.interpret_move)

st.divider()

# =========================
# 4. Bonds & Commodities
# =========================
section_title(4, "채권 & 원자재")
fred_key = config.get_fred_api_key()
yield_df = dfetch.fetch_fred_series(config.FRED_SERIES["us_10y"], fred_key)
hy_df = dfetch.fetch_fred_series(config.FRED_SERIES["hy_spread"], fred_key)

cols = st.columns(6)

def fred_caption(api_key: str) -> str:
    return "FRED API 키를 확인해 주세요" if not api_key else "FRED 응답 일시 지연 — 잠시 후 새로고침"

with cols[0]:
    if not yield_df.empty:
        latest_y = float(yield_df["value"].iloc[-1])
        prev_y = float(yield_df["value"].iloc[-2]) if len(yield_df) >= 2 else latest_y
        st.metric("10Y 금리", f"{latest_y:.2f}%", delta=f"{(latest_y - prev_y)*100:+.0f}bp")
        st.caption(f"기준일: {yield_df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    else:
        st.metric("10Y 금리", "데이터 없음")
        st.caption(fred_caption(fred_key))

with cols[1]:
    if not hy_df.empty:
        latest_h = float(hy_df["value"].iloc[-1])
        prev_h = float(hy_df["value"].iloc[-2]) if len(hy_df) >= 2 else latest_h
        st.metric("HY 스프레드", f"{latest_h:.2f}%", delta=f"{(latest_h - prev_h)*100:+.0f}bp")
        st.caption(f"기준일: {hy_df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    else:
        st.metric("HY 스프레드", "데이터 없음")
        st.caption(fred_caption(fred_key))

remaining = list(config.COMMODITIES_FX.items())
for i, (name, ticker) in enumerate(remaining):
    with cols[i + 2]:
        commodity_metric(name, ticker)

st.divider()

# =========================
# 5. Risk Interpretation
# =========================
section_title(5, "시장 위험 해석 (10Y · HY 스프레드 · VIX · MOVE)")

if yield_df.empty or hy_df.empty:
    st.info("FRED API 키가 설정되지 않으면 위험 해석을 표시할 수 없습니다.")
else:
    yield_sig = risk.interpret_10y(yield_df["value"])
    hy_sig = risk.interpret_hy_spread(hy_df["value"])
    yc = (yield_df["value"].iloc[-1] - yield_df["value"].iloc[-6]) * 100 if len(yield_df) >= 6 else 0
    hc = (hy_df["value"].iloc[-1] - hy_df["value"].iloc[-6]) * 100 if len(hy_df) >= 6 else 0
    combined = risk.combine(yield_sig, hy_sig, yc, hc)

    vix_df = dfetch.fetch_index_history("^VIX", period="6mo")
    move_df = dfetch.fetch_index_history("^MOVE", period="6mo")
    vix_sig = risk.interpret_vix(float(vix_df["Close"].iloc[-1])) if not vix_df.empty else None
    move_sig = risk.interpret_move(float(move_df["Close"].iloc[-1])) if not move_df.empty else None

    rcols = st.columns(2)
    with rcols[0]:
        st.markdown(f"#### {yield_sig.icon} 10Y 금리")
        st.markdown(f"**{yield_sig.headline}**")
        st.write(yield_sig.detail)
        st.markdown(f"#### {hy_sig.icon} HY 스프레드")
        st.markdown(f"**{hy_sig.headline}**")
        st.write(hy_sig.detail)
    with rcols[1]:
        if vix_sig:
            st.markdown(f"#### {vix_sig.icon} VIX (주식 변동성)")
            st.markdown(f"**{vix_sig.headline}**")
            st.write(vix_sig.detail)
        if move_sig:
            st.markdown(f"#### {move_sig.icon} MOVE (채권 변동성)")
            st.markdown(f"**{move_sig.headline}**")
            st.write(move_sig.detail)

    st.markdown("---")
    st.markdown(f"### {combined.icon} 종합 판단 (10Y + HY)")
    st.markdown(f"**{combined.headline}**")
    st.write(combined.detail)

    with st.expander("🧭 해석 임계치 가이드"):
        st.markdown("""
**10년물 금리 (5일 변동 기준)**
- 🟢 ±30bp 이내: 안정
- 🟡 -30bp 이하 급락: 경기 둔화 / 안전자산 쏠림
- 🔴 +30bp 이상 급등: 주식 PER 압박, 성장주 매도 위험

**하이일드 스프레드 (절대 수준 기준, FRED BAMLH0A0HYM2)**
- 🟢 < 3.5%: 위험선호 강함, 시장 안정
- 🟡 3.5~5%: 정상 범위 (장기 평균 부근)
- 🟠 5~7%: 신용 우려 확산
- 🔴 > 7%: 신용 경색·침체 신호 (2008·2020 수준)
- 🔴 5일간 +50bp 이상 급확대: 조기경보 (주식 하락 선행지표)

**조합 신호**
- 🔴 금리·스프레드 동시 급등: 긴축/스태그플레이션 위험
- 🔴 금리 하락 + 스프레드 상승: 전형적 리세션 패턴

**VIX (S&P 500 옵션 내재변동성, 절대 수준)**
- 🟢 < 15: 매우 낮음 (안일 — 역설적으로 변곡점 주의)
- 🟡 15~20: 정상 (장기 평균 부근)
- 🟠 20~30: 경계 (헤지 비용 상승, 우려 형성)
- 🔴 30~40: 공포
- 🔴 40+: 패닉 (2008·2020 위기 수준)

**MOVE (미 국채 옵션 내재변동성, 절대 수준)**
- 🟢 < 80: 채권시장 안정
- 🟡 80~110: 정상
- 🟠 110~140: 경계 (통화정책 불확실성·인플레이션 우려)
- 🔴 140+: 채권시장 스트레스 (2022~2023 SVB 사태급)
""")

st.divider()

# =========================
# 6. Sector ETFs (좌하단)
# =========================
section_title(6, "섹터 · 종목 트래커")


def render_picker_chart(group: dict, default_idx: int = 0, key_prefix: str = ""):
    cols = st.columns([1, 2.4])
    with cols[0]:
        choice = st.radio(
            "선택",
            list(group.keys()),
            index=default_idx,
            label_visibility="collapsed",
            key=f"{key_prefix}_radio",
        )
        ticker = group[choice]
        info = dfetch.fetch_latest_price(ticker)
        if info:
            st.metric(
                label=f"{choice}",
                value=f"${info['price']:,.2f}",
                delta=f"{info['change_pct']:+.2f}%",
            )
            st.caption(f"기준일: {info['as_of']}")

    with cols[1]:
        df = dfetch.fetch_index_history(ticker, period="2y")
        if df.empty:
            st.warning("데이터 없음")
            return
        last_close = float(df["Close"].iloc[-1])
        ma200 = df["MA200"].dropna()
        ma_value = float(ma200.iloc[-1]) if not ma200.empty else None
        vs_ma_pct = ((last_close / ma_value) - 1) * 100 if ma_value else None

        if vs_ma_pct is not None:
            badge = "🟢" if vs_ma_pct >= 0 else "🔴"
            st.markdown(
                f"**{choice} ({ticker})** · {badge} 200일선 대비 "
                f"<span class='num'>{vs_ma_pct:+.2f}%</span> "
                f"(MA200: <span class='num'>${ma_value:,.2f}</span>)",
                unsafe_allow_html=True,
            )

        chart_df = df.tail(260).reset_index()
        primary = line_color()
        r, g, b = (int(primary[i:i+2], 16) for i in (1, 3, 5))
        fill = f"rgba({r}, {g}, {b}, 0.08)"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df["Date"], y=chart_df["Close"],
            name="Close", line=dict(width=2.5, color=primary),
            fill="tozeroy", fillcolor=fill,
        ))
        fig.add_trace(go.Scatter(
            x=chart_df["Date"], y=chart_df["MA200"],
            name="MA200", line=dict(width=1.5, dash="dash", color=muted_color()),
        ))
        fig.update_layout(
            **plotly_layout(),
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True, legend=dict(orientation="h", y=-0.15),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor=grid_color()),
        )
        st.plotly_chart(fig, use_container_width=True)


tab_labels = ["섹터 ETF", "M7", "반도체"] + list(config.SECTOR_LEADERS.keys())
tabs = st.tabs(tab_labels)

with tabs[0]:
    render_picker_chart(config.SECTOR_ETFS, default_idx=7, key_prefix="sec")
with tabs[1]:
    render_picker_chart(config.MAG7, default_idx=6, key_prefix="m7")
with tabs[2]:
    render_picker_chart(config.SEMICONDUCTORS, default_idx=0, key_prefix="semi")

for i, (sector_name, group) in enumerate(config.SECTOR_LEADERS.items(), start=3):
    with tabs[i]:
        render_picker_chart(group, default_idx=0, key_prefix=f"lead_{sector_name}")

st.divider()
st.caption("본 대시보드는 정보 제공용이며 투자 권유가 아닙니다.")
