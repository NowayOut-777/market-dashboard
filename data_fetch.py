import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

import config

CACHE_TTL = 3600
# 실패는 캐시하지 않는다. 대신 아래 시간 동안만 재시도를 보류해 요청 폭주를 막는다.
FAIL_RETRY_AFTER = 120

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

FALLBACK_TICKERS = {
    "^GSPC": "SPY",
    "^NDX": "QQQ",
    "^DJI": "DIA",
}


class FetchError(Exception):
    """캐시 내부에서 발생시켜 실패 결과가 1시간 캐시되는 것을 막는다."""


_fail_memo: dict = {}


def _failed_recently(key) -> bool:
    return time.time() - _fail_memo.get(key, 0) < FAIL_RETRY_AFTER


def _mark_failed(key) -> None:
    _fail_memo[key] = time.time()


def _fetch_history_with_retry(ticker: str, period: str, retries: int = 3) -> pd.DataFrame:
    for i in range(retries):
        try:
            df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
            if not df.empty:
                return df
        except Exception:
            pass
        if i < retries - 1:
            time.sleep(0.4 * (i + 1))
    return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_index_history(ticker: str, period: str):
    df = _fetch_history_with_retry(ticker, period)
    source = ticker
    if (df.empty or df["Close"].dropna().empty) and ticker in FALLBACK_TICKERS:
        source = FALLBACK_TICKERS[ticker]
        df = _fetch_history_with_retry(source, period)
    if df.empty or df["Close"].dropna().empty:
        raise FetchError(ticker)
    df = df[["Close"]].copy()
    df["MA200"] = df["Close"].rolling(window=config.MA_WINDOW).mean()
    return df, source


def fetch_index_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    key = ("hist", ticker, period)
    if _failed_recently(key):
        return pd.DataFrame()
    try:
        df, source = _cached_index_history(ticker, period)
    except FetchError:
        _mark_failed(key)
        return pd.DataFrame()
    except Exception:
        _mark_failed(key)
        return pd.DataFrame()
    df.attrs["source_ticker"] = source
    return df


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_latest_price(ticker: str) -> dict:
    df = _fetch_history_with_retry(ticker, "5d")
    source = ticker
    closes = df["Close"].dropna() if not df.empty else pd.Series(dtype=float)
    if len(closes) < 2 and ticker in FALLBACK_TICKERS:
        source = FALLBACK_TICKERS[ticker]
        df = _fetch_history_with_retry(source, "5d")
        closes = df["Close"].dropna() if not df.empty else pd.Series(dtype=float)
    if len(closes) < 2:
        raise FetchError(ticker)
    last = closes.iloc[-1]
    prev = closes.iloc[-2]
    return {
        "price": float(last),
        "prev_close": float(prev),
        "change_pct": float((last / prev - 1) * 100),
        "as_of": closes.index[-1].strftime("%Y-%m-%d"),
        "source_ticker": source,
    }


def fetch_latest_price(ticker: str) -> Optional[dict]:
    key = ("price", ticker)
    if _failed_recently(key):
        return None
    try:
        return _cached_latest_price(ticker)
    except Exception:
        _mark_failed(key)
        return None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_fear_greed() -> dict:
    last_err = "응답 없음"
    for attempt in range(3):
        try:
            r = requests.get(CNN_URL, headers=CNN_HEADERS, timeout=(3.05, 10))
            r.raise_for_status()
            data = r.json()
            fg = data.get("fear_and_greed") if isinstance(data, dict) else None
            if not isinstance(fg, dict) or fg.get("score") is None or not fg.get("rating"):
                raise ValueError("CNN 응답 형식 불완전")
            components = {}
            for comp_key in config.FEAR_GREED_COMPONENTS:
                comp = data.get(comp_key)
                if isinstance(comp, dict) and isinstance(comp.get("score"), (int, float)):
                    components[comp_key] = {
                        "score": float(comp["score"]),
                        "rating": str(comp.get("rating") or ""),
                    }
            return {
                "components": components,
                "score": float(fg["score"]),
                "rating": str(fg["rating"]),
                "previous_close": fg.get("previous_close"),
                "previous_1_week": fg.get("previous_1_week"),
                "previous_1_month": fg.get("previous_1_month"),
                "previous_1_year": fg.get("previous_1_year"),
                "timestamp": fg.get("timestamp"),
            }
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise FetchError(last_err)


def fetch_fear_greed() -> Optional[dict]:
    key = ("fear_greed",)
    if _failed_recently(key):
        return {"error": "일시적 조회 실패 — 잠시 후 자동 재시도됩니다"}
    try:
        return _cached_fear_greed()
    except Exception as e:
        _mark_failed(key)
        return {"error": str(e)}


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_fred_series(series_id: str, api_key: str, days: int) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": days,
    }
    obs = []
    last_err = ""
    for attempt in range(3):
        try:
            r = requests.get(FRED_URL, params=params, timeout=(3.05, 10))
            r.raise_for_status()
            obs = r.json().get("observations", [])
            if obs:
                break
        except Exception as e:
            last_err = str(e)
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    if not obs:
        raise FetchError(last_err or "관측치 없음")
    df = pd.DataFrame(obs)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        raise FetchError("숫자 관측치 없음")
    return df[["date", "value"]]


def fetch_fred_series(series_id: str, api_key: str, days: int = 120) -> pd.DataFrame:
    if not api_key:
        return pd.DataFrame()
    key = ("fred", series_id, days)
    if _failed_recently(key):
        return pd.DataFrame()
    try:
        return _cached_fred_series(series_id, api_key, days)
    except Exception:
        _mark_failed(key)
        return pd.DataFrame()


class PartialFetch(FetchError):
    """일부 티커만 받아진 결과 — 캐시하지 않고 잠시만 보여준 뒤 다시 시도한다."""

    def __init__(self, partial: pd.DataFrame, missing: list):
        super().__init__(f"누락: {', '.join(missing)}")
        self.partial = partial
        self.missing = missing


def _adjusted(df: pd.DataFrame) -> pd.DataFrame:
    # 배당락일마다 가짜 하락이 생기지 않게 수익률은 배당 조정 종가로 계산한다
    col = "Adj Close" if "Adj Close" in df else "Close"
    out = df[col] if col in df else pd.DataFrame()
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_multi_close(tickers: tuple, period: str) -> pd.DataFrame:
    closes = pd.DataFrame()
    try:
        # yf.download 한 번으로 묶어 부른다 (내부적으로는 티커별로 순차 요청)
        df = yf.download(list(tickers), period=period, auto_adjust=False,
                         progress=False, threads=False)
        closes = _adjusted(df)
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(tickers[0])
    except Exception:
        closes = pd.DataFrame()

    # yf.download는 일부 티커가 실패해도 예외 없이 빈 열만 남긴다 — 빠진 티커는 개별로 다시 받는다
    missing = [t for t in tickers if t not in closes or not closes[t].notna().any()]
    for t in missing:
        one = _fetch_history_with_retry(t, period)
        if not one.empty:
            series = _adjusted(one)
            series.index = series.index.tz_localize(None) if series.index.tz is not None else series.index
            closes = closes.join(series.rename(t), how="outer") if not closes.empty else series.to_frame(t)
    closes = closes.dropna(how="all")
    missing = [t for t in tickers if t not in closes or not closes[t].notna().any()]
    if closes.empty:
        raise FetchError("일괄 조회 결과 없음")
    if missing:
        raise PartialFetch(closes, missing)
    return closes


_partial_memo: dict = {}


def fetch_multi_close(tickers: tuple, period: str = "1y") -> pd.DataFrame:
    """여러 티커의 종가(배당 조정)를 열(column)=티커 형태로 돌려준다. 실패하면 빈 DataFrame.
    일부만 받아졌으면 그 부분을 돌려주되 캐시하지 않아 2분 뒤 다시 시도한다."""
    key = ("multi", tickers, period)
    if _failed_recently(key):
        return _partial_memo.get(key, pd.DataFrame())
    try:
        return _cached_multi_close(tickers, period)
    except PartialFetch as e:
        _mark_failed(key)
        _partial_memo[key] = e.partial
        return e.partial
    except Exception:
        _mark_failed(key)
        _partial_memo.pop(key, None)
        return pd.DataFrame()


def now_kst_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Seoul")
    except Exception:
        tz = timezone(timedelta(hours=9))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M KST")


def fetch_macro(fred_key: str) -> dict:
    """경기·금리 곡선 지표. 대시보드와 AI 브리핑이 같은 캐시를 공유한다.

    FRED 8개 계열을 순서대로 받으면 콜드 스타트가 수십 초로 늘어나 병렬로 받는다.
    """
    fs = config.FRED_SERIES
    # 금리차는 '최근 1년 내 역전 여부'까지 보려고 길게 받는다
    plan = {
        "t10y2y": (fs["t10y2y"], 400),
        "t10y3m": (fs["t10y3m"], 400),
        "fed_funds": (fs["fed_funds"], 120),
        "fed_upper": (fs["fed_target_upper"], 120),
        "fed_lower": (fs["fed_target_lower"], 120),
        "cpi": (fs["cpi"], 30),
        "unemployment": (fs["unemployment"], 30),
        "sahm": (fs["sahm"], 30),
    }
    try:
        from concurrent.futures import ThreadPoolExecutor
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()

        def run(item):
            name, (sid, days) = item
            if ctx is not None:
                add_script_run_ctx(threading.current_thread(), ctx)
            return name, fetch_fred_series(sid, fred_key, days=days)

        with ThreadPoolExecutor(max_workers=4) as pool:
            return dict(pool.map(run, plan.items()))
    except Exception:
        return {name: fetch_fred_series(sid, fred_key, days=days) for name, (sid, days) in plan.items()}


def cpi_yoy(cpi_df: pd.DataFrame) -> pd.Series:
    """월별 CPI 지수 → 전년 동월 대비 상승률(%) 시계열.

    발표가 빠진 달(예: 2025년 10월 셧다운)이 있어도 12개월 전과 비교하도록 날짜로 맞춘다.
    행 기준으로 12칸 밀면 빠진 달 이후로는 13개월 전과 비교하게 된다.
    """
    if cpi_df.empty:
        return pd.Series(dtype=float)
    s = cpi_df.set_index("date")["value"].asfreq("MS")
    return ((s / s.shift(12) - 1) * 100).dropna()


def value_months_ago(series: pd.Series, dates: pd.Series, months: int = 1):
    """날짜 기준으로 N개월 전(또는 그 직전) 값. 없으면 None."""
    s = pd.Series(series.values, index=pd.to_datetime(dates.values)).dropna().sort_index()
    if s.empty:
        return None
    target = s.index[-1] - pd.DateOffset(months=months)
    if target < s.index[0]:
        return None
    return float(s.asof(target))


def sector_returns(periods) -> pd.DataFrame:
    """섹터 ETF별 기간 수익률(%)과 200일선 대비(%). periods = ((라벨, 거래일 수), ...)
    받지 못한 섹터는 결과의 attrs["missing"]에 이름으로 남긴다."""
    tickers = tuple(config.SECTOR_ETFS.values())
    names = {t: n for n, t in config.SECTOR_ETFS.items()}
    closes = fetch_multi_close(tickers, period="1y")
    longest = max(n for _, n in periods)
    rows = []
    for t in tickers:
        if closes.empty or t not in closes:
            continue
        s = closes[t].dropna()
        if len(s) <= longest:
            continue
        row = {"섹터": names[t], "티커": t}
        for label, n in periods:
            row[label] = (float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1) * 100
        if len(s) >= config.MA_WINDOW:
            ma = float(s.rolling(config.MA_WINDOW).mean().iloc[-1])
            row["200일선 대비"] = (float(s.iloc[-1]) / ma - 1) * 100
        rows.append(row)
    out = pd.DataFrame(rows)
    loaded = set(out["티커"]) if not out.empty else set()
    out.attrs["missing"] = [names[t] for t in tickers if t not in loaded]
    return out


_refresh = {"ts": 0.0}
_refresh_lock = threading.Lock()


def try_global_refresh(cooldown: float) -> bool:
    """모든 방문자를 통틀어 cooldown초에 한 번만 전체 캐시 초기화를 허용한다."""
    with _refresh_lock:
        now = time.time()
        if now - _refresh["ts"] < cooldown:
            return False
        _refresh["ts"] = now
        return True
