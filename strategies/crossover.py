# strategies/crossover.py

from statistics import mean

from config import SHORT_TERM_PERIOD, LONG_TERM_PERIOD

def analyze_crossover(rates, prev_short_avg, prev_long_avg):
    """
    골든/데드크로스 감지 및 메시지 생성

    골든크로스: 단기 이동평균선이 장기선을 상향 돌파 → 매수 시그널  
    데드크로스: 단기 이동평균선이 장기선을 하향 돌파 → 매도 시그널
    """
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_short_avg, prev_long_avg

    short_ma = mean(rates[-SHORT_TERM_PERIOD:])
    long_ma = mean(rates[-LONG_TERM_PERIOD:])
    signal = None

    if prev_short_avg is not None and prev_long_avg is not None:
        crossed_up = short_ma > long_ma and prev_short_avg <= prev_long_avg
        crossed_down = short_ma < long_ma and prev_short_avg >= prev_long_avg

        if crossed_up:
            signal = (
                "🟢 *골든크로스 발생!* 장기 상승 전환 신호입니다.\n"
                "📈 단기 평균선이 장기 평균선을 상향 돌파했어요.\n"
                "💡 *매수 시그널입니다.*\n"
                f"📊 이동평균선 비교\n단기: {short_ma:.2f} > 장기: {long_ma:.2f}"
            )
        elif crossed_down:
            signal = (
                "🔴 *데드크로스 발생!* 하락 전환 가능성이 있습니다.\n"
                "📉 단기 평균선이 장기 평균선을 하향 돌파했어요.\n"
                "💡 *매도 시그널입니다.*\n"
                f"📊 이동평균선 비교\n단기: {short_ma:.2f} < 장기: {long_ma:.2f}"
            )

    return signal, short_ma, long_ma