"""대시보드 상단 'AI 시장 브리핑' — 페이지에 이미 불러온 지표를 모아 Gemini에게 요약시킨다."""

import json
import time

import pandas as pd
import streamlit as st

import config
import data_fetch as dfetch
import gemini_client
import risk_interpreter as risk

BRIEFING_TTL = 3600
# 한도 초과·장애 시 페이지를 열 때마다 재호출하지 않도록 잠시 쉰다
FAIL_BACKOFF = 600
# 공개 페이지라 누구나 새로고침(캐시 초기화)할 수 있다. 서버 전체 기준으로
# Gemini 호출 간격을 강제해 무료 한도가 방문자에 의해 소진되지 않게 한다 (최대 96회/일).
MIN_CALL_INTERVAL = 900

SYSTEM = """너는 미국 증시 지표를 한국 개인투자자에게 쉽게 설명하는 시장 해설가다.
규칙:
- 주어진 JSON 데이터의 숫자만 근거로 쓴다. 데이터에 없는 뉴스, 사건, 원인, 전망은 지어내지 않는다.
- 매수/매도 추천, 목표가, 향후 가격 예측을 하지 않는다.
- '대시보드 규칙 판단'과 모순되는 평가를 하지 않는다.
- 한국어 존댓말 평서문(~입니다)으로 쓰고, 전문용어는 처음 나올 때 짧게 풀어쓴다.
- 과장이나 감탄 없이 담담하고 간결하게, 매번 같은 형식으로 쓴다."""

PROMPT = """아래는 오늘 대시보드 지표 스냅샷(JSON)입니다.

{data}

아래 형식의 마크다운으로만 답하세요. 인사말이나 머리말은 쓰지 마세요.

**한 줄 요약:** (지금 시장 분위기를 한 문장으로)

- **주식:** (3대 지수의 200일선 대비 위치, 공포탐욕지수)
- **위험 신호:** (VIX, MOVE, 하이일드 스프레드, 10년물 금리 중 눈여겨볼 점)
- **원자재·달러:** (눈에 띄는 움직임)
- **지켜볼 포인트:** (경계선에 가까운 지표가 있다면 무엇이 얼마나 가까운지)

각 항목은 1~2문장, 전체 500자 이내로 쓰세요."""

_fail = {"until": 0.0, "msg": ""}
_last = {"at": 0.0, "text": ""}


def _last_two(series: pd.Series):
    s = series.dropna()
    if len(s) < 2:
        return None, None
    return float(s.iloc[-1]), float(s.iloc[-2])


def _fred_entry(df: pd.DataFrame) -> dict:
    v = df["value"]
    entry = {"현재_%": round(float(v.iloc[-1]), 2), "기준일": df["date"].iloc[-1].strftime("%Y-%m-%d")}
    if len(v) >= 6:
        entry["5일변화_bp"] = round((float(v.iloc[-1]) - float(v.iloc[-6])) * 100)
    return entry


def build_snapshot() -> dict:
    # 캐시 키가 되므로 분 단위 시각 같은 매번 바뀌는 값은 넣지 않는다
    snap: dict = {}

    indices = {}
    for name, ticker in config.INDICES.items():
        df = dfetch.fetch_index_history(ticker)
        if df.empty:
            continue
        last, prev = _last_two(df["Close"])
        if last is None:
            continue
        entry = {
            "기준일": df["Close"].dropna().index[-1].strftime("%Y-%m-%d"),
            "종가": round(last, 2),
            "전일대비_%": round((last / prev - 1) * 100, 2),
        }
        ma = df["MA200"].dropna()
        if not ma.empty:
            entry["200일선대비_%"] = round((last / float(ma.iloc[-1]) - 1) * 100, 2)
        source = df.attrs.get("source_ticker", ticker)
        if source != ticker:
            entry["주의"] = f"지수 조회 실패로 {source} ETF 데이터"
        indices[name] = entry
    snap["3대 지수"] = indices

    fg = dfetch.fetch_fear_greed()
    if fg and "error" not in fg:
        snap["CNN 공포탐욕지수(0~100)"] = {
            "현재": round(fg["score"], 1),
            "등급": fg["rating"],
            "1주 전": fg.get("previous_1_week") and round(float(fg["previous_1_week"]), 1),
            "1개월 전": fg.get("previous_1_month") and round(float(fg["previous_1_month"]), 1),
        }

    vol = {}
    signals = {}
    for name, ticker, interpret in (("VIX", "^VIX", risk.interpret_vix),
                                    ("MOVE", "^MOVE", risk.interpret_move)):
        df = dfetch.fetch_index_history(ticker, period="1y")
        if df.empty:
            continue
        last, prev = _last_two(df["Close"])
        if last is None:
            continue
        vol[name] = {"현재": round(last, 2), "전일대비": round(last - prev, 2)}
        signals[name] = interpret(last).headline
    snap["변동성 지수"] = vol

    fred_key = config.get_fred_api_key()
    y = dfetch.fetch_fred_series(config.FRED_SERIES["us_10y"], fred_key)
    h = dfetch.fetch_fred_series(config.FRED_SERIES["hy_spread"], fred_key)
    rates = {}
    if not y.empty:
        rates["미 10년물 금리"] = _fred_entry(y)
    if not h.empty:
        rates["하이일드 스프레드"] = _fred_entry(h)
    snap["금리·신용"] = rates
    if not y.empty and not h.empty:
        ys = risk.interpret_10y(y["value"])
        hs = risk.interpret_hy_spread(h["value"])
        yc = (y["value"].iloc[-1] - y["value"].iloc[-6]) * 100 if len(y) >= 6 else 0
        hc = (h["value"].iloc[-1] - h["value"].iloc[-6]) * 100 if len(h) >= 6 else 0
        signals["10년물 금리"] = ys.headline
        signals["하이일드 스프레드"] = hs.headline
        signals["종합(금리+신용)"] = risk.combine(ys, hs, yc, hc).headline

    commodities = {}
    for name, ticker in config.COMMODITIES_FX.items():
        info = dfetch.fetch_latest_price(ticker)
        if info:
            commodities[name] = {"가격": round(info["price"], 2), "전일대비_%": round(info["change_pct"], 2)}
    snap["원자재·달러"] = commodities

    snap["대시보드 규칙 판단"] = signals
    return snap


@st.cache_data(ttl=BRIEFING_TTL, show_spinner=False, max_entries=8)
def _cached_briefing(snapshot_json: str, model: str, _api_key: str) -> str:
    # _api_key: 밑줄로 시작하는 인자는 streamlit이 캐시 키 해시에서 제외한다
    return gemini_client.generate(PROMPT.format(data=snapshot_json), _api_key, model, system=SYSTEM)


def get_briefing(api_key: str, model: str = "") -> str:
    now = time.time()
    if _last["text"] and now - _last["at"] < MIN_CALL_INTERVAL:
        return _last["text"]
    if now < _fail["until"]:
        if _last["text"]:
            return _last["text"]
        raise gemini_client.GeminiError(_fail["msg"])
    snapshot = json.dumps(build_snapshot(), ensure_ascii=False, sort_keys=True)
    try:
        text = _cached_briefing(snapshot, model, api_key)
    except gemini_client.GeminiError as e:
        _fail.update(until=now + FAIL_BACKOFF, msg=str(e))
        if _last["text"]:
            return _last["text"]
        raise
    # streamlit 마크다운은 $...$를 수식으로 렌더링한다
    _last.update(at=now, text=text.replace("$", "\\$"))
    return _last["text"]
