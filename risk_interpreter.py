from dataclasses import dataclass
from typing import Optional

import pandas as pd

import config


@dataclass
class Signal:
    level: str          # "safe" | "neutral" | "watch" | "danger"
    icon: str           # 🟢🟡🟠🔴
    headline: str
    detail: str


LEVEL_ICONS = {
    "safe": "🟢",
    "neutral": "🟡",
    "watch": "🟠",
    "danger": "🔴",
}


def _icon(level: str) -> str:
    return LEVEL_ICONS.get(level, "⚪")


def _five_day_change_bp(series: pd.Series) -> Optional[float]:
    if len(series) < 6:
        return None
    return float((series.iloc[-1] - series.iloc[-6]) * 100)


def interpret_10y(series: pd.Series) -> Signal:
    if series.empty:
        return Signal("neutral", _icon("neutral"), "데이터 없음", "FRED 응답을 받지 못했습니다.")
    latest = float(series.iloc[-1])
    change_bp = _five_day_change_bp(series)

    if change_bp is None:
        return Signal(
            "neutral", _icon("neutral"),
            f"현재 {latest:.2f}%",
            "5일 변동을 계산할 데이터가 부족합니다.",
        )

    if change_bp >= config.YIELD_5D_BP_THRESHOLD:
        return Signal(
            "danger", _icon("danger"),
            f"{latest:.2f}% (5일 +{change_bp:.0f}bp 급등)",
            "급격한 금리 상승은 주식의 할인율을 끌어올려 PER 압박과 성장주 매도 압력을 만듭니다.",
        )
    if change_bp <= -config.YIELD_5D_BP_THRESHOLD:
        return Signal(
            "watch", _icon("watch"),
            f"{latest:.2f}% (5일 {change_bp:.0f}bp 급락)",
            "급락은 경기 둔화 전망 또는 안전자산 쏠림을 시사합니다. 침체 우려 신호일 수 있습니다.",
        )
    return Signal(
        "safe", _icon("safe"),
        f"{latest:.2f}% (5일 {change_bp:+.0f}bp)",
        "최근 5일 변동이 ±30bp 이내로 안정적입니다.",
    )


def interpret_hy_spread(series: pd.Series) -> Signal:
    if series.empty:
        return Signal("neutral", _icon("neutral"), "데이터 없음", "FRED 응답을 받지 못했습니다.")
    latest = float(series.iloc[-1])
    change_bp = _five_day_change_bp(series)

    if latest > config.HY_SPREAD_LEVELS["danger"]:
        level = "danger"
        headline = f"{latest:.2f}% — 신용 경색·침체 신호"
        detail = "7%를 넘는 구간은 2008년·2020년 같은 위기 국면에서 나타났습니다. 위험자산 노출 축소를 고려할 구간."
    elif latest > config.HY_SPREAD_LEVELS["warning"]:
        level = "watch"
        headline = f"{latest:.2f}% — 신용 우려 확산"
        detail = "5~7%는 시장이 신용 리스크를 본격적으로 반영하기 시작하는 구간입니다."
    elif latest > config.HY_SPREAD_LEVELS["safe"]:
        level = "neutral"
        headline = f"{latest:.2f}% — 중립"
        detail = "장기 평균 부근의 정상 수준입니다."
    else:
        level = "safe"
        headline = f"{latest:.2f}% — 위험선호 강함"
        detail = "스프레드가 좁다는 것은 투자자들이 정크본드까지 적극적으로 매수하고 있다는 뜻입니다."

    if change_bp is not None and change_bp >= config.HY_SPREAD_5D_BP_THRESHOLD:
        level = "danger"
        detail += f" 다만 5일간 +{change_bp:.0f}bp 급확대 — 주식 하락 선행지표일 수 있어 조기경보입니다."

    return Signal(level, _icon(level), headline, detail)


def interpret_vix(latest: float) -> Signal:
    if latest < config.VIX_LEVELS["safe"]:
        return Signal("safe", _icon("safe"), f"{latest:.2f} — 매우 낮음",
                      "변동성이 매우 낮은 구간. 시장이 안일(complacency)할 수 있어 역설적으로 변곡점 주의.")
    if latest < config.VIX_LEVELS["warning"]:
        return Signal("neutral", _icon("neutral"), f"{latest:.2f} — 정상",
                      "장기 평균(약 19~20) 부근의 정상적인 변동성 수준입니다.")
    if latest < config.VIX_LEVELS["danger"]:
        return Signal("watch", _icon("watch"), f"{latest:.2f} — 경계",
                      "투자자들이 헤지 비용을 높게 지불하기 시작한 구간. 우려가 형성되는 단계.")
    if latest < 40:
        return Signal("danger", _icon("danger"), f"{latest:.2f} — 공포",
                      "공포 영역. 주식시장 단기 급락 또는 매크로 충격이 진행 중일 가능성.")
    return Signal("danger", _icon("danger"), f"{latest:.2f} — 패닉",
                  "패닉 영역 (40+). 역사적으로 2008·2020 같은 위기 국면에서만 나타남.")


def interpret_move(latest: float) -> Signal:
    if latest < config.MOVE_LEVELS["safe"]:
        return Signal("safe", _icon("safe"), f"{latest:.2f} — 낮음",
                      "채권시장 변동성이 낮음. 금리 경로에 대한 시장 합의가 안정적.")
    if latest < config.MOVE_LEVELS["warning"]:
        return Signal("neutral", _icon("neutral"), f"{latest:.2f} — 정상",
                      "정상 범위. 금리 변동성이 평균 수준입니다.")
    if latest < config.MOVE_LEVELS["danger"]:
        return Signal("watch", _icon("watch"), f"{latest:.2f} — 경계",
                      "채권시장 불안 상승. 통화정책 불확실성 또는 인플레이션 우려가 반영되는 구간.")
    return Signal("danger", _icon("danger"), f"{latest:.2f} — 채권시장 스트레스",
                  "140+ 영역은 2022·2023년 SVB 사태처럼 채권시장 스트레스가 극심한 국면. "
                  "금리 충격이 주식·신용으로 전이될 위험.")


def combine(yield_sig: Signal, hy_sig: Signal,
            yield_change_bp: Optional[float],
            hy_change_bp: Optional[float]) -> Signal:
    yc = yield_change_bp or 0
    hc = hy_change_bp or 0

    if yc >= config.YIELD_5D_BP_THRESHOLD and hc >= config.HY_SPREAD_5D_BP_THRESHOLD:
        return Signal(
            "danger", _icon("danger"),
            "강한 위험 — 금리·스프레드 동시 상승",
            "긴축 또는 스태그플레이션 우려가 동시에 작동하는 상황입니다. 주식·신용 양쪽에 비우호적.",
        )
    if yc <= -config.YIELD_5D_BP_THRESHOLD and hc >= config.HY_SPREAD_5D_BP_THRESHOLD:
        return Signal(
            "danger", _icon("danger"),
            "침체 우려 — 금리 하락 + 스프레드 상승",
            "안전자산(국채) 쏠림과 신용 악화가 동시에 나타나는 전형적 리세션 패턴입니다.",
        )

    levels = ["safe", "neutral", "watch", "danger"]
    rank = max(levels.index(yield_sig.level), levels.index(hy_sig.level))
    worst = levels[rank]
    headlines = {
        "safe": "안전 — 시장 안정",
        "neutral": "보통 — 중립적 시장 상황",
        "watch": "경계 — 신용/금리 일부 불안",
        "danger": "위험 — 명확한 경고 신호",
    }
    return Signal(worst, _icon(worst), headlines[worst], "10년물과 HY 스프레드 신호를 종합한 결과입니다.")
