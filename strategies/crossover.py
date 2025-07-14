# strategies/crossover.py

from statistics import mean

from config import SHORT_TERM_PERIOD, LONG_TERM_PERIOD

def analyze_crossover(rates, prev_short_avg, prev_long_avg):
    """
    골든/데드크로스 감지 및 메시지 생성

    전환 감지: 골든크로스 또는 데드크로스 발생 시 메시지 강조  
    상태 해석: 현재 단기 > 장기 → 골든 상태로, 단기 < 장기 → 데드 상태로 해석
    """
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_short_avg, prev_long_avg

    short_ma = mean(rates[-SHORT_TERM_PERIOD:])
    long_ma = mean(rates[-LONG_TERM_PERIOD:])
    EPSILON = 0.005

    signal = None
    crossed_up = False
    crossed_down = False

    if prev_short_avg is not None and prev_long_avg is not None:
        crossed_up = short_ma > long_ma and prev_short_avg <= prev_long_avg
        crossed_down = short_ma < long_ma and prev_short_avg >= prev_long_avg

    if abs(short_ma - long_ma) <= EPSILON:
        relation = "="
    elif short_ma > long_ma:
        relation = ">"
    else:
        relation = "<"

    # 전환 메시지 우선
    if crossed_up:
        signal = (
            "🟢 *골든크로스 발생!* 장기 상승 전환 신호입니다.\n"
            "📈 단기 평균선이 장기 평균선을 상향 돌파했어요.\n"
            "💡 *매수 시그널입니다.*"
        )
    elif crossed_down:
        signal = (
            "🔴 *데드크로스 발생!* 하락 전환 가능성이 있습니다.\n"
            "📉 단기 평균선이 장기 평균선을 하향 돌파했어요.\n"
            "💡 *매도 시그널입니다.*"
        )
    else:
        # 현재 상태 해석만 붙이기
        if relation == ">":
            signal = (
                "🟢 *골든 상태 유지 중*\n"
                "📈 단기 평균선이 장기 평균선보다 높습니다.\n"
                "💡 *상승 흐름 지속 가능성 있음.*"
            )
        elif relation == "<":
            signal = (
                "🔴 *데드 상태 유지 중*\n"
                "📉 단기 평균선이 장기 평균선보다 낮습니다.\n"
                "💡 *약세 흐름 지속 가능성 있음.*"
            )

    # 평균선 비교 정보는 항상 추가
    if signal:
        signal += f"\n📊 이동평균선 비교\n단기: {short_ma:.2f} {relation} 장기: {long_ma:.2f}"

    return signal, short_ma, long_ma