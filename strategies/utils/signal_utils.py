# utils/signal_utils.py

from config import SIGNAL_WEIGHTS

# 각 전략별 메시지 특성상 신호 강도를 다르게 반영할 키워드 정의
SIGNAL_KEYWORDS = {
    "buy": {
        "강한": {"골든크로스", "급반등", "강한 반전", "저점 매수"},
        "약한": {"하락", "하단", "반전", "약세", "이탈"}
    },
    "sell": {
        "강한": {"데드크로스", "급등", "과열 돌파", "고점"},
        "약한": {"상단", "상승", "과열", "돌파"}
    },
    "neutral": {
        "유지": {"골든 상태 유지", "데드 상태 유지"}
    }
}

def get_signal_direction(messages):
    """
    메시지 내 키워드를 기반으로 방향성 판단
    강/약 구분 + 중립 메시지는 제외 처리
    """
    def contains(msg, keywords):
        return any(kw in msg for kw in keywords)

    buy_score = 0
    sell_score = 0

    for msg in messages:
        if not msg:
            continue

        # 강한 키워드 우선 반영 (2점)
        if contains(msg, SIGNAL_KEYWORDS["buy"]["강한"]):
            buy_score += 2
        elif contains(msg, SIGNAL_KEYWORDS["buy"]["약한"]):
            buy_score += 1

        if contains(msg, SIGNAL_KEYWORDS["sell"]["강한"]):
            sell_score += 2
        elif contains(msg, SIGNAL_KEYWORDS["sell"]["약한"]):
            sell_score += 1

    # 방향성 판단
    if buy_score > 0 and sell_score == 0:
        return "buy"
    elif sell_score > 0 and buy_score == 0:
        return "sell"
    elif buy_score > 0 and sell_score > 0:
        if buy_score > sell_score:
            return "buy"
        elif sell_score > buy_score:
            return "sell"
        else:
            return "conflict"
    else:
        return "neutral"

def get_signal_score(active_signals: dict[str, str]) -> int:
    """
    전략별 시그널 메시지에 따라 가중치 차등 적용하여 점수 계산
    - 전략 가중치 × 메시지 강도 (0.5~1.0) 적용
    - 최대 100점 제한
    """
    score = 0
    for name, msg in active_signals.items():
        weight = SIGNAL_WEIGHTS.get(name, 0)

        # 메시지가 유지 상태면 낮은 가중치 적용
        if any(kw in msg for kw in SIGNAL_KEYWORDS["neutral"]["유지"]):
            score += int(weight * 0.3)
        # 강한 신호 포함 시 높은 점수 반영
        elif any(kw in msg for kw in SIGNAL_KEYWORDS["buy"]["강한"] | SIGNAL_KEYWORDS["sell"]["강한"]):
            score += weight
        # 약한 키워드만 있을 경우 점수 일부만 반영
        else:
            score += int(weight * 0.6)

    return min(score, 100)

def generate_combo_summary(score: int, matched: int, total: int, direction: str) -> str:
    """
    점수 및 방향성 기반 콤보 전략 헤더 생성

    Args:
        score (int): 신호 점수 (0~100)
        matched (int): 활성화된 전략 수
        total (int): 전체 전략 수
        direction (str): 'buy', 'sell', 'conflict', 'neutral'

    Returns:
        str: 텔레그램용 헤더 메시지
    """
    ratio = matched / total if total else 0
    dir_text = {"buy": "🟢 매수", "sell": "🔴 매도", "conflict": "⚖️ 중립", "neutral": "ℹ️ 관망"}.get(direction, "❓ 미확정")

    # ✅ 단일 전략일 경우는 별도 메시지 처리
    if matched == 1:
        if score >= 30:
            return (
                f"📌 *[주요 전략 기반 해석 — {dir_text} 시사]*\n"
                f"💬 하나의 핵심 전략에서 방향성 단서가 포착되었습니다."
            )
        else:
            return (
                f"🔍 *[참고용 신호 — {dir_text} 시사]*\n"
                f"📉 약한 신호로, 시장 흐름 참고 수준입니다."
            )

    # ✅ 2개 이상 전략이 일치하는 경우 (기존 구조 유지)
    if score >= 90 and ratio >= 0.75:
        return (
            f"🔥 *[강력한 {dir_text} 신호 감지]*\n"
            f"💡 다수 전략이 일치하며 시장 움직임이 뚜렷합니다."
        )
    elif score >= 70:
        return (
            f"🧭 *[진입 고려 단계 — {dir_text} 신호 감지]*\n"
            f"📈 여러 전략에서 일치된 방향이 포착되었습니다."
        )
    elif score >= 40:
        return (
            f"⚠️ *[불확실한 시그널 감지]*\n"
            f"📌 일부 전략은 {dir_text}를 시사하지만 해석은 신중히 필요합니다."
        )
    elif score >= 20:
        return (
            f"🔍 *[참고용 신호 — {dir_text} 시사]*\n"
            f"📉 약한 신호로, 시장 흐름 참고 수준입니다."
        )
    else:
        return (
            f"🚫 *[진입 신호 부족 — 전략 해석 미약]*\n"
            f"{'📈 매수로' if direction == 'buy' else '📉 매도로'} 해석할 근거가 부족합니다."
        )

def get_action_message(direction: str, score: int) -> str:
    if direction == "buy":
        if score < 30:
            return (
                "🟢 *저점 반등 가능성이 감지되었습니다.*\n"
                "📉 *시장이 과매도 상태일 수 있습니다.*\n"
                "💡 참고 지표로 활용해 보세요."
            )
        elif score < 50:
            return (
                "🟢 *저점 반등 가능성을 시사합니다.*\n"
                "📉 *시장이 하락세를 보이는 가운데 일부 반등 시그널이 포착되었습니다.*\n"
                "💡 진입 타이밍으로 보기엔 이르지만, 흐름 관찰이 필요합니다."
            )
        else:
            return (
                "🟢 *매수 진입 타이밍으로 판단됩니다.*\n"
                "📉 *시장이 과도하게 하락했거나, 반등 신호가 감지되었습니다.*\n"
                "💡 추세 전환, 저점 반등 가능성을 고려한 진입 타이밍입니다."
            )

    elif direction == "sell":
        if score < 30:
            return (
                "🔴 *고점 도달 가능성이 감지되었습니다.*\n"
                "📈 *시장 과열 구간일 수 있습니다.*\n"
                "💡 참고 지표로 활용해 보세요."
            )
        elif score < 50:
            return (
                "🔴 *과열 신호가 일부 감지되었습니다.*\n"
                "📈 *과거 고점 패턴과 유사한 움직임이 포착되었으나 신뢰도는 낮습니다.*\n"
                "💡 추세 반전 가능성에 주의하세요."
            )
        else:
            return (
                "🔴 *매도 고려 타이밍으로 판단됩니다.*\n"
                "📈 *시장이 과열되었거나, 하락 전환 신호가 감지되었습니다.*\n"
                "💡 피크 도달 또는 고점 차익 실현 구간일 수 있습니다."
            )

    elif direction == "conflict":
        return (
            "⚠️ *전략 간 방향성이 상충됩니다.*\n"
            "💡 서로 다른 시그널이 동시에 감지되어, 섣부른 진입보다는 관망이 권장됩니다."
        )

    else:
        return (
            "ℹ️ *명확한 방향성이 없습니다.*\n"
            "💡 시장 상황을 조금 더 지켜보는 것이 좋겠습니다."
        )
    

# === 추가: 정량 보조지표 유틸 ===
from statistics import mean
from math import sqrt

def ema(series, period):
    if len(series) < period: return None
    k = 2 / (period + 1)
    e = series[-period]
    for v in series[-period+1:]:
        e = v * k + e * (1 - k)
    return e

def sma(series, period):
    if len(series) < period: return None
    return sum(series[-period:]) / period

def rolling_stdev(series, period):
    if len(series) < period: return None
    window = series[-period:]
    m = mean(window)
    var = sum((x - m) ** 2 for x in window) / (len(window) - 1)
    return sqrt(var)

def zscore(series, period):
    """마지막 값이 최근 period 평균 대비 얼마나 벗어났는지 표준화"""
    if len(series) < period: return None
    m = sma(series, period)
    s = rolling_stdev(series, period)
    if not s or s == 0: return 0.0
    return (series[-1] - m) / s

def atr_from_rates(highs, lows, closes, period=14):
    """
    Wilder 스타일 ATR 추정치.
    우선순위: (high/low/close) → (close-only fallback)
    TR_i = max(H_i - L_i, |H_i - C_{i-1}|, |L_i - C_{i-1}|)
    단, 고저가가 없으면 TR_i ≈ |C_i - C_{i-1}| 로 근사.
    반환값 단위는 원이며, 최근 period 구간의 단순 평균을 사용합니다.
    """
    highs = highs or []
    lows = lows or []
    closes = closes or []

    n = len(closes)

    # Case A: high/low/close 모두 제공되고 길이가 충분한 경우
    if highs and lows and n >= period + 1 and len(highs) >= n and len(lows) >= n:
        trs = []
        for i in range(1, n):
            h = highs[i]
            l = lows[i]
            pc = closes[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if len(trs) >= period:
            return sum(trs[-period:]) / period

    # Case B: 종가만 있는 경우 — 절대 차분으로 근사
    if n >= period + 1:
        diffs = [abs(closes[i] - closes[i - 1]) for i in range(1, n)]
        return sum(diffs[-period:]) / period

    return None
