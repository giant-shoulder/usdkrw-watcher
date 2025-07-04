from datetime import datetime
import pytz

def analyze_expected_range(current_rate: float, expected: dict) -> str | None:
    """
    오늘의 예상 환율 범위를 벗어났는지 판단하고 메시지 반환.
    - 벗어난 경우: 경고 메시지 반환
    - 예상 범위 내: None
    """
    if not expected:
        return None  # 예측 없음

    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    if expected["date"] != today:
        return None

    low, high = expected["low"], expected["high"]

    if current_rate > high:
        return (
            f"🚨 *예상 환율 상단 돌파 감지!*\n"
            f"예상 상단: {high:.2f}원\n"
            f"현재 환율: {current_rate:.2f}원\n"
            "📈 시장이 예측보다 과열되어 상승 중입니다."
        )
    elif current_rate < low:
        return (
            f"🚨 *예상 환율 하단 이탈 감지!*\n"
            f"예상 하단: {low:.2f}원\n"
            f"현재 환율: {current_rate:.2f}원\n"
            "📉 시장이 예측보다 더 약세를 보이고 있습니다."
        )

    return None