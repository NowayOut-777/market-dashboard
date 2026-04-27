import os

INDICES = {
    "S&P 500": "^GSPC",
    "NASDAQ 100": "^NDX",
    "Dow Jones": "^DJI",
}

COMMODITIES_FX = {
    "WTI": "CL=F",
    "Brent": "BZ=F",
    "Gold (선물)": "GC=F",
    "Silver (선물)": "SI=F",
    "달러 인덱스 (DXY)": "DX-Y.NYB",
}

VOLATILITY_INDICES = {
    "VIX": "^VIX",
    "MOVE": "^MOVE",
}

SECTOR_ETFS = {
    "에너지": "XLE",
    "소재": "XLB",
    "산업재": "XLI",
    "임의소비재": "XLY",
    "필수소비재": "XLP",
    "헬스케어": "XLV",
    "금융": "XLF",
    "정보기술": "XLK",
    "커뮤니케이션 서비스": "XLC",
    "유틸리티": "XLU",
    "리츠(부동산)": "XLRE",
}

MAG7 = {
    "Apple (AAPL)": "AAPL",
    "Microsoft (MSFT)": "MSFT",
    "Alphabet (GOOGL)": "GOOGL",
    "Amazon (AMZN)": "AMZN",
    "Meta (META)": "META",
    "Tesla (TSLA)": "TSLA",
    "Nvidia (NVDA)": "NVDA",
}

SEMICONDUCTORS = {
    "SMH (필라델피아 반도체 ETF)": "SMH",
    "SOXX (iShares 반도체 ETF)": "SOXX",
    "Nvidia (NVDA)": "NVDA",
    "AMD (AMD)": "AMD",
    "TSMC (TSM)": "TSM",
    "Broadcom (AVGO)": "AVGO",
    "ASML (ASML)": "ASML",
    "Micron (MU)": "MU",
    "Intel (INTC)": "INTC",
}

SECTOR_LEADERS = {
    "정보기술 (비반도체)": {
        "Oracle (ORCL)": "ORCL",
        "Salesforce (CRM)": "CRM",
        "Adobe (ADBE)": "ADBE",
        "Cisco (CSCO)": "CSCO",
        "ServiceNow (NOW)": "NOW",
        "Intuit (INTU)": "INTU",
        "Palantir (PLTR)": "PLTR",
        "IBM (IBM)": "IBM",
        "Accenture (ACN)": "ACN",
        "Uber (UBER)": "UBER",
    },
    "임의소비재": {
        "McDonald's (MCD)": "MCD",
        "Home Depot (HD)": "HD",
        "Booking (BKNG)": "BKNG",
        "Nike (NKE)": "NKE",
        "Starbucks (SBUX)": "SBUX",
        "TJX (TJX)": "TJX",
        "Royal Caribbean (RCL)": "RCL",
    },
    "필수소비재": {
        "Walmart (WMT)": "WMT",
        "Costco (COST)": "COST",
        "P&G (PG)": "PG",
        "Coca-Cola (KO)": "KO",
        "PepsiCo (PEP)": "PEP",
        "Philip Morris (PM)": "PM",
        "Colgate (CL)": "CL",
    },
    "커뮤니케이션 서비스": {
        "Alphabet C (GOOG)": "GOOG",
        "Netflix (NFLX)": "NFLX",
        "Disney (DIS)": "DIS",
        "T-Mobile (TMUS)": "TMUS",
        "Verizon (VZ)": "VZ",
        "AT&T (T)": "T",
    },
    "산업재": {
        "GE Aerospace (GE)": "GE",
        "Boeing (BA)": "BA",
        "Lockheed Martin (LMT)": "LMT",
        "RTX (RTX)": "RTX",
        "Caterpillar (CAT)": "CAT",
        "Deere (DE)": "DE",
        "Honeywell (HON)": "HON",
        "Eaton (ETN)": "ETN",
        "Union Pacific (UNP)": "UNP",
        "Waste Management (WM)": "WM",
    },
    "헬스케어": {
        "Eli Lilly (LLY)": "LLY",
        "J&J (JNJ)": "JNJ",
        "UnitedHealth (UNH)": "UNH",
        "AbbVie (ABBV)": "ABBV",
        "Merck (MRK)": "MRK",
        "Pfizer (PFE)": "PFE",
        "Abbott (ABT)": "ABT",
        "Thermo Fisher (TMO)": "TMO",
        "Stryker (SYK)": "SYK",
        "Intuitive Surgical (ISRG)": "ISRG",
        "Bristol Myers (BMY)": "BMY",
        "Amgen (AMGN)": "AMGN",
    },
    "금융": {
        "Berkshire B (BRK-B)": "BRK-B",
        "JPMorgan (JPM)": "JPM",
        "Visa (V)": "V",
        "Mastercard (MA)": "MA",
        "Bank of America (BAC)": "BAC",
        "Wells Fargo (WFC)": "WFC",
        "Goldman Sachs (GS)": "GS",
        "Morgan Stanley (MS)": "MS",
        "Citigroup (C)": "C",
        "Amex (AXP)": "AXP",
        "BlackRock (BLK)": "BLK",
        "S&P Global (SPGI)": "SPGI",
    },
    "에너지": {
        "ExxonMobil (XOM)": "XOM",
        "Chevron (CVX)": "CVX",
        "ConocoPhillips (COP)": "COP",
        "EOG Resources (EOG)": "EOG",
    },
    "소재": {
        "Linde (LIN)": "LIN",
        "Sherwin-Williams (SHW)": "SHW",
        "Ecolab (ECL)": "ECL",
        "Air Products (APD)": "APD",
    },
    "유틸리티": {
        "NextEra (NEE)": "NEE",
        "Southern (SO)": "SO",
        "Dominion (D)": "D",
    },
    "리츠 (부동산)": {
        "American Tower (AMT)": "AMT",
        "Crown Castle (CCI)": "CCI",
        "Realty Income (O)": "O",
    },
}

VIX_LEVELS = {
    "safe": 15.0,
    "warning": 20.0,
    "danger": 30.0,
}

MOVE_LEVELS = {
    "safe": 80.0,
    "warning": 110.0,
    "danger": 140.0,
}

FRED_SERIES = {
    "us_10y": "DGS10",
    "hy_spread": "BAMLH0A0HYM2",
}

MA_WINDOW = 200

HY_SPREAD_LEVELS = {
    "safe": 3.5,
    "warning": 5.0,
    "danger": 7.0,
}

YIELD_5D_BP_THRESHOLD = 30
HY_SPREAD_5D_BP_THRESHOLD = 50


def get_fred_api_key() -> str:
    key = os.getenv("FRED_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("FRED_API_KEY", "")
    except Exception:
        return ""


def get_app_password() -> str:
    pw = os.getenv("APP_PASSWORD", "")
    if pw:
        return pw
    try:
        import streamlit as st
        return st.secrets.get("APP_PASSWORD", "")
    except Exception:
        return ""
