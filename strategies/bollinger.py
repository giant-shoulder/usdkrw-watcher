# strategies/bollinger.py

from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD

def analyze_bollinger(rates: list[float], current: float, prev: float = None):
    """
    볼린저 밴드 상단 돌파/하단 이탈 여부 분석 및 메시지 생성
    """
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None, None

    avg = mean(rates[-MOVING_AVERAGE_PERIOD:])
    std = stdev(rates[-MOVING_AVERAGE_PERIOD:])
    upper = avg + 2 * std
    lower = avg - 2 * std

    arrow = ""
    diff_section = ""
    if prev is not None:
        diff = round(current - prev, 2)
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "→"
        direction = "상승 중" if diff > 0 else "하락 중" if diff < 0 else "변화 없음"
        diff_section = (
            f"\n\n{'🔺' if diff > 0 else '🔻' if diff < 0 else 'ℹ️'} *이전 관측값 대비 {direction}*\n"
            f"이전: {prev:.2f} → 현재: {current:.2f}\n"
            f"변동: {diff:+.2f}원"
        )

    if current > upper:
        status = "upper_breakout"
        message = (
            f"📈 볼린저 밴드 상단 돌파!\n"
            f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n상단: {upper:.2f}"
            f"{diff_section}"
        )
    elif current < lower:
        status = "lower_breakout"
        message = (
            f"📉 볼린저 밴드 하단 이탈!\n"
            f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n하단: {lower:.2f}"
            f"{diff_section}"
        )
    else:
        status, message = None, None

    return status, message