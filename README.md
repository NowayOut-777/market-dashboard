# 미국 시장 대시보드

매일 갱신되는 미국 시장 모니터링 Streamlit 대시보드.

## 화면 구성
1. 미국 3대 지수 (S&P 500 / NASDAQ 100 / Dow Jones) — 전일 종가 + 200일 이동평균
2. CNN 공포탐욕지수
3. 변동성 지수: VIX (S&P 500 옵션 IV) · MOVE (미 국채 옵션 IV)
4. 채권/원자재: 10년물 금리 · HY 스프레드 · WTI · Brent · 금(선물) · 은(선물)
5. 시장 위험 해석 (10Y · HY 스프레드 · VIX · MOVE 결합 신호)
6. 섹터·종목 트래커 (14개 탭): 섹터 ETF · M7 · 반도체 · GICS 11개 섹터별 대형주

다크/라이트 토글 지원, KBH 360 디자인 토큰 적용.

## 데이터 소스
- 지수·원자재·종목: yfinance (Yahoo Finance)
- 10Y 금리·HY 스프레드: FRED (`DGS10`, `BAMLH0A0HYM2`)
- 공포탐욕지수: CNN 공개 JSON

---

## 🖥️ 로컬 실행

### 1. FRED API 키 발급
1. https://fredaccount.stlouisfed.org/apikeys 가입 (무료, 1분)
2. **Request API Key** → 32자 키 복사

### 2. 시크릿 파일 작성
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```
`.streamlit/secrets.toml` 편집:
```toml
FRED_API_KEY = "발급받은_키"
APP_PASSWORD = ""
```

### 3. 의존성 설치 & 실행
```bash
pip install -r requirements.txt
streamlit run dashboard.py
```
또는 Windows에서 `run.bat` 더블클릭.

---

## 🚀 Streamlit Community Cloud 배포

배포 환경: 무료, GitHub 연동, 비밀번호 보호 가능.

### 1단계 — GitHub 저장소 생성 & 푸시

#### Option A. GitHub CLI(`gh`)로 한 번에
```bash
cd C:\Users\김민수\Desktop\Claude_test5

git init
git add .
git status                  # secrets.toml이 목록에 없는지 확인
git commit -m "initial commit: market dashboard"
git branch -M main

gh auth login               # 브라우저 인증
gh repo create market-dashboard --private --source=. --push
```

#### Option B. 웹에서 수동
1. https://github.com/new 접속
2. **Repository name** : `market-dashboard` (자유)
3. **Private** 선택 (지인용이라면)
4. README/.gitignore/license 추가하지 말 것 (이미 있음)
5. **Create repository** → 안내된 명령어 실행:
```bash
cd C:\Users\김민수\Desktop\Claude_test5
git init
git add .
git commit -m "initial commit: market dashboard"
git branch -M main
git remote add origin https://github.com/<your-id>/market-dashboard.git
git push -u origin main
```

### 2단계 — Streamlit Cloud 연결

1. https://share.streamlit.io 접속 → **Sign in with GitHub**
2. **Create app** → **Deploy a public app from GitHub**
3. 항목 입력:
   - **Repository**: `<your-id>/market-dashboard`
   - **Branch**: `main`
   - **Main file path**: `dashboard.py`
   - **App URL**: 원하는 서브도메인 (예: `kim-market.streamlit.app`)
4. **Advanced settings...** 펼치기:
   - **Python version**: `3.12` (또는 3.13)
   - **Secrets** 박스에 아래 붙여넣기:
     ```toml
     FRED_API_KEY = "발급받은_키"
     APP_PASSWORD = "지인에게_알려줄_비번"
     ```
5. **Deploy** 클릭 → 1~2분 후 URL 발급

### 3단계 — 동작 확인
- 발급받은 URL 접속
- 비밀번호 입력 화면이 뜨면 ✅
- 6개 섹션 + 14개 탭 모두 정상 렌더링되면 완료

### 4단계 — 지인에게 공유
- URL + 비밀번호만 알려주면 됨
- 비밀번호는 **App settings → Secrets** 에서 언제든 변경 가능

---

## 🔄 데이터 갱신

- 모든 fetch는 `@st.cache_data(ttl=3600)` — 1시간 캐시
- **누군가 페이지 열 때마다** 캐시 만료시 자동 갱신
- 수동 갱신: 우상단 **🔄 새로고침** 버튼 → 캐시 즉시 클리어

별도 cron/스케줄러 불필요. 사용자가 페이지 접근 = 트리거.

---

## ⚙️ 설정 변경

`config.py`에서 임계치 조정:
- `HY_SPREAD_LEVELS` — HY 스프레드 위험 구간 (3.5/5.0/7.0%)
- `VIX_LEVELS` — VIX 구간 (15/20/30)
- `MOVE_LEVELS` — MOVE 구간 (80/110/140)
- `YIELD_5D_BP_THRESHOLD` — 10Y 5일 변동 위험 기준 (30bp)
- `HY_SPREAD_5D_BP_THRESHOLD` — HY 5일 변동 위험 기준 (50bp)

종목 추가/제거: `INDICES`, `MAG7`, `SEMICONDUCTORS`, `SECTOR_LEADERS` 사전 편집.

코드 수정 후 `git push` → Streamlit Cloud가 자동으로 재배포 (약 30초).

---

## 🛑 보안 체크리스트

- [x] `.streamlit/secrets.toml`은 `.gitignore` 등록 — 절대 커밋 금지
- [x] FRED API 키 / 비밀번호는 Streamlit Cloud **Secrets** 에 입력 (저장소 X)
- [x] Public 저장소로 만들 경우 비밀번호 보호(`APP_PASSWORD`) 권장
- [ ] GitHub 저장소 push 직전 `git status` 로 secrets.toml이 안 보이는지 재확인

---

## 📂 파일 구조

```
Claude_test5/
├── dashboard.py            # 메인 Streamlit 앱
├── data_fetch.py           # yfinance / FRED / CNN 데이터 수집
├── risk_interpreter.py     # 시장 위험 해석 로직
├── config.py               # 심볼·임계치·키 로더
├── requirements.txt        # Python 의존성 (Streamlit Cloud 빌드 입력)
├── .python-version         # Python 버전 핀
├── .gitignore              # 시크릿/캐시 제외
├── .streamlit/
│   ├── config.toml         # Streamlit 테마 (라이트 기본)
│   ├── secrets.toml        # ❌ 커밋 금지 (FRED 키)
│   └── secrets.toml.example
├── run.bat                 # Windows 실행 헬퍼
└── README.md               # 본 문서
```

---

## 디스클레이머
정보 제공 목적이며 투자 권유가 아닙니다. 데이터 정확성 보장하지 않음.
