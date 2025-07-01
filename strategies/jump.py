# strategies/jump.py

from config import JUMP_THRESHOLD

def analyze_jump(prev, current):
    """
    직전 환율 대비 급변 감지
    - 상승폭 또는 하락폭이 JUMP_THRESHOLD 이상이면 경고 메시지 생성
    """
    if prev is None:
        return None

    diff = round(current - prev, 2)

    if abs(diff) >= JUMP_THRESHOLD:
        direction = "급상승" if diff > 0 else "급하락"
        symbol = "🔺📈" if diff > 0 else "🔵📉"
        return (
            f"{symbol} *단기 {direction}!* \n"
            f"현재: {current:.2f}\n"
            f"이전: {prev:.2f}\n"
            f"변동: {diff:+.2f}원"
        )

    return None