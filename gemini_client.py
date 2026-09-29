"""Gemini(Google AI) 텍스트 생성 — 대시보드 브리핑과 200일선 알림 해설이 함께 쓴다.

streamlit에 의존하지 않으므로 GitHub Actions 스크립트에서도 그대로 import할 수 있다.
"""

import re

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# 고정 모델 ID는 몇 달 만에 단종된다(2.5 계열은 2026-09 신규 키 차단). *-latest 별칭은 구글이
# 새 모델 출시 때마다 교체하므로(프리뷰일 수도 있음) 이것을 먼저 쓰고, 둘 다 안 되면
# 이 키로 쓸 수 있는 모델 목록에서 최신 Flash 계열을 찾아 시도한다.
DEFAULT_MODELS = ("gemini-flash-latest", "gemini-flash-lite-latest")
_EXCLUDE = ("tts", "image", "audio", "live", "embedding", "native", "robotics", "computer")

_discovered: list = []


class GeminiError(Exception):
    """사용자에게 그대로 보여줘도 되는 짧은 한국어 메시지를 담는다 (키는 절대 포함하지 않음).

    transient=True면 시간이 지나면 풀리는 실패(한도, 장애, 연결)라 이전 결과를 대신 보여줘도 되고,
    False면 키·권한 문제처럼 사람이 고쳐야 하는 실패라 숨기지 말고 드러내야 한다.
    """

    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class _Retry(Exception):
    """다음 후보 모델로 넘어가도 되는 실패."""

    def __init__(self, reason: str, model_missing: bool = False):
        super().__init__(reason)
        self.model_missing = model_missing


def _error_message(r: requests.Response) -> str:
    try:
        return r.json().get("error", {}).get("message", "")[:200]
    except ValueError:
        return ""


def _extract_text(data) -> tuple:
    if not isinstance(data, dict):
        return "", False
    for cand in data.get("candidates") or []:
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if text.strip():
            return text.strip(), cand.get("finishReason") == "MAX_TOKENS"
    return "", False


def _discover_models(headers: dict, timeout: int) -> list:
    if _discovered:
        return _discovered
    try:
        r = requests.get(f"{API_BASE}/models", headers=headers,
                         params={"pageSize": 200}, timeout=timeout)
        models = r.json().get("models", []) if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        return []
    names = []
    for m in models:
        name = m.get("name", "").removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(x in name for x in _EXCLUDE):
            continue
        names.append(name)

    def rank(n: str):
        version = tuple(int(x) for x in re.findall(r"\d+", n)[:2])
        return version, "lite" not in n, "preview" not in n and "exp" not in n

    names.sort(key=rank, reverse=True)
    _discovered.extend(names[:3])
    return _discovered


def _call(model: str, headers: dict, body: dict, timeout: int) -> str:
    try:
        r = requests.post(f"{API_BASE}/models/{model}:generateContent",
                          headers=headers, json=body, timeout=timeout)
    except requests.RequestException:
        raise GeminiError("Gemini 서버에 연결하지 못했습니다", transient=True) from None

    code, msg = r.status_code, _error_message(r)
    # 구글 원문 오류에는 프로젝트 번호 등이 섞일 수 있어 공개 페이지에는 상태별 안내만 보여준다
    if code in (400, 401, 403) and "key" in msg.lower():
        raise GeminiError("Gemini API 키가 유효하지 않습니다")
    if code == 404:
        raise _Retry(f"모델 {model}을(를) 쓸 수 없습니다", model_missing=True)
    if code == 429:
        # 무료 한도는 모델별로 따로라 다른 모델은 될 수 있다
        if "perday" in r.text.lower().replace("_", ""):
            raise _Retry("오늘 무료 사용량을 다 썼습니다 — 한국시간 오후 4~5시(미 태평양 자정)에 초기화됩니다")
        raise _Retry("무료 사용량 한도에 걸렸습니다 — 잠시 후 자동으로 다시 시도합니다")
    if code in (500, 502, 503, 504):
        raise _Retry("Gemini 서버 일시 장애 — 잠시 후 자동으로 다시 시도합니다")
    if code == 402:
        raise GeminiError("Gemini 선불 크레딧이 소진되었습니다")
    if code == 403:
        raise GeminiError("Gemini API 접근이 거부되었습니다 (키 권한 확인 필요)")
    if code == 400:
        # 모델마다 지원 파라미터가 달라 400이 날 수 있다 — 다른 모델로 넘어간다
        raise _Retry("Gemini 요청 오류 (HTTP 400)")
    if code >= 300:
        raise GeminiError(f"Gemini 요청 오류 (HTTP {code})")

    try:
        text, truncated = _extract_text(r.json())
    except ValueError:
        raise GeminiError("Gemini 응답을 해석하지 못했습니다") from None
    if not text:
        raise _Retry("Gemini가 빈 응답을 돌려줬습니다")
    if truncated:
        text += "\n\n_(응답 일부가 잘렸습니다)_"
    return text


def generate(prompt: str, api_key: str, model: str = "", system: str = "",
             timeout: int = 60) -> str:
    api_key = (api_key or "").strip()
    if not api_key:
        raise GeminiError("GEMINI_API_KEY가 설정되지 않았습니다")
    # 복사할 때 섞인 공백·줄바꿈·전각/한글 문자는 헤더 인코딩에서 예외를 낸다 — 미리 막는다
    if not api_key.isascii() or any(c.isspace() for c in api_key):
        raise GeminiError("API 키에 공백이나 잘못된 문자가 섞여 있습니다 — 키를 다시 복사해 등록하세요")

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # temperature 등 샘플링 파라미터는 3.x 모델에서 폐기됨 — 넣지 않는다.
        # 사고(thinking) 토큰도 이 한도를 소모하므로 여유 있게 잡는다.
        "generationConfig": {"maxOutputTokens": 8192},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    # 키는 URL이 아니라 헤더로 보낸다 — URL은 예외 메시지나 로그에 그대로 찍힐 수 있다
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    tried: set = set()
    reason, reason_is_missing = "사용 가능한 모델이 없습니다", True

    def attempt(candidates) -> str:
        nonlocal reason, reason_is_missing
        for m in candidates:
            if m in tried:
                continue
            tried.add(m)
            try:
                return _call(m, headers, body, timeout)
            except _Retry as e:
                # '모델 없음'보다 한도·장애 사유가 사용자에게 더 유용하므로 덮어쓰지 않는다
                if reason_is_missing or not e.model_missing:
                    reason, reason_is_missing = str(e), e.model_missing
            except GeminiError:
                raise
            except Exception:
                # 호출하는 쪽(알림 발송 등)이 Gemini 때문에 멈추지 않도록 전부 GeminiError로 바꾼다
                raise GeminiError("Gemini 호출 중 예기치 못한 오류가 발생했습니다", transient=True) from None
        return ""

    if model:
        text = attempt([model])
    else:
        text = attempt(DEFAULT_MODELS) or attempt(_discover_models(headers, timeout))
    if text:
        return text
    # 모든 후보가 '모델 없음'이면 설정 문제, 그 외(한도·장애)는 시간이 지나면 풀린다
    raise GeminiError(reason, transient=not reason_is_missing)
