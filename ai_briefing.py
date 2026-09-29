"""대시보드 상단 'AI 시장 브리핑' — 페이지에 이미 불러온 지표를 모아 Gemini에게 요약시킨다."""

import json
import threading
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
# 연속 선물의 하루 등락이 이보다 크면 월물 교체 영향일 수 있다 (대시보드 안내와 같은 기준)
FUTURES_ROLL_ALERT_PCT = 5.0
# 일시 장애 때 이전 요약을 대신 보여주는 최대 기간 — 이보다 오래된 요약은 현재 지표와 어긋날 수 있다
STALE_MAX = 3 * 3600

SYSTEM = """너는 미국 증시 지표를 한국 개인투자자에게 쉽게 설명하는 시장 해설가다.
규칙:
- 주어진 JSON 데이터의 숫자만 근거로 쓴다. 데이터에 없는 뉴스, 사건, 원인, 전망은 지어내지 않는다.
- 매수/매도 추천, 목표가, 향후 가격 예측을 하지 않는다.
- '대시보드 규칙 판단'과 모순되는 평가를 하지 않는다.
- '주의' 항목이 붙은 수치는 실제 시장 움직임으로 단정하지 말고, 언급한다면 그 주의 내용을 함께 밝힌다.
- 한국어 존댓말 평서문(~입니다)으로 쓰고, 전문용어는 처음 나올 때 짧게 풀어쓴다.
- 과장이나 감탄 없이 담담하고 간결하게, 매번 같은 형식으로 쓴다."""

PROMPT = """아래는 오늘 대시보드 지표 스냅샷(JSON)입니다.

{data}

아래 형식의 마크다운으로만 답하세요. 인사말이나 머리말은 쓰지 마세요.

**한 줄 요약:** (지금 시장 분위기를 한 문장으로)

- **주식:** (3대 지수의 200일선 대비 위치, 공포탐욕지수와 눈에 띄는 구성지표, 섹터 흐름)
- **위험 신호:** (VIX, MOVE, 하이일드 스프레드, 10년물 금리 중 눈여겨볼 점)
- **경기:** (장단기 금리차, 삼의 법칙, 물가·고용이 말해주는 경기 사이클)
- **원자재·환율:** (유가·금·달러·원/달러 환율의 눈에 띄는 움직임)
- **지켜볼 포인트:** ('경계선에 가까운 지표' 목록의 앞쪽 1~2개를 수치와 함께. 이미 안전한 판단을 반복하지 말 것)

각 항목은 1~2문장, 전체 600자 이내로 쓰세요."""

_fail = {"until": 0.0, "msg": "", "transient": True}
_last = {"at": 0.0, "text": ""}
_lock = threading.Lock()


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
            entry = {"가격": round(info["price"], 2), "전일대비_%": round(info["change_pct"], 2)}
            if ticker.endswith("=F") and abs(info["change_pct"]) >= FUTURES_ROLL_ALERT_PCT:
                # 연속 선물은 만기 월물 교체 때 가격이 점프한다 — AI가 실제 급등락으로 해석하지 않게 알린다
                entry["주의"] = "선물 월물 교체(롤오버) 영향일 수 있어 실제 시장 움직임보다 과장됐을 수 있음"
            commodities[name] = entry
    snap["원자재·달러·환율"] = commodities

    m = dfetch.fetch_macro(fred_key)
    macro = {}
    for key, label in (("t10y2y", "장단기 금리차 10Y-2Y(%p)"), ("t10y3m", "장단기 금리차 10Y-3M(%p)"),
                       ("fed_funds", "실효 연방기금금리 EFFR(%)"), ("unemployment", "실업률(%)"),
                       ("sahm", "삼의 법칙(%p, 0.5 이상이면 침체 신호)")):
        if not m[key].empty:
            macro[label] = round(float(m[key]["value"].iloc[-1]), 2)
    if not m["fed_upper"].empty and not m["fed_lower"].empty:
        macro["연준 기준금리 목표 범위(%)"] = (
            f"{float(m['fed_lower']['value'].iloc[-1]):.2f}-{float(m['fed_upper']['value'].iloc[-1]):.2f}")
    yoy = dfetch.cpi_yoy(m["cpi"])
    if not yoy.empty:
        macro["CPI 전년비(%, 헤드라인)"] = round(float(yoy.iloc[-1]), 2)
        macro["CPI 기준월"] = yoy.index[-1].strftime("%Y-%m")
    snap["경기·금리곡선"] = macro
    if not m["t10y2y"].empty and not m["t10y3m"].empty and not m["sahm"].empty:
        cs = risk.interpret_yield_curve(m["t10y2y"]["value"], m["t10y3m"]["value"])
        ss = risk.interpret_sahm(m["sahm"]["value"])
        signals["장단기 금리차"] = cs.headline
        signals["삼의 법칙"] = ss.headline
        signals["경기 사이클"] = risk.combine_cycle(cs, ss).headline

    sectors = dfetch.sector_returns((("1개월", 21),))
    if not sectors.empty:
        ranked = sectors.sort_values("1개월", ascending=False)
        # 받아진 섹터가 적어도 상위·하위 목록이 겹치지 않게 하고, 하위는 가장 부진한 것부터
        k = min(3, len(ranked) // 2)
        fmt = lambda r: f"{r['섹터']}({r['티커']}) {r['1개월']:+.1f}%"
        entry = {
            "1개월 상위": [fmt(r) for _, r in ranked.head(k).iterrows()],
            "1개월 하위(부진한 순)": [fmt(r) for _, r in ranked.tail(k).iloc[::-1].iterrows()],
        }
        if "200일선 대비" in sectors:
            valid = sectors["200일선 대비"].dropna()
            entry["200일선 위 섹터 수"] = f"{int((valid > 0).sum())}/{len(valid)}"
        missing = sectors.attrs.get("missing", [])
        if missing:
            entry["데이터 누락 섹터"] = missing
        snap[f"섹터(SPDR ETF {len(sectors)}개, 배당 조정)"] = entry

    if fg and "error" not in fg and fg.get("components"):
        snap["공포탐욕 구성지표(0~100)"] = {
            config.FEAR_GREED_COMPONENTS[k]: round(v["score"]) for k, v in fg["components"].items()
            if k in config.FEAR_GREED_COMPONENTS
        }

    snap["대시보드 규칙 판단"] = signals
    snap["경계선에 가까운 지표(가까운 순)"] = _watch_points(snap, y, h, m)
    return snap


def _next_threshold(value: float, levels) -> tuple:
    """value 위쪽으로 가장 가까운 경계값과 그 거리. 모든 경계를 넘었으면 (None, None)."""
    for lv in levels:
        if value < lv:
            return lv, lv - value
    return None, None


def _watch_points(snap: dict, y: pd.DataFrame, h: pd.DataFrame, m: dict, limit: int = 4) -> list:
    # (상대 거리, 설명) — 상대 거리 = 경계까지 남은 폭 / 지표별 '의미 있는 변동폭'.
    # 이미 위험 경계를 넘은 지표는 거리 0으로 맨 앞에 둔다.
    cands = []
    for name, e in snap.get("3대 지수", {}).items():
        gap = e.get("200일선대비_%")
        if gap is not None:
            text = (f"{name}: 200일선 대비 {gap:+.2f}% — 0%가 되면 200일선 하향 이탈" if gap > 0
                    else f"{name}: 200일선 아래 {gap:+.2f}% — 0%를 넘으면 200일선 회복")
            cands.append((abs(gap) / 5, text))
    vol = snap.get("변동성 지수", {})
    for name, levels, scale in (("VIX", (15, 20, 30, 40), 5), ("MOVE", (80, 110, 140), 20)):
        if name in vol:
            cur = vol[name]["현재"]
            lv, dist = _next_threshold(cur, levels)
            if lv is None:
                cands.append((0, f"{name}: {cur:.2f} — 이미 최고 경계선 {levels[-1]} 초과 (극심한 스트레스)"))
            else:
                cands.append((dist / scale, f"{name}: {cur:.2f} — 다음 경계선 {lv}까지 {dist:.1f}"))
    if not h.empty:
        v = float(h["value"].iloc[-1])
        lv, dist = _next_threshold(v, (3.5, 5.0, 7.0))
        if lv is None:
            cands.append((0, f"하이일드 스프레드: {v:.2f}% — 이미 위험 경계 7% 초과"))
        else:
            cands.append((dist / 0.75, f"하이일드 스프레드: {v:.2f}% — 다음 경계선 {lv}%까지 {dist:.2f}%p"))
    if len(y) >= 6:
        change = (float(y["value"].iloc[-1]) - float(y["value"].iloc[-6])) * 100
        if abs(change) >= 30:
            cands.append((0, f"10년물 금리: 5일 변동 {change:+.0f}bp — 이미 ±30bp 급변 기준 초과"))
        else:
            cands.append(((30 - abs(change)) / 15, f"10년물 금리: 5일 변동 {change:+.0f}bp — ±30bp를 넘으면 급변 신호"))
    for key, label in (("t10y2y", "10Y-2Y 금리차"), ("t10y3m", "10Y-3M 금리차")):
        if not m[key].empty:
            v = float(m[key]["value"].iloc[-1])
            text = (f"{label}: {v:+.2f}%p — 0 아래로 내려가면 역전" if v >= 0
                    else f"{label}: {v:+.2f}%p — 이미 역전 상태, 0 위로 올라오면 역전 해소(과거 침체 시작 시점과 자주 겹침)")
            cands.append((abs(v) / 0.5, text))
    if not m["sahm"].empty:
        v = float(m["sahm"]["value"].iloc[-1])
        if v >= 0.5:
            cands.append((0, f"삼의 법칙: {v:+.2f}%p — 이미 침체 신호(0.5%p) 발동 상태"))
        else:
            cands.append(((0.5 - v) / 0.25, f"삼의 법칙: {v:+.2f}%p — 0.5%p에 닿으면 침체 신호"))
    fg = snap.get("CNN 공포탐욕지수(0~100)")
    if fg:
        score = fg["현재"]
        nearest = min((25, 45, 55, 75), key=lambda b: abs(score - b))
        cands.append((abs(score - nearest) / 10, f"공포탐욕지수: {score:.1f} — 구간 경계 {nearest}까지 {abs(score - nearest):.1f}"))
    cands.sort(key=lambda c: c[0])
    return [text for _, text in cands[:limit]]


@st.cache_data(ttl=BRIEFING_TTL, show_spinner=False, max_entries=8)
def _cached_briefing(snapshot_json: str, model: str, _api_key: str) -> str:
    # _api_key: 밑줄로 시작하는 인자는 streamlit이 캐시 키 해시에서 제외한다
    return gemini_client.generate(PROMPT.format(data=snapshot_json), _api_key, model, system=SYSTEM)


def escape_markdown(text: str) -> str:
    # streamlit/GitHub 마크다운은 $...$를 수식으로, ~...~를 취소선으로 렌더링한다 ('1~2일' 등)
    return text.replace("$", "\\$").replace("~", "\\~")


def _result(stale: bool) -> dict:
    return {"text": _last["text"], "at": _last["at"], "stale": stale}


def get_briefing(api_key: str, model: str = "") -> dict:
    """{"text": 요약, "at": 생성 시각(epoch), "stale": 최신 생성에 실패해 이전 요약을 보여주는지}"""
    # 여러 방문자가 동시에 열어도 Gemini 호출은 한 번만 나가도록 직렬화한다
    with _lock:
        now = time.time()
        has_recent = bool(_last["text"]) and now - _last["at"] < STALE_MAX
        if _last["text"] and now - _last["at"] < MIN_CALL_INTERVAL:
            return _result(stale=False)
        if now < _fail["until"]:
            if _fail["transient"] and has_recent:
                return _result(stale=True)
            raise gemini_client.GeminiError(_fail["msg"], transient=_fail["transient"])

        snap = build_snapshot()
        if not snap.get("3대 지수"):
            # 지표를 못 불러온 상태로 요약하면 틀린 내용이 좋은 요약을 덮어쓴다
            if has_recent:
                return _result(stale=True)
            raise gemini_client.GeminiError("지표를 아직 불러오지 못해 요약을 건너뜁니다", transient=True)

        try:
            text = _cached_briefing(json.dumps(snap, ensure_ascii=False, sort_keys=True), model, api_key)
        except gemini_client.GeminiError as e:
            _fail.update(until=now + FAIL_BACKOFF, msg=str(e), transient=e.transient)
            # 키·권한 문제는 옛 요약 뒤에 숨기지 않고 드러낸다
            if e.transient and has_recent:
                return _result(stale=True)
            raise
        _last.update(at=now, text=escape_markdown(text))
        return _result(stale=False)
