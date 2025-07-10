# strategies/bollinger.py

from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD
from strategies.utils.streak import get_streak_advisory
from db import (
    get_bounce_probability_from_rates,
    get_reversal_probability_from_rates
)

from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD
from strategies.utils.streak import get_streak_advisory
from db import (
    get_bounce_probability_from_rates,
    get_reversal_probability_from_rates
)


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

async def analyze_bollinger(
    conn,
    rates: list[float],
    current: float,
    prev: float = None,
    prev_upper: int = 0,
    prev_lower: int = 0,
    cross_msg: str = None,
    jump_msg: str = None
) -> tuple[str | None, list[str], int, int, int, int]:
    """
    볼린저 밴드 분석 함수
    - 현재 환율이 밴드 상단/하단을 돌파하거나 이탈했는지 판단
    - 돌파/이탈 시 유사한 과거 조건에서의 반등 또는 조정 확률 계산
    - 메시지 형태로 결과 제공
    """
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None, [], prev_upper, prev_lower, 0, 0

    avg = mean(rates[-MOVING_AVERAGE_PERIOD:])
    std = stdev(rates[-MOVING_AVERAGE_PERIOD:])
    upper = avg + 2 * std
    lower = avg - 2 * std
    band_width = upper - lower

    volatility_label, volatility_comment = get_volatility_info(band_width)

    # 현재가 vs 이전가 비교
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

    if current > upper:
        status = "upper_breakout"
        upper_streak = prev_upper + 1
        lower_streak = 0
        distance = round(current - upper, 2)

        deviation = distance
        tolerance = auto_tolerance(deviation)

        # 상단 돌파 후 유사 초과폭 기준 조정 확률 계산
        prob = await get_reversal_probability_from_rates(conn, upper, deviation, tolerance, MOVING_AVERAGE_PERIOD)
        prob_msg = format_prob_msg("upper", prob)
        icon = "📈"
        label = "상단"

    elif current < lower:
        status = "lower_breakout"
        lower_streak = prev_lower + 1
        upper_streak = 0
        distance = round(lower - current, 2)

        deviation = distance
        tolerance = auto_tolerance(deviation)

        # 하단 이탈 후 유사 초과폭 기준 반등 확률 계산
        prob = await get_bounce_probability_from_rates(conn, lower, deviation, tolerance, MOVING_AVERAGE_PERIOD)
        prob_msg = format_prob_msg("lower", prob)
        icon = "📉"
        label = "하단"

    else:
        return None, [], prev_upper, prev_lower, 0, 0

    # 밴드 폭 메시지 구성
    band_msg = (
        f"{icon} 현재 밴드 폭은 *{band_width:.2f}원*입니다.\n"
        f"→ {volatility_label}으로, {volatility_comment}"
    )

    # 종합 메시지 구성
    messages.append(
        f"{icon} 볼린저 밴드 {label} {'돌파' if label == '상단' else '이탈'}!\n"
        f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n{label}: {upper if label == '상단' else lower:.2f}\n\n"
        f"📏 현재가가 {label}보다 {abs(distance):.2f}원 {'위' if label == '상단' else '아래'}입니다."
        f"{diff_section}\n\n"
        f"📊 과거 3개월간 유사한 상황에서\n"
        f"{prob_msg}\n"
        f"→ *{'되돌림(하락)' if label == '상단' else '반등'} 가능성을 충분히 고려할 수 있는 흐름입니다.*\n\n"
        f"{band_msg}"
    )

    # 반복 경고 메시지 확인
    u_level, l_level, streak_msg = get_streak_advisory(
        upper=upper_streak,
        lower=lower_streak,
        cross_msg=cross_msg,
        jump_msg=jump_msg,
        prev_upper=prev_upper,
        prev_lower=prev_lower
    )
    if streak_msg:
        messages.append(f"🧭 *동일 신호 반복 알림:*\n{streak_msg}")
        new_upper_level = u_level
        new_lower_level = l_level

    return status, messages, upper_streak, lower_streak, new_upper_level, new_lower_level