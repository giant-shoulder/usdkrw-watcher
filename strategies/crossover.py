from statistics import mean
from config import SHORT_TERM_PERIOD, LONG_TERM_PERIOD

def analyze_crossover(
    rates, prev_short_avg, prev_long_avg,
    prev_signal_type=None, prev_price=None, current_price=None
):
    """
    골든/데드크로스 감지 및 메시지 생성 (리팩토링)

    - 골든/데드크로스 발생 시 전환 메시지 출력
    - 골든/데드 상태 유지 시:
      - 이전 상태와 달라졌거나
      - 가격 변화가 일정 이상이거나
      - 평균선 간 간격이 변화했을 때만 메시지 출력
    - 메시지에 현재 환율과 전일 대비 변동폭 포함
    """
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_short_avg, prev_long_avg, prev_signal_type

    short_ma = mean(rates[-SHORT_TERM_PERIOD:])
    long_ma = mean(rates[-LONG_TERM_PERIOD:])
    EPSILON = 0.005
    PRICE_GAP_THRESHOLD = 0.5
    SPREAD_DIFF_THRESHOLD = 0.03

    signal = None
    crossed_up = crossed_down = False

    if prev_short_avg is not None and prev_long_avg is not None:
        crossed_up = short_ma > long_ma and prev_short_avg <= prev_long_avg
        crossed_down = short_ma < long_ma and prev_short_avg >= prev_long_avg

    # 평균선 관계 표현
    if abs(short_ma - long_ma) <= EPSILON:
        relation = "="
    elif short_ma > long_ma:
        relation = ">"
    else:
        relation = "<"

    spread_now = short_ma - long_ma

    # 환율 변화 계산
    rate_change_info = ""
    if current_price and prev_price:
        diff = round(current_price - prev_price, 2)
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "→"
        rate_change_info = f"\n💱 현재 환율: {current_price:.2f}원 ({arrow} {abs(diff):.2f}원)"

    if crossed_up:
        signal_type = "golden"
        signal = (
            "🟢 *골든크로스 발생!* 장기 상승 전환 신호입니다.\n"
            "📈 단기 평균선이 장기 평균선을 상향 돌파했어요.\n"
            "💡 *매수 시그널입니다.*"
        )
    elif crossed_down:
        signal_type = "dead"
        signal = (
            "🔴 *데드크로스 발생!* 하락 전환 가능성이 있습니다.\n"
            "📉 단기 평균선이 장기 평균선을 하향 돌파했어요.\n"
            "💡 *매도 시그널입니다.*"
        )
    else:
        if short_ma > long_ma:
            signal_type = "golden"
        elif short_ma < long_ma:
            signal_type = "dead"
        else:
            signal_type = None

        if signal_type:
            should_report = (
                prev_signal_type != signal_type or
                (prev_price and current_price and abs(current_price - prev_price) >= PRICE_GAP_THRESHOLD) or
                (prev_short_avg is not None and prev_long_avg is not None and abs((prev_short_avg - prev_long_avg) - spread_now) >= SPREAD_DIFF_THRESHOLD)
            )
            if should_report:
                signal = (
                    f"{'🟢' if signal_type == 'golden' else '🔴'} *{signal_type.capitalize()} 상태 유지 중*\n"
                    f"{'📈' if signal_type == 'golden' else '📉'} 단기 평균선이 장기 평균선보다 {'높습니다' if signal_type == 'golden' else '낮습니다'}.\n"
                    f"💡 *{'상승' if signal_type == 'golden' else '약세'} 흐름 지속 가능성 있음.*"
                )

    if signal:
        signal += f"\n📊 이동평균선 비교\n단기: {short_ma:.2f} {relation} 장기: {long_ma:.2f}"
        signal += rate_change_info

    return signal, short_ma, long_ma, signal_type