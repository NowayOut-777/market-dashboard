"""3대 지수 200일선 알림 — GitHub Actions에서 매일 미국 장 마감 후 실행.

알림 조건 (지수별, 당일 1회 — 전일 대비 상태 변화로만 발화):
  1. 하향 돌파: 전일 종가 >= 전일 MA200 이고 당일 종가 < 당일 MA200
  2. 상향 돌파: 전일 종가 <= 전일 MA200 이고 당일 종가 > 당일 MA200
  3. 근접 진입: 이격률이 ±BAND_PCT% 밖 → 안으로 진입

발송 수단 (환경변수로 선택, 우선순위 순):
  - ALERT_EMAIL_TO + RESEND_API_KEY        → Resend API (from: onboarding@resend.dev)
  - ALERT_EMAIL_TO + SMTP_USER + SMTP_PASS → Gmail SMTP (앱 비밀번호)
  - (위 둘 다 없으면) GITHUB_TOKEN          → 저장소에 이슈를 만들고 소유자를 담당자로 지정.
    GitHub가 소유자 계정 이메일로 알림 메일을 보내므로 별도 키 없이 동작한다.

기타 환경변수:
  FORCE_SEND=true  → 이벤트가 없어도 현재 상태 메일 발송 (설정 테스트용)
  DRY_RUN=1        → 메일 대신 stdout 출력 (로컬 테스트용)
"""

import html as html_lib
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gemini_client import GeminiError, generate as gemini_generate  # noqa: E402

INDICES = {
    "S&P 500": ("^GSPC", "SPY"),
    "NASDAQ 100": ("^NDX", "QQQ"),
    "Dow Jones": ("^DJI", "DIA"),
}
MA_WINDOW = 200
BAND_PCT = 1.0
ALERT_LABEL = "ma200-alert"

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


def display_name(r: dict) -> str:
    primary = INDICES[r["name"]][0]
    return r["name"] if r["source"] == primary else f"{r['name']} ({r['source']} 대체)"


AI_SYSTEM = """너는 미국 증시 지표를 한국 개인투자자에게 쉽게 설명하는 시장 해설가다.
주어진 JSON 숫자만 근거로 쓰고, 데이터에 없는 뉴스·원인·전망은 지어내지 않는다.
매수/매도 추천, 목표가, 가격 예측은 하지 않는다. 한국어 존댓말(~입니다)로 쓴다."""

AI_PROMPT = """3대 지수의 200일 이동평균선 알림 데이터입니다 (이격률 = 종가가 200일선보다 몇 % 위/아래인지).

{data}

다음 내용을 3~4문장의 한 단락으로 써 주세요. 머리말, 목록, 제목 없이 본문만 씁니다.
1) 이벤트가 있다면 무엇이 일어났는지, 없다면 현재 위치가 어떤지
2) 200일선이 시장에서 보통 어떤 의미로 받아들여지는지 한 문장
3) 다음 며칠간 확인하면 좋은 점 (예: 돌파 후 며칠 유지되는지)"""


def ai_commentary(results: list) -> str:
    """GEMINI_API_KEY가 있으면 AI 해설 한 단락을 만든다. 없거나 실패하면 빈 문자열."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return ""
    data = [
        {"지수": display_name(r), "종가": round(r["close"], 2), "200일선": round(r["ma200"], 2),
         "이격률_%": round(r["gap_pct"], 2), "기준일": str(r["as_of"]),
         "이벤트": [e.split(" ", 1)[1] for e in r["events"]] or "없음"}
        for r in results
    ]
    try:
        return gemini_generate(
            AI_PROMPT.format(data=json.dumps(data, ensure_ascii=False, indent=1)),
            api_key, os.getenv("GEMINI_MODEL", ""), system=AI_SYSTEM,
        )
    except GeminiError as e:
        print(f"::warning::AI 해설 생략 — {e}")
        return ""


def commentary_html(text: str) -> str:
    if not text:
        return ""
    body = html_lib.escape(text)
    body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body).replace("\n", "<br>")
    return (
        "<div style='margin-top:16px;padding:12px 14px;background:#f3f5f8;border-radius:10px'>"
        "<div style='font-weight:600;margin-bottom:6px'>🤖 AI 해설 (Gemini)</div>"
        f"<div style='color:#2b3140;line-height:1.6'>{body}</div>"
        "<div style='color:#6b7280;font-size:12px;margin-top:6px'>AI가 생성한 해설로 틀릴 수 있으며 투자 권유가 아닙니다.</div>"
        "</div>"
    )


def build_email(results: list, triggered: list, commentary: str = "") -> tuple:
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
            f"<td style='padding:8px 12px;border-bottom:1px solid #e5e8ee'><b>{display_name(r)}</b></td>"
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
      {commentary_html(commentary)}
      <p style="color:#6b7280;font-size:13px">
        돌파/±{BAND_PCT:.0f}% 진입 시에만 발송됩니다 · 정보 제공용, 투자 권유 아님<br>
        대시보드: https://market-dashboard-ver1.streamlit.app
      </p>
    </div>
    """
    return subject, html


def build_markdown(results: list, commentary: str = "") -> str:
    as_of = results[0]["as_of"] if results else ""
    lines = [
        f"### 📊 3대 지수 200일선 체크 (기준일 {as_of})",
        "",
        "| 지수 | 종가 | MA200 | 이격률 | 이벤트 |",
        "|---|---:|---:|---:|---|",
    ]
    for r in results:
        ev = "<br>".join(r["events"]) if r["events"] else "—"
        lines.append(
            f"| **{display_name(r)}** | {r['close']:,.2f} | {r['ma200']:,.2f} "
            f"| {r['gap_pct']:+.2f}% | {ev} |"
        )
    if commentary:
        lines += [
            "",
            "#### 🤖 AI 해설 (Gemini)",
            # GitHub 마크다운도 $...$를 수식으로 렌더링한다
            commentary.replace("$", "\\$"),
            "",
            "_AI가 생성한 해설로 틀릴 수 있으며 투자 권유가 아닙니다._",
        ]
    lines += [
        "",
        f"돌파/±{BAND_PCT:.0f}% 진입 시에만 발송됩니다 · 정보 제공용, 투자 권유 아님",
        "대시보드: https://market-dashboard-ver1.streamlit.app",
    ]
    return "\n".join(lines)


def create_github_issue(title: str, body: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "") or repo.split("/")[0]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api = f"https://api.github.com/repos/{repo}"
    try:
        # 라벨이 이미 있으면 422 — 무시해도 된다
        requests.post(
            f"{api}/labels", headers=headers, timeout=20,
            json={"name": ALERT_LABEL, "color": "d12d3a", "description": "200일선 알림"},
        )
    except requests.RequestException as e:
        print(f"::warning::라벨 생성 건너뜀: {e}")
    try:
        r = requests.post(
            f"{api}/issues", headers=headers, timeout=20,
            json={
                "title": title,
                # 소유자 알림 메일은 이 @멘션으로 발생한다 (실측: 알림 사유 reason=mention)
                "body": f"{body}\n\ncc @{owner}",
                "assignees": [owner],
                "labels": [ALERT_LABEL],
            },
        )
    except requests.RequestException as e:
        print(f"::error::GitHub 이슈 생성 실패: {e}")
        sys.exit(1)
    if r.status_code >= 300:
        print(f"::error::GitHub 이슈 생성 실패 ({r.status_code}): {r.text}")
        sys.exit(1)
    print(f"GitHub 이슈 알림 발송 완료 → {r.json().get('html_url')} "
          f"(@{owner} 멘션 — GitHub 알림 메일로 전달, 수 분 지연 가능)")


def write_step_summary(markdown: str) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def send_alert(results: list, triggered: list) -> None:
    commentary = ai_commentary(results)
    subject, html = build_email(results, triggered, commentary)
    markdown = build_markdown(results, commentary)

    if DRY_RUN:
        print("=== DRY RUN — 알림 내용 ===")
        print("Subject:", subject)
        print(markdown)
        return

    write_step_summary(markdown)

    to_addr = os.getenv("ALERT_EMAIL_TO", "")
    has_email_sender = bool(os.getenv("RESEND_API_KEY")) or bool(
        os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))

    if to_addr and has_email_sender:
        send_email(subject, html, to_addr)
    elif os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPOSITORY"):
        create_github_issue(subject, markdown)
    else:
        print("::error::발송 수단이 없습니다. GitHub Actions에서 실행하거나 "
              "ALERT_EMAIL_TO + RESEND_API_KEY(또는 SMTP_USER/SMTP_PASS)를 설정하세요.")
        sys.exit(1)


def send_email(subject: str, html: str, to_addr: str) -> None:
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
        send_alert(results, triggered)
    else:
        print("모든 지수가 200일선에서 충분히 떨어져 있습니다 — 메일 없음.")


if __name__ == "__main__":
    main()
