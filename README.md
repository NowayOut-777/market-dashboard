# 미국 시장 대시보드

매일 갱신되는 미국 시장 모니터링 Streamlit 대시보드.

## 화면 구성
0. 🤖 오늘의 AI 시장 브리핑 (Gemini) — 아래 지표 전체를 요약하고, 경계선에 가장 가까운 지표를 '지켜볼 포인트'로 짚음 (`GEMINI_API_KEY` 설정 시에만 표시)
1. 미국 3대 지수 (S&P 500 / NASDAQ 100 / Dow Jones) — 최근 종가 + 200일 이동평균
2. CNN 공포탐욕지수 + **구성 지표 7개** (모멘텀·주가 강도·시장 폭·풋콜·VIX·안전자산·정크본드)
3. 변동성 지수: VIX (S&P 500 옵션 IV) · MOVE (미 국채 옵션 IV)
4. 채권·원자재·환율: 10년물 금리 · HY 스프레드 · WTI · Brent · 금 · 은 · 달러 인덱스 · **원/달러 환율**
5. **경기 & 금리 곡선**: 장단기 금리차(10Y-2Y, 10Y-3M) · 연준 기준금리 · CPI 전년비 · 실업률 · 삼의 법칙 + 금리차 추이 차트
6. 시장 위험 해석: 금리·신용·변동성 신호 + **경기 사이클 판단**(장단기 금리 역전 / 삼의 법칙)
7. **섹터 히트맵 & 시장 폭**: 11개 섹터의 1일·1주·1개월·3개월 수익률과 200일선 대비, 200일선 위 섹터 수
8. 섹터·종목 트래커 (4개 탭): 섹터 ETF · M7 · 반도체 · 섹터별 대형주(GICS 11개 선택)

다크/라이트 토글 지원, KBH 360 디자인 토큰 적용.

## 데이터 소스
- 지수·원자재·종목: yfinance (Yahoo Finance)
- 금리·신용·경기: FRED (`DGS10`, `BAMLH0A0HYM2`, `T10Y2Y`, `T10Y3M`, `DFF`, `CPIAUCSL`, `UNRATE`, `SAHMREALTIME`)
- 공포탐욕지수 + 구성 지표 7개: CNN 공개 JSON

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
- 6개 섹션 + 트래커 4개 탭 모두 정상 렌더링되면 완료 (Gemini 키를 넣었다면 맨 위 AI 브리핑도)

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

## 🤖 AI 시장 브리핑 (Gemini, 선택)

[Google AI Studio](https://aistudio.google.com/apikey)에서 무료 Gemini API 키를 발급하면 두 곳에 AI 요약이 붙습니다.

| 위치 | 내용 | 키를 넣는 곳 |
|---|---|---|
| 대시보드 맨 위 | 오늘 지표를 3~4줄로 요약 (최대 15분 간격 갱신) | Streamlit Cloud **Secrets** (+ 로컬은 `.streamlit/secrets.toml`) |
| 200일선 알림 메일 | 이벤트의 의미를 한 단락으로 해설 | GitHub **Secrets** |

**등록 방법** — 키는 채팅·코드·커밋 어디에도 붙여넣지 말고 아래처럼 직접 넣으세요.

1. **Streamlit Cloud**: share.streamlit.io → 앱 ⋮ → **Settings → Secrets** 에 한 줄 추가 후 Save
   ```toml
   GEMINI_API_KEY = "발급받은_키"
   ```
2. **로컬 테스트용**: `.streamlit/secrets.toml` 에 같은 한 줄 추가 (gitignore 되어 있음)
3. **GitHub (알림 해설)**: PowerShell에서 실행 → 뜨는 입력창에 키 붙여넣기 (화면에 안 보임)
   ```powershell
   gh secret set GEMINI_API_KEY
   ```

**동작 방식**
- 키가 없으면 AI 기능만 조용히 꺼지고 나머지는 그대로 동작합니다.
- 서버 전체 기준으로 Gemini 호출을 **최대 15분에 1회**로 제한합니다 (공개 페이지라 누가 새로고침을 연타해도 하루 최대 96회 — 무료 한도 안). 그 사이엔 직전 요약을 보여줍니다.
- 한도 초과·장애 시 10분간 재호출을 멈추고, 직전 요약이 있으면 그것을, 없으면 안내 문구를 표시합니다.
- 모델은 구글이 최신 모델로 계속 교체하는 `gemini-flash-latest` → `gemini-flash-lite-latest` 별칭을 쓰고, 둘 다 안 되면 이 키로 쓸 수 있는 모델 목록에서 최신 Flash를 자동으로 찾습니다. 모델이 단종돼도 손댈 필요가 없습니다. 특정 모델로 고정하려면 `GEMINI_MODEL` 시크릿을 추가하세요.
- AI는 페이지에 있는 숫자만 근거로 요약하도록 지시되어 있으며, 매수·매도 추천이나 가격 예측은 하지 않습니다. 그래도 틀릴 수 있습니다.

---

## 📧 200일선 이메일 알림 (GitHub Actions)

매 거래일 미국 장 마감 직후(한국시간 오전 6:40경) 3대 지수를 체크해서, 아래 이벤트 발생 시에만 메일을 보냅니다:
- 🔴 200일선 **하향 돌파** / 🟢 **상향 돌파**
- 🟡 200일선 **±1% 이내 진입** (밖에서 안으로 들어올 때 1회)

이벤트가 없으면 메일이 오지 않습니다. PC가 꺼져 있어도, 대시보드를 아무도 안 열어도 동작합니다.

### 알림 받는 방법 (기본값: 설정 불필요)

**아무것도 안 해도 동작합니다.** 이벤트가 생기면 워크플로가 이 저장소에 `ma200-alert` 라벨의 이슈를 만들고 소유자를 담당자로 지정합니다. GitHub가 이를 **GitHub 계정 이메일로 알림 메일**로 보내줍니다. 필요한 권한은 워크플로 기본 토큰뿐이라 키 발급이 필요 없습니다.

- 메일이 안 오면 GitHub → **Settings → Notifications** 에서 *Participating* 과 *Watching* 의 **Email** 이 켜져 있는지 확인하세요.
- 알림 이력은 저장소 **Issues** 탭에서 `label:ma200-alert` 로 모아 볼 수 있습니다.

#### (선택) 예쁜 HTML 메일로 직접 받기

GitHub 알림 대신 표가 들어간 HTML 메일을 원하면 저장소 **Settings → Secrets and variables → Actions** 에 아래를 등록하세요. 등록되면 자동으로 이 경로가 우선합니다.

| Secret | 값 |
|---|---|
| `ALERT_EMAIL_TO` | 받을 이메일 주소 |
| `RESEND_API_KEY` | [resend.com](https://resend.com) 가입 후 API 키 (무료 플랜은 가입 이메일로만 발송) |
| 또는 `SMTP_USER` + `SMTP_PASS` | Gmail 주소 + [앱 비밀번호](https://myaccount.google.com/apppasswords) |

### 테스트

저장소 → **Actions → MA200 Alert → Run workflow** → `force_send` 체크 → 실행.
이벤트가 없어도 현재 상태 알림(이슈 또는 메일)이 오면 설정 성공. 테스트로 만들어진 이슈는 닫아도 됩니다.

### 조건 변경

`scripts/check_ma200.py` 상단의 `BAND_PCT = 1.0` (근접 기준 %) 수정 후 push.

### 운영 시 알아둘 것

- **알림 경로 확인**: Actions 실행 화면 상단 안내("알림 경로")에 현재 GitHub 이슈 알림인지 직접 메일인지 표시됩니다.
- **60일 자동 비활성화**: GitHub는 저장소에 60일간 커밋이 없으면 예약 워크플로를 끕니다. 워크플로 마지막 단계(Keepalive)가 매 실행마다 스스로를 재활성화해 이를 막습니다. 만약 Actions 탭에 "This scheduled workflow is disabled" 배너가 보이면 **Enable workflow** 를 누르거나 아무 커밋이나 push 하면 다시 켜집니다.
- **실행 시각 지연**: GitHub 예약 작업은 혼잡 시 1~2시간 늦게 돌 수 있습니다(보통 한국시간 오전 7~9시 사이). 하루 한 번만 돌면 되므로 문제 없습니다.

---

## 💤 앱 잠들지 않게 하기 (GitHub Actions)

Streamlit Community Cloud 무료 플랜은 방문이 한동안(약 12시간) 없으면 앱을 재웁니다. `.github/workflows/keep-awake.yml` 이 **6시간마다** 헤드리스 크롬으로 대시보드를 열고, 잠들어 있으면 깨우기 버튼을 눌러 줍니다. 덕분에 친구들이 언제 들어와도 "Zzzz" 화면 없이 바로 보입니다.

- 단순 주소 호출(curl)은 방문으로 집계되지 않아 실제 브라우저를 씁니다.
- 앱 화면을 확인하지 못하면 실행이 실패로 끝나고 GitHub가 실패 알림 메일을 보냅니다 — 대시보드가 다운됐다는 신호입니다.
- 수동 실행: 저장소 **Actions → Keep App Awake → Run workflow**
- 끄고 싶으면 같은 화면에서 **Disable workflow**.

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
├── gemini_client.py        # Gemini API 호출 (대시보드·알림 공용)
├── ai_briefing.py          # 대시보드 AI 브리핑 (지표 스냅샷 → 요약)
├── scripts/check_ma200.py  # 200일선 알림 (GitHub Actions에서 실행)
├── scripts/keep_awake.py   # 앱 잠들지 않게 주기적 방문
├── .github/workflows/      # 알림 스케줄
├── requirements.txt        # Python 의존성 (Streamlit Cloud 빌드 입력)
├── .python-version         # Python 버전 핀
├── .gitignore              # 시크릿/캐시 제외
├── .streamlit/
│   ├── config.toml         # Streamlit 테마 (라이트 기본)
│   ├── secrets.toml        # ❌ 커밋 금지 (FRED·Gemini 키)
│   └── secrets.toml.example
├── run.bat                 # Windows 실행 헬퍼
└── README.md               # 본 문서
```

---

## 디스클레이머
정보 제공 목적이며 투자 권유가 아닙니다. 데이터 정확성 보장하지 않음.
