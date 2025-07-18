# strategies/bollinger.py

from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD
from strategies.utils.streak import get_streak_advisory
from db import (
    get_bounce_probability_from_rates,
    get_reversal_probability_from_rates,
    insert_breakout_event,
    get_pending_breakouts,
    mark_breakout_resolved
)
from utils import now_kst
EPSILON = 0.01  # 기준선과 거의 같은 경우 오차 허용


def get_volatility_info(band_width: float) -> tuple[str, str]:
    if band_width < 2:
        return "매우 좁은 변동성 구간", "시장 움직임이 거의 없어 횡보 흐름일 가능성이 높습니다."
    elif band_width < 3:
        return "좁은 변동성 구간", "가격 변화가 크지 않아 신중한 접근이 필요합니다."
    elif band_width < 5:
        return "보통 수준의 변동성", "일반적인 변동 구간으로 해석됩니다."
    elif band_width < 7:
        return "상대적으로 넓은 변동성", "가격이 빠르게 움직일 수 있는 구간입니다."
    else:
        return "매우 넓은 변동성 구간", "시장 불확실성이 높아 급격한 변동이 우려됩니다."


def format_prob_msg(direction: str, prob: float) -> str:
    direction_kr = "반등" if direction == "lower" else "되돌림(하락)"
    base_msg = f"📊 과거 3개월간 유사한 상황에서 *30분 이내 {direction_kr} 확률은 약 {prob:.0f}%*입니다."

    if prob >= 75:
        return f"{base_msg}\n→ *통계적으로 {direction_kr} 흐름이 강하게 나타났던 구간입니다.*"
    elif prob >= 50:
        return f"{base_msg}\n→ *{direction_kr} 가능성을 충분히 고려할 수 있는 흐름입니다.*"
    elif prob >= 30:
        return f"{base_msg}\n→ *참고 가능한 수치이긴 하나, 신중한 판단이 필요합니다.*"
    else:
        return f"{base_msg}\n→ *{('하락세' if direction == 'lower' else '상승세')} 지속 가능성도 염두에 둘 필요가 있습니다.*"

def auto_tolerance(deviation: float) -> float:
    """
    deviation 크기에 따라 적절한 tolerance 자동 결정
    """
    if deviation < 0.05:
        return 0.01
    elif deviation < 0.10:
        return 0.02
    elif deviation < 0.30:
        return 0.03
    elif deviation < 0.70:
        return 0.05
    else:
        return 0.10


def generate_realized_breakout_summary(matched_events: list) -> str:
    """
    여러 예측 일치 이벤트를 하나의 요약 메시지로 병합
    matched_events: [(event_type, threshold, current, elapsed_min, predicted_prob), ...]
    """
    if not matched_events:
        return None

    lines = []
    for i, (etype, th, curr, elapsed, prob) in enumerate(matched_events, start=1):
        is_upper = etype == "upper_breakout"
        action = "상단선 돌파" if is_upper else "하단선 이탈"
        result = "상단 기준선 아래 복귀" if is_upper else "하단 기준선 위로 복귀"
        lines.append(
            f"{i}) {elapsed}분 전: {action} → {elapsed}분 만에 {result} "
            f"(기준선: {th:.2f} / 현재: {curr:.2f})"
        )

    return (
        f"✅ *최근 30분 내 예측 일치 보고*\n"
        f"📌 {len(matched_events)}건의 예측이 모두 정확히 맞았습니다.\n\n" +
        "\n".join(lines) +
        "\n\n💡 동일 조건에서 향후 흐름 판단에 참고해 보세요."
    )


async def check_breakout_reversals(conn, current_rate: float, current_time) -> list[str]:
    """
    최근 발생한 breakout 이벤트들 중 30분 이내 반등/되돌림이 실제 발생했는지 감지하여
    ✅ 여러 개 일치 시 하나의 요약 메시지로 병합
    """
    pending = await get_pending_breakouts(conn)
    matched_events = []

    for event in pending:
        event_id = event["id"]
        event_type = event["event_type"]
        timestamp = event["timestamp"]
        threshold = event["threshold"]
        predicted_prob = event.get("predicted_probability", None)
        minutes_elapsed = int((current_time - timestamp).total_seconds() // 60)

        if minutes_elapsed > 30:
            continue

        realized = False
        if event_type == "lower_breakout" and current_rate >= threshold + EPSILON:
            realized = True
        elif event_type == "upper_breakout" and current_rate <= threshold - EPSILON:
            realized = True

        if realized:
            matched_events.append(
                (event_type, threshold, current_rate, minutes_elapsed, predicted_prob)
            )
            await mark_breakout_resolved(conn, event_id)

    # ✅ 병합 메시지 생성
    if matched_events:
        return [generate_realized_breakout_summary(matched_events)]
    return []


def format_realized_breakout_message(
    event_type: str,
    threshold: float,
    current: float,
    elapsed_min: int,
    predicted_prob: float | None = None
) -> str:
    """
    실제 되돌림/반등 발생 시 사용자 알림 메시지 구성
    """
    is_upper = event_type == "upper_breakout"
    icon = "📉" if is_upper else "📈"
    title = f"{icon} *볼린저 밴드 {'상단선 돌파' if is_upper else '하단선 이탈'} 후 실제 {'되돌림(하락)' if is_upper else '반등'} 감지!*"

    line1 = f"📏 {'상단 기준선' if is_upper else '하단 기준선'}: {threshold:.2f}원"
    line2 = f"💱 현재 환율: {current:.2f}원"
    line3 = f"⏱️ 경과 시간: {elapsed_min}분"

    pred = (
        f"*30분 내 {'상단 기준선 아래로 하락' if is_upper else '하단 기준선 위로 반등'}할 확률 {predicted_prob:.0f}%*"
        if predicted_prob is not None else "*예측 확률 정보 없음*"
    )
    result = f"*{elapsed_min}분 만에 {'상단 기준선 아래로 복귀' if is_upper else '하단 기준선 위로 복귀'}*"

    return (
        f"{title}\n\n"
        f"{line1}  \n{line2}  \n{line3}\n\n"
        f"📊 *예측이 실제로 일치했어요!*\n\n"
        f"• {elapsed_min}분 전 안내드렸던 전략 신호: 볼린저 밴드 {'상단선 돌파' if is_upper else '하단선 이탈'}  \n"
        f"• 예측: {pred}  \n"
        f"• 결과: {result}  \n\n"
        f"📊 동일 조건에서 향후 흐름 판단에 참고해 보세요."
    )

async def analyze_bollinger(
    conn,
    rates: list[float],
    current: float,
    prev: float = None,
    prev_upper: int = 0,
    prev_lower: int = 0,
    cross_msg: str = None,
    jump_msg: str = None,
    prev_status: str = None  # ✅ 추가: 이전 상태 전달
) -> tuple[str | None, list[str], int, int, int, int]:
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None, [], prev_upper, prev_lower, 0, 0

    avg = mean(rates[-MOVING_AVERAGE_PERIOD:])
    std = stdev(rates[-MOVING_AVERAGE_PERIOD:])
    upper = avg + 2 * std
    lower = avg - 2 * std
    band_width = upper - lower

    if band_width < EPSILON:
        return None, [], prev_upper, prev_lower, 0, 0

    volatility_label, volatility_comment = get_volatility_info(band_width)

    arrow = ""
    diff_section = ""
    if prev is not None:
        diff = round(current - prev, 2)
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "→"
        direction = "상승 중" if diff > 0 else "하락 중" if diff < 0 else "변화 없음"
        diff_section = (
            f"\n\n{'🔺' if diff > 0 else '🔵' if diff < 0 else 'ℹ️'} *이전 관측값 대비 {direction}*\n"
            f"이전: {prev:.2f} → 현재: {current:.2f}\n"
            f"변동: {diff:+.2f}원"
        )

    messages = []
    status = None
    upper_streak, lower_streak = 0, 0
    new_upper_level, new_lower_level = prev_upper, prev_lower

    now = now_kst()

    if current > upper + EPSILON:
        status = "upper_breakout"

        # ✅ 동일 상태면 발송 금지
        if prev_status == status:
            return status, [], prev_upper, prev_lower, prev_upper, prev_lower

        upper_streak = prev_upper + 1
        lower_streak = 0
        distance = round(current - upper, 2)
        deviation = distance
        tolerance = auto_tolerance(deviation)

        prob = await get_reversal_probability_from_rates(
            conn, upper, deviation, tolerance, MOVING_AVERAGE_PERIOD
        )
        prob_msg = format_prob_msg("upper", prob)
        icon = "📈"
        label = "상단"

        await insert_breakout_event(
            conn, event_type="upper_breakout", timestamp=now, boundary=upper, threshold=upper
        )

    elif current < lower - EPSILON:
        status = "lower_breakout"

        # ✅ 동일 상태면 발송 금지
        if prev_status == status:
            return status, [], prev_upper, prev_lower, prev_upper, prev_lower

        lower_streak = prev_lower + 1
        upper_streak = 0
        distance = round(lower - current, 2)
        deviation = distance
        tolerance = auto_tolerance(deviation)

        prob = await get_bounce_probability_from_rates(
            conn, lower, deviation, tolerance, MOVING_AVERAGE_PERIOD
        )
        prob_msg = format_prob_msg("lower", prob)
        icon = "📉"
        label = "하단"

        await insert_breakout_event(
            conn, event_type="lower_breakout", timestamp=now, boundary=lower, threshold=lower
        )

    else:
        return None, [], prev_upper, prev_lower, 0, 0

    band_msg = (
        f"{icon} 현재 밴드 폭은 *{band_width:.2f}원*입니다.\n"
        f"→ {volatility_label}으로, {volatility_comment}"
    )

    messages.append(
        f"{icon} 볼린저 밴드 {label} {'돌파' if label == '상단' else '이탈'}!\n"
        f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n"
        f"{label}: {upper if label == '상단' else lower:.2f}\n\n"
        f"📏 현재가가 {label}보다 {abs(distance):.2f}원 {'위' if label == '상단' else '아래'}입니다."
        f"{diff_section}\n\n"
        f"{prob_msg}\n\n"
        f"{band_msg}"
    )

    u_level, l_level, streak_msg = get_streak_advisory(
        upper=upper_streak,
        lower=lower_streak,
        cross_msg=cross_msg,
        jump_msg=jump_msg,
        prev_upper=prev_upper,
        prev_lower=prev_lower,
    )
    if streak_msg:
        messages.append(f"🧭 *동일 신호 반복 알림:*\n{streak_msg}")
        new_upper_level = u_level
        new_lower_level = l_level

    return status, messages, upper_streak, lower_streak, new_upper_level, new_lower_level