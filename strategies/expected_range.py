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
                f"🚨 *외환 딜러 예상 범위 하단 이탈 감지!*\n"
                f"📌 예상 하단(딜러 전망): {low:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원\n"
                "📉 시장이 외환 딜러 예상보다 약세를 보이며 하락 압력이 강해지고 있습니다."
            )
        elif in_cooldown():
            return None
        elif below_start_time and (now - below_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            below_start_time = None
            return (
                f"⚠️ *외환 딜러 예상 범위 하단 이탈 30분 이상 지속!*\n"
                f"📌 예상 하단(딜러 전망): {low:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원\n"
                "📉 딜러 예상보다 낮은 수준에서 약세 흐름이 장기화되고 있습니다."
            )
        return None

    # 상단 돌파
    elif rate > high:
        if not was_above_expected:
            was_above_expected = True
            last_expected_alert_time = now
            above_start_time = now
            return (
                f"🚨 *외환 딜러 예상 범위 상단 돌파 감지!*\n"
                f"📌 예상 상단(딜러 전망): {high:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원\n"
                "📈 시장이 외환 딜러 예상보다 강세를 보이며 매수세가 우위를 점하고 있습니다."
            )
        elif in_cooldown():
            return None
        elif above_start_time and (now - above_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            above_start_time = None
            return (
                f"⚠️ *외환 딜러 예상 범위 상단 돌파 30분 이상 지속!*\n"
                f"📌 예상 상단(딜러 전망): {high:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원\n"
                "📈 예상 범위를 넘어선 강세 흐름이 지속되며 과열 조짐이 나타나고 있습니다."
            )
        return None

    # 범위 내로 복귀 시 상태 초기화
    was_below_expected = False
    was_above_expected = False
    below_start_time = None
    above_start_time = None
    return None