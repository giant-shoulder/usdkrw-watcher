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

# 히스테리시스 여유 (경계 재진입/재이탈 잡신호 억제)
HYST = 0.10  # 원 단위, 필요시 config로 이관 가능

# 편차 기반 레벨링 임계값 (예상폭 대비 비율)
LEVEL_MILD = 0.03      # 3% 미만: 약함
LEVEL_MODERATE = 0.07  # 7% 미만: 보통
# 7% 이상: 강함

def _deviation_and_ratio(rate: float, low: float, high: float) -> tuple[float, float]:
    """예상 범위를 벗어난 절대편차와, 범위폭 대비 비율을 반환."""
    width = max(1e-6, high - low)
    if rate < low:
        dev = (low - rate)
    elif rate > high:
        dev = (rate - high)
    else:
        dev = 0.0
    return dev, (dev / width)


def _level_for_ratio(ratio: float) -> tuple[str, str]:
    """편차 비율에 따른 레벨과 라벨 텍스트."""
    if ratio >= LEVEL_MODERATE:
        return ("강함", "🟥 강함")
    if ratio >= LEVEL_MILD:
        return ("보통", "🟧 보통")
    return ("약함", "🟨 약함")

# ✅ 예상 범위 이탈 감지 및 쿨다운/지속 알림 추가 적용
def analyze_expected_range(rate: float, expected: dict, now: datetime) -> str | None:
    global was_below_expected, was_above_expected, last_expected_alert_time
    global below_start_time, above_start_time

    if not expected or expected["date"] != now.date():
        return None

    low, high = expected["low"], expected["high"]

    # 히스테리시스 경계
    below_hard = (rate < (low - HYST))
    above_hard = (rate > (high + HYST))
    reenter_from_below = was_below_expected and (rate >= (low + HYST))
    reenter_from_above = was_above_expected and (rate <= (high - HYST))

    def in_cooldown():
        return last_expected_alert_time and (now - last_expected_alert_time) < COOLDOWN

    # 하단 이탈 (히스테리시스 적용)
    if below_hard:
        dev, ratio = _deviation_and_ratio(rate, low, high)
        level_txt, level_badge = _level_for_ratio(ratio)

        if not was_below_expected:
            was_below_expected = True
            last_expected_alert_time = now
            below_start_time = now
            return (
                f"🚨 *예상 범위 하단 이탈 감지* {level_badge}\n"
                f"📌 예상 하단: {low:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원 (하단 대비 −{dev:.2f}원, 폭 대비 {ratio*100:.1f}%, 레벨: {level_txt})\n"
                "📉 시장이 딜러 예상보다 약세로 이탈했습니다."
            )
        elif in_cooldown():
            return None
        elif below_start_time and (now - below_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            below_start_time = None
            return (
                f"⚠️ *하단 이탈 지속(30분+)* {level_badge}\n"
                f"📌 예상 하단: {low:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원 (하단 대비 −{dev:.2f}원, 폭 대비 {ratio*100:.1f}%, 레벨: {level_txt})\n"
                "📉 약세 흐름이 장기화되고 있습니다."
            )
        return None

    # 상단 돌파 (히스테리시스 적용)
    elif above_hard:
        dev, ratio = _deviation_and_ratio(rate, low, high)
        level_txt, level_badge = _level_for_ratio(ratio)

        if not was_above_expected:
            was_above_expected = True
            last_expected_alert_time = now
            above_start_time = now
            return (
                f"🚨 *예상 범위 상단 돌파 감지* {level_badge}\n"
                f"📌 예상 상단: {high:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원 (상단 대비 +{dev:.2f}원, 폭 대비 {ratio*100:.1f}%, 레벨: {level_txt})\n"
                "📈 시장이 딜러 예상보다 강세로 이탈했습니다."
            )
        elif in_cooldown():
            return None
        elif above_start_time and (now - above_start_time) > SUSTAINED_DURATION:
            last_expected_alert_time = now
            above_start_time = None
            return (
                f"⚠️ *상단 돌파 지속(30분+)* {level_badge}\n"
                f"📌 예상 상단: {high:.2f}원\n"
                f"💱 현재 환율: {rate:.2f}원 (상단 대비 +{dev:.2f}원, 폭 대비 {ratio*100:.1f}%, 레벨: {level_txt})\n"
                "📈 강세 흐름이 장기화되고 있습니다."
            )
        return None

    # 범위 내로 복귀 (히스테리시스 기반 확실 복귀) 시 상태 초기화 + 알림
    if reenter_from_below:
        was_below_expected = False
        below_start_time = None
        last_expected_alert_time = now
        margin = rate - low
        return (
            f"✅ *예상 범위 하단 복귀 확인*\n"
            f"📌 예상 하단: {low:.2f}원\n"
            f"💱 현재 환율: {rate:.2f}원 (복귀 여유 +{margin:.2f}원)\n"
            "↩️ 하단 경계 상향 복귀를 확인했습니다."
        )

    if reenter_from_above:
        was_above_expected = False
        above_start_time = None
        last_expected_alert_time = now
        margin = high - rate
        return (
            f"✅ *예상 범위 상단 복귀 확인*\n"
            f"📌 예상 상단: {high:.2f}원\n"
            f"💱 현재 환율: {rate:.2f}원 (복귀 여유 +{margin:.2f}원)\n"
            "↩️ 상단 경계 하향 복귀를 확인했습니다."
        )

    # 완전 범위 내 유지: 상태만 리셋
    was_below_expected = False
    was_above_expected = False
    below_start_time = None
    above_start_time = None
    return None