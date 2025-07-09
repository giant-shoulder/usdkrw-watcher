# utils/streak.py

def get_streak_advisory(upper, lower, cross_msg, jump_msg, prev_upper, prev_lower):
    is_golden = cross_msg and "골든크로스" in cross_msg
    is_dead = cross_msg and "데드크로스" in cross_msg
    is_crash = jump_msg and "급하락" in jump_msg
    is_surge = jump_msg and "급상승" in jump_msg

    # 하단 이탈 경고 (기준 완화: 5회부터)
    if lower >= 5 and not is_dead and not is_surge:
        for level, count in zip([3, 4, 5, 6], [5, 9, 13, 17]):
            if lower == count and prev_lower <= level - 1:
                return prev_upper, level, (
                    f"⚠️ *지속적인 하단 이탈 주의!* 하단 이탈이 *{lower}회* 연속 발생하고 있습니다.\n"
                    "📉 환율이 계속해서 낮아지며 불안정한 흐름을 보이고 있습니다.\n"
                    "💡 *지금은 섣부른 진입보다는 신중한 관망이 필요한 시점입니다.*"
                )

    # 상단 돌파 경고 (기준 완화: 5회부터)
    if upper >= 5 and not is_golden and not is_crash:
        for level, count in zip([3, 4, 5, 6], [5, 9, 13, 17]):
            if upper == count and prev_upper <= level - 1:
                return level, prev_lower, (
                    f"🚨 *지속적인 상단 돌파 주의!* 상단 돌파가 *{upper}회* 연속 발생하고 있습니다.\n"
                    "📈 환율이 계속해서 상승하며 과열 양상을 보이고 있습니다.\n"
                    "💡 *지금은 고점 부근일 수 있으니 리스크 관리와 차익 실현 여부를 점검해보세요.*"
                )

    return prev_upper, prev_lower, None