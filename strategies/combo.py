from strategies.utils import (
    get_score_bar,
    get_signal_score,
    get_signal_direction,
    generate_combo_summary,
    get_streak_advisory,
    get_action_message
)

def analyze_combo(
    b_status: str,
    b_msg: str,
    j_msg: str,
    c_msg: str,
    e_msg: str,
    upper_streak: int,
    lower_streak: int,
    prev_upper_level: int,
    prev_lower_level: int
):
    """
    활성화된 전략 메시지를 기반으로 종합 분석 수행:
    - 전략 점수 계산
    - 방향성 판단
    - 헤더/액션/점수바/반복 경고 통합
    - 단일 전략이라도 충분한 점수일 경우 combo 스타일 사용
    """

    signals = {
        "📊 볼린저 밴드": b_msg,
        "⚡ 급변 감지": j_msg,
        "🔁 이동평균선 크로스": c_msg,
        "📡 예상 범위 이탈": e_msg,
    }
    active_signals = {k: v for k, v in signals.items() if v}

    if not active_signals:
        return None

    # 점수 및 방향성 판단
    score = get_signal_score(active_signals)
    direction = get_signal_direction(active_signals.values())

    # ✅ 단일 전략일 경우 conflict → neutral 처리
    if len(active_signals) == 1 and direction == "conflict":
        direction = "neutral"

    # 콤보 메시지 생성 조건: 전략 수 ≥ 2 또는 단일 전략 + 점수 30 이상
    should_apply_combo = (
        len(active_signals) >= 2
        or (len(active_signals) == 1 and score >= 30)
    )

    if not should_apply_combo:
        return None

    # 헤더 및 해석 메시지
    header = generate_combo_summary(
        score=score,
        matched=len(active_signals),
        total=len(signals),
        direction=direction
    )

    action = get_action_message(direction, score)

    # 전략별 상세 메시지
    signal_details = "\n\n".join([f"{k}\n{v}" for k, v in active_signals.items()])
    score_bar = get_score_bar(score, direction)

    # streak 관련 추가 참고 메시지
    new_upper, new_lower, streak_msg = get_streak_advisory(
        upper_streak, lower_streak,
        cross_msg=c_msg,
        jump_msg=j_msg,
        prev_upper=prev_upper_level,
        prev_lower=prev_lower_level
    )

    message = (
        f"{header}\n\n"
        f"{signal_details}\n\n"
        f"{action}\n\n"
        f"🧮 신호 점수: *{score}점*\n"
        f"{score_bar}"
    )
    if streak_msg:
        message += f"\n\n🧭 *추가 참고:*\n{streak_msg}"

    return {
        "message": message,
        "type": direction,
        "score": score,
        "new_upper_level": new_upper,
        "new_lower_level": new_lower,
    }