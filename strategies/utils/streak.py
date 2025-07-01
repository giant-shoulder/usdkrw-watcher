# utils/streak.py

def get_streak_advisory(upper, lower, cross_msg, jump_msg, prev_upper, prev_lower):
    is_golden = cross_msg and "골든크로스" in cross_msg
    is_dead = cross_msg and "데드크로스" in cross_msg
    is_crash = jump_msg and "급하락" in jump_msg
    is_surge = jump_msg and "급상승" in jump_msg

    # 하단 이탈 경고
    if lower >= 7 and not is_dead and not is_surge:
        for level, count in zip([3, 4, 5, 6], [7, 11, 15, 19]):
            if lower == count and prev_lower < level:
                return prev_upper, level, (
                    f"🚨 *강력한 하락 경고!* 하단 이탈이 *{lower}회* 반복되고 있습니다.\n"
                    "📉 단기 하락 확증 가능성이 높으며 손절 기준 점검이 필요합니다.\n"
                    "💡 *추가 손실 방지에 대비하세요.*"
                )

    # 상단 돌파 경고
    if upper >= 7 and not is_golden and not is_crash:
        for level, count in zip([3, 4, 5, 6], [7, 11, 15, 19]):
            if upper == count and prev_upper < level:
                return level, prev_lower, (
                    f"🚨 *과열 경고!* 상단 돌파가 *{upper}회* 반복되고 있습니다.\n"
                    "📈 고점 근접 가능성 높으며 과열 국면에 진입 중입니다.\n"
                    "💡 *리스크 관리와 익절 여부 점검을 권장합니다.*"
                )

    return prev_upper, prev_lower, None
