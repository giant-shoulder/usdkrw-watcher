import asyncio
from datetime import datetime, timedelta
import pytz

# ✅ 예상 환율 상태 추적 변수 (글로벌 상태로 유지)
was_below_expected = False
was_above_expected = False
last_expected_alert_time = None
below_start_time = None
above_start_time = None
COOLDOWN = timedelta(minutes=15)
SUSTAINED_DURATION = timedelta(minutes=30)

# ✅ 예상 범위 이탈 감지 및 쿨다운/지속 알림 추가 적용
def analyze_expected_range(rate: float, expected: dict, now: datetime) -> str | None:
    global was_below_expected, was_above_expected, last_expected_alert_time
    global below_start_time, above_start_time

    if not expected or expected["date"] != now.date():
        return None

    low, high = expected["low"], expected["high"]

    def in_cooldown():
        return last_expected_alert_time and (now - last_expected_alert_time) < COOLDOWN

    # 하단 이탈
    if rate < low:
        if not was_below_expected:
            was_below_expected = True
            last_expected_alert_time = now
            below_start_time = now
            return (
                f"🚨 *예상 환율 하단 이탈 감지!*\n"
                f"예상 하단: {low:.2f}원\n"
                f"현재 환율: {rate:.2f}원\n"
                "📉 시장이 예측보다 더 약세를 보이고 있습니다."
            )
        elif in_cooldown():
            return None
        elif below_start_time and (now - below_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            below_start_time = None
            return (
                f"⚠️ *예상 환율 하단 이탈 30분 이상 지속 감지!*\n"
                f"예상 하단: {low:.2f}원\n"
                f"현재 환율: {rate:.2f}원\n"
                "📉 지속적인 약세 흐름이 이어지고 있습니다."
            )
        return None

    # 상단 돌파
    elif rate > high:
        if not was_above_expected:
            was_above_expected = True
            last_expected_alert_time = now
            above_start_time = now
            return (
                f"🚨 *예상 환율 상단 돌파 감지!*\n"
                f"예상 상단: {high:.2f}원\n"
                f"현재 환율: {rate:.2f}원\n"
                "📈 시장이 예측보다 강세를 보이며 상승 중입니다."
            )
        elif in_cooldown():
            return None
        elif above_start_time and (now - above_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            above_start_time = None
            return (
                f"⚠️ *예상 환율 상단 돌파 30분 이상 지속 감지!*\n"
                f"예상 상단: {high:.2f}원\n"
                f"현재 환율: {rate:.2f}원\n"
                "📈 과열된 상승 흐름이 지속되고 있습니다."
            )
        return None

    # 범위 내로 복귀 시 상태 초기화
    was_below_expected = False
    was_above_expected = False
    below_start_time = None
    above_start_time = None
    return None