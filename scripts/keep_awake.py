"""Streamlit Community Cloud 앱이 잠들지 않도록 헤드리스 브라우저로 방문한다.

Community Cloud는 한동안 방문이 없으면 앱을 재운다. 단순 HTTP 요청은 방문으로 치지 않으므로
(웹소켓 세션이 열려야 함) 실제 브라우저로 페이지를 열고, 잠들어 있으면 깨우기 버튼을 누른다.
"""

import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = os.getenv("APP_URL", "https://market-dashboard-ver1.streamlit.app/")
APP_MARKER = "미국 시장 대시보드"
WAKE_BUTTON = re.compile(r"get this app back up", re.I)


def app_rendered(page, timeout_s: int) -> bool:
    # 앱 본체는 같은 도메인의 iframe(/~/+/) 안에 그려지므로 모든 프레임을 확인한다
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for frame in page.frames:
            try:
                if APP_MARKER in frame.inner_text("body", timeout=2000):
                    return True
            except Exception:
                pass
        time.sleep(3)
    return False


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=90_000)
        time.sleep(5)

        woke = False
        button = page.get_by_role("button", name=WAKE_BUTTON)
        if button.count():
            print("앱이 잠들어 있음 → 깨우는 중")
            button.first.click()
            woke = True

        ok = app_rendered(page, 300 if woke else 120)
        if ok:
            # 세션이 잠시 유지돼야 방문으로 집계되고, 첫 방문자를 위해 데이터 캐시도 채워진다
            time.sleep(30)
        browser.close()

    if ok:
        print("✅ 대시보드 정상 동작 확인" + (" (방금 깨움)" if woke else " (이미 깨어 있었음)"))
    else:
        print("::error::대시보드 화면을 확인하지 못했습니다 — 앱이 다운됐거나 잠자기 화면이 바뀌었을 수 있습니다")
        sys.exit(1)


if __name__ == "__main__":
    main()
