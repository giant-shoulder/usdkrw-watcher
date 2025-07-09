# strategies/bollinger.py

from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD
from strategies.utils.streak import get_streak_advisory
from db import (
    get_bounce_probability_from_rates,
    get_reversal_probability_from_rates
)

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
    볼린저 밴드 상단/하단 분석 + 거리/반등/조정 확률 및 반복 경고 포함
    """
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None, [], prev_upper, prev_lower, 0, 0

    avg = mean(rates[-MOVING_AVERAGE_PERIOD:])
    std = stdev(rates[-MOVING_AVERAGE_PERIOD:])
    upper = avg + 2 * std
    lower = avg - 2 * std
    band_width = upper - lower

    volatility_label = (
        "매우 좁음" if band_width < 2 else
        "좁음" if band_width < 3 else
        "보통" if band_width < 5 else
        "넓음" if band_width < 7 else
        "매우 넓음"
    )

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
        reversal_prob = await get_reversal_probability_from_rates(conn, upper)
        if reversal_prob >= 75:
            prob_msg = (
                f"📊 과거 유사한 상단 돌파 이후 *되돌림(하락) 비율은 약 {reversal_prob:.0f}%*입니다.\n"
                f"→ *상승 직후 일시적인 조정 흐름이 자주 나타났던 패턴입니다.*"
            )
        elif reversal_prob >= 50:
            prob_msg = (
                f"📊 비슷한 상단 돌파 상황에서의 되돌림 확률은 *약 {reversal_prob:.0f}%*입니다.\n"
                f"→ *과열 이후 단기 조정 가능성을 열어둘 수 있습니다.*"
            )
        elif reversal_prob >= 30:
            prob_msg = (
                f"📊 상단 돌파 후 되돌림 확률은 *약 {reversal_prob:.0f}%*입니다.\n"
                f"→ *추세 유지와 조정이 혼재된 구간으로 보입니다.*"
            )
        else:
            prob_msg = (
                f"📊 되돌림 확률은 *약 {reversal_prob:.0f}%*로 낮은 수준입니다.\n"
                f"→ *상승세가 그대로 이어질 가능성도 고려됩니다.*"
            )

        messages.append(
            f"📈 볼린저 밴드 상단 돌파!\n"
            f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n상단: {upper:.2f}\n\n"
            f"📏 현재가가 상단보다 {abs(distance):.2f}원 위입니다.\n"
            f"→ {'약한' if abs(distance) < 0.2 else '상당한'} 돌파로, 조정 가능성도 고려됩니다."
            f"{diff_section}\n\n"
            f"📊 과거 유사 상단 돌파 후 조정 확률은 약 {reversal_prob:.0f}%입니다.\n"
            f"{prob_msg}\n\n"
            f"📈 현재 밴드 폭: {band_width:.2f}원 ({volatility_label} 변동성)"
        )

    elif current < lower:
        status = "lower_breakout"
        lower_streak = prev_lower + 1
        upper_streak = 0
        distance = round(lower - current, 2)
        bounce_prob = await get_bounce_probability_from_rates(conn, lower)
        if bounce_prob >= 75:
            prob_msg = (
                f"📊 과거 유사한 하단 이탈 이후 *반등이 나타난 비율은 약 {bounce_prob:.0f}%*입니다.\n"
                f"→ *통계적으로 반등 흐름이 강하게 나타났던 구간입니다.*"
            )
        elif bounce_prob >= 50:
            prob_msg = (
                f"📊 과거 유사 상황에서의 반등 확률은 *약 {bounce_prob:.0f}%*입니다.\n"
                f"→ *반등 가능성을 충분히 고려할 수 있는 흐름입니다.*"
            )
        elif bounce_prob >= 30:
            prob_msg = (
                f"📊 과거 사례에서의 반등 확률은 *약 {bounce_prob:.0f}%* 수준입니다.\n"
                f"→ *참고 가능한 수치이긴 하나, 신중한 판단이 필요합니다.*"
            )
        else:
            prob_msg = (
                f"📊 반등 확률은 *약 {bounce_prob:.0f}%*로 낮은 편입니다.\n"
                f"→ *하락세 지속 가능성도 염두에 둘 필요가 있습니다.*"
            )

        messages.append(
            f"📉 볼린저 밴드 하단 이탈!\n"
            f"이동평균: {avg:.2f}\n현재: {current:.2f} {arrow}\n하단: {lower:.2f}\n\n"
            f"📏 현재가가 하단보다 {abs(distance):.2f}원 아래입니다.\n"
            f"→ {'약한' if abs(distance) < 0.2 else '상당한'} 이탈로, 반등 가능성도 고려됩니다."
            f"{diff_section}\n\n"
            f"📊 과거 유사 하단 이탈 후 반등 확률은 약 {bounce_prob:.0f}%입니다.\n"
            f"{prob_msg}\n\n"
            f"📈 현재 밴드 폭: {band_width:.2f}원 ({volatility_label} 변동성)"
        )

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