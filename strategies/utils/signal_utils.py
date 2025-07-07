# utils/signal_utils.py

from config import SIGNAL_WEIGHTS

def get_signal_direction(messages):
    """메시지 내 키워드 기반으로 buy/sell/conflict/neutral 판단"""
    buy_keywords = {
        "하단", "하락",        # 밴드 이탈 → 과매도
        "골든크로스", "급반등", # 추세 전환 상승
        "반전", "저점", "이탈", "약세"  # 예상보다 하락 → 저가 매수
    }

    sell_keywords = {
        "상단", "상승",         # 밴드 상단 돌파 → 과열
        "데드크로스", "급등",   # 추세 전환 하락 or 과열 급등
        "고점", "과열", "돌파"   # 고점 도달 판단
    }

    def contains(msg, keywords):
        return any(kw in msg for kw in keywords)

    buy_score = sum(contains(msg, buy_keywords) for msg in messages if msg)
    sell_score = sum(contains(msg, sell_keywords) for msg in messages if msg)

    if buy_score > 0 and sell_score == 0:
        return "buy"
    elif sell_score > 0 and buy_score == 0:
        return "sell"
    elif buy_score > 0 and sell_score > 0:
        return "buy" if buy_score > sell_score else "sell" if sell_score > buy_score else "conflict"
    return "neutral"

def get_signal_score(active_signals: dict[str, str]) -> int:
    """
    활성화된 전략에 따라 종합 점수 계산.
    각 전략별 가중치를 기준으로 계산하고, 최대 100점으로 제한.
    """
    score = 0
    for signal_name in active_signals:
        weight = SIGNAL_WEIGHTS.get(signal_name, 0)
        score += weight
    return min(score, 100)

def generate_combo_header(score: int, matched: int, total: int, direction: str) -> str:
    """
    종합 전략 점수 및 일치 전략 수 기반 헤더 생성

    Args:
        score (int): 신호 점수 (0~100)
        matched (int): 활성화된 전략 수
        total (int): 전체 전략 수
        direction (str): 방향성 ('buy', 'sell', 'conflict', 'neutral')

    Returns:
        str: 헤더 메시지
    """
    ratio = matched / total if total else 0
    dir_emoji = "🟢 매수" if direction == "buy" else "🔴 매도" if direction == "sell" else "⚖️ 중립"

    if score >= 90 and ratio >= 0.75:
        return f"🔥 *[강력한 {dir_emoji} 신호 감지]*\n💡 다수 전략이 일치하며 시장 움직임이 뚜렷합니다."
    elif score >= 70 and ratio >= 0.5:
        return f"🧭 *[진입 고려 단계 — {dir_emoji} 시사]*\n📌 일부 전략이 일치하여 흐름을 주시할 구간입니다."
    elif score >= 40:
        return f"⚠️ *[불확실한 신호 감지]*\n⏳ 전략 간 일치 부족으로 진입은 신중히 판단하세요."
    else:
        return f"🚫 *[진입 신호 부족 — 전략 해석 미약]*\n📉 {dir_emoji}로 해석할 근거가 부족합니다."
