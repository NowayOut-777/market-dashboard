from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

import config

CACHE_TTL = 3600


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


def _fetch_history_with_retry(ticker: str, period: str, retries: int = 3) -> pd.DataFrame:
    import time
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
def fetch_index_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = _fetch_history_with_retry(ticker, period)
    if df.empty and ticker in FALLBACK_TICKERS:
        df = _fetch_history_with_retry(FALLBACK_TICKERS[ticker], period)
    if df.empty:
        return df
    df = df[["Close"]].copy()
    df["MA200"] = df["Close"].rolling(window=config.MA_WINDOW).mean()
    return df


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_latest_price(ticker: str) -> Optional[dict]:
    df = _fetch_history_with_retry(ticker, "5d")
    if (df.empty or len(df) < 2) and ticker in FALLBACK_TICKERS:
        df = _fetch_history_with_retry(FALLBACK_TICKERS[ticker], "5d")
    if df.empty or len(df) < 2:
        return None
    last = df["Close"].iloc[-1]
    prev = df["Close"].iloc[-2]
    return {
        "price": float(last),
        "prev_close": float(prev),
        "change_pct": float((last / prev - 1) * 100),
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
    }


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_fear_greed() -> Optional[dict]:
    try:
        r = requests.get(CNN_URL, headers=CNN_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": str(e)}
    fg = data.get("fear_and_greed", {})
    return {
        "score": float(fg.get("score", 0)),
        "rating": fg.get("rating", "unknown"),
        "previous_close": fg.get("previous_close"),
        "previous_1_week": fg.get("previous_1_week"),
        "previous_1_month": fg.get("previous_1_month"),
        "previous_1_year": fg.get("previous_1_year"),
        "timestamp": fg.get("timestamp"),
    }


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_fred_series(series_id: str, api_key: str, days: int = 60) -> pd.DataFrame:
    if not api_key:
        return pd.DataFrame()
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": days,
    }
    try:
        r = requests.get(FRED_URL, params=params, timeout=15)
        r.raise_for_status()
        obs = r.json().get("observations", [])
    except Exception:
        return pd.DataFrame()
    if not obs:
        return pd.DataFrame()
    df = pd.DataFrame(obs)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    return df[["date", "value"]]


def now_kst_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
