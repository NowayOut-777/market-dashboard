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
            r = requests.get(CNN_URL, headers=CNN_HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            fg = data.get("fear_and_greed") if isinstance(data, dict) else None
            if not isinstance(fg, dict) or fg.get("score") is None or not fg.get("rating"):
                raise ValueError("CNN 응답 형식 불완전")
            return {
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
            r = requests.get(FRED_URL, params=params, timeout=15)
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


def now_kst_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Seoul")
    except Exception:
        tz = timezone(timedelta(hours=9))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M KST")
