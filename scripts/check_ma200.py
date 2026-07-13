"""3대 지수 200일선 알림 — GitHub Actions에서 매일 미국 장 마감 후 실행.

알림 조건 (지수별, 당일 1회 — 전일 대비 상태 변화로만 발화):
  1. 하향 돌파: 전일 종가 >= 전일 MA200 이고 당일 종가 < 당일 MA200
  2. 상향 돌파: 전일 종가 <= 전일 MA200 이고 당일 종가 > 당일 MA200
  3. 근접 진입: 이격률이 ±BAND_PCT% 밖 → 안으로 진입

발송 수단 (환경변수로 선택, 우선순위 순):
  - RESEND_API_KEY            → Resend API (from: onboarding@resend.dev)
  - SMTP_USER + SMTP_PASS     → Gmail SMTP (앱 비밀번호)
수신자: ALERT_EMAIL_TO (Resend 무료 플랜은 가입 이메일로만 발송 가능)

기타 환경변수:
  FORCE_SEND=true  → 이벤트가 없어도 현재 상태 메일 발송 (설정 테스트용)
  DRY_RUN=1        → 메일 대신 stdout 출력 (로컬 테스트용)
"""

import os
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
import yfinance as yf

INDICES = {
    "S&P 500": ("^GSPC", "SPY"),
    "NASDAQ 100": ("^NDX", "QQQ"),
    "Dow Jones": ("^DJI", "DIA"),
}
MA_WINDOW = 200
BAND_PCT = 1.0

DRY_RUN = os.getenv("DRY_RUN", "") == "1"
FORCE_SEND = os.getenv("FORCE_SEND", "").lower() == "true"


def us_eastern_today():
    # 미 동부 날짜 (DST 정확도를 위해 zoneinfo 우선, 실패 시 UTC-5 근사)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def fetch_close_series(primary: str, fallback: str):
    for ticker in (primary, fallback):
        for attempt in range(3):
            try:
                df = yf.Ticker(ticker).history(period="2y", auto_adjust=False)
                closes = df["Close"].dropna()
                if len(closes) >= MA_WINDOW + 2:
                    return closes, ticker
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    return None, None


def analyze(name: str, closes: pd.Series, source: str) -> dict:
    ma = closes.rolling(MA_WINDOW).mean()
    c_now = float(closes.iloc[-1])
    c_prev = float(closes.iloc[-2])
    m_now = float(ma.iloc[-1])
    m_prev = float(ma.iloc[-2])
    gap_now = (c_now / m_now - 1) * 100
    gap_prev = (c_prev / m_prev - 1) * 100

    events = []
    if c_prev >= m_prev and c_now < m_now:
        events.append("🔴 200일선 하향 돌파")
    if c_prev <= m_prev and c_now > m_now:
        events.append("🟢 200일선 상향 돌파")
    if abs(gap_now) <= BAND_PCT and abs(gap_prev) > BAND_PCT:
        events.append(f"🟡 200일선 ±{BAND_PCT:.0f}% 근접 진입")

    return {
        "name": name,
        "source": source,
        "close": c_now,
        "ma200": m_now,
        "gap_pct": gap_now,
        "as_of": closes.index[-1].date(),
        "events": events,
    }


def build_email(results: list, triggered: list) -> tuple:
    if triggered:
        headline = " / ".join(
            f"{r['name']}: {', '.join(e.split(' ', 1)[1] for e in r['events'])}"
            for r in triggered
        )
        subject = f"[시장 알림] {headline}"
    else:
        subject = "[시장 알림] 테스트 — 3대 지수 200일선 현황"

    rows = []
    for r in results:
        ev = "<br>".join(r["events"]) if r["events"] else "—"
        rows.append(
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee'><b>{r['name']}</b></td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee;text-align:right'>{r['close']:,.2f}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee;text-align:right'>{r['ma200']:,.2f}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee;text-align:right'>{r['gap_pct']:+.2f}%</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee'>{ev}</td>"
            f"</tr>"
        )
    as_of = results[0]["as_of"] if results else ""
    html = f"""
    <div style="font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;max-width:640px">
      <h2 style="color:#0e131c">📊 3대 지수 200일선 체크 <span style="font-size:14px;color:#6b7280">(기준일 {as_of})</span></h2>
      <table style="border-collapse:collapse;width:100%">
        <tr style="background:#f3f5f8">
          <th style="padding:8px 12px;text-align:left">지수</th>
          <th style="padding:8px 12px;text-align:right">종가</th>
          <th style="padding:8px 12px;text-align:right">MA200</th>
          <th style="padding:8px 12px;text-align:right">이격률</th>
          <th style="padding:8px 12px;text-align:left">이벤트</th>
        </tr>
        {''.join(rows)}
      </table>
      <p style="color:#6b7280;font-size:13px">
        돌파/±{BAND_PCT:.0f}% 진입 시에만 발송됩니다 · 정보 제공용, 투자 권유 아님<br>
        대시보드: https://market-dashboard-ver1.streamlit.app
      </p>
    </div>
    """
    return subject, html


def send_email(subject: str, html: str) -> None:
    to_addr = os.getenv("ALERT_EMAIL_TO", "")

    if DRY_RUN:
        print("=== DRY RUN — 메일 내용 ===")
        print("Subject:", subject)
        print(html)
        return

    if not to_addr:
        print("::error::ALERT_EMAIL_TO 시크릿이 설정되지 않았습니다.")
        sys.exit(1)

    resend_key = os.getenv("RESEND_API_KEY", "")
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if resend_key:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}"},
            json={
                "from": "Market Alert <onboarding@resend.dev>",
                "to": [to_addr],
                "subject": subject,
                "html": html,
            },
            timeout=20,
        )
        if r.status_code >= 300:
            print(f"::error::Resend 발송 실패 ({r.status_code}): {r.text}")
            sys.exit(1)
        print(f"Resend로 발송 완료 → {to_addr}")
    elif smtp_user and smtp_pass:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_addr
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_addr], msg.as_string())
        print(f"Gmail SMTP로 발송 완료 → {to_addr}")
    else:
        print("::error::발송 수단이 없습니다. RESEND_API_KEY 또는 SMTP_USER/SMTP_PASS 시크릿을 등록하세요.")
        sys.exit(1)


def main() -> None:
    results = []
    failed = []
    for name, (primary, fallback) in INDICES.items():
        closes, source = fetch_close_series(primary, fallback)
        if closes is None:
            failed.append(name)
            continue
        results.append(analyze(name, closes, source))

    if failed:
        print(f"::warning::데이터 조회 실패: {', '.join(failed)}")
    if not results:
        print("::error::모든 지수 조회 실패 — 알림을 판단할 수 없습니다.")
        sys.exit(1)

    for r in results:
        ev = ", ".join(r["events"]) if r["events"] else "이벤트 없음"
        print(f"{r['name']} ({r['source']}): close={r['close']:,.2f} "
              f"MA200={r['ma200']:,.2f} gap={r['gap_pct']:+.2f}% as_of={r['as_of']} → {ev}")

    # 휴장일/미갱신 데이터로 어제 이벤트가 재발송되는 것을 방지
    fresh = all(r["as_of"] >= us_eastern_today() - timedelta(days=1) for r in results)
    if not fresh and not (FORCE_SEND or DRY_RUN):
        print("데이터가 최신이 아닙니다 (휴장일 추정) — 알림 판단 생략.")
        return

    triggered = [r for r in results if r["events"]]
    if triggered or FORCE_SEND:
        subject, html = build_email(results, triggered)
        send_email(subject, html)
    else:
        print("모든 지수가 200일선에서 충분히 떨어져 있습니다 — 메일 없음.")


if __name__ == "__main__":
    main()
