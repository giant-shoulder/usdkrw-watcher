# utils/signal_utils.py

from config import SIGNAL_WEIGHTS

def get_signal_direction(messages):
    """메시지 내 키워드 기반으로 buy/sell/conflict/neutral 판단"""
    buy_keywords = {"하단", "하락", "골든크로스", "급반등", "반전", "저점"}
    sell_keywords = {"상단", "상승", "데드크로스", "급락", "고점"}

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

def get_signal_score(signals):
    """전략별 가중치 기반 총점 계산"""
    return sum(SIGNAL_WEIGHTS.get(k, 0) for k in signals if signals[k])
