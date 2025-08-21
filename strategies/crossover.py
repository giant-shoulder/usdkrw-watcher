from statistics import mean
from utils.time import now_kst
from strategies.utils.signal_utils import sma

from config import (
    SHORT_TERM_PERIOD, LONG_TERM_PERIOD,
    EPSILON, SPREAD_DIFF_THRESHOLD, PRICE_GAP_THRESHOLD,
    MIN_REPORT_INTERVAL, REMINDER_INTERVAL
)

# 🔧 강화 파라미터: 의미있는 스프레드/가격 거리 + 전환 확정 틱 수
SPREAD_MIN = 0.05       # 스프레드 최소 절대값 (단기-장기)
DIST_MIN = 0.05         # 현가격-장기MA 최소 거리
CONFIRM_BARS = 2        # 전환 직후 N틱 유지되면 확정

# 전환 확정 카운터 (일시적 스파이크 억제)
_confirm_counts = {"golden": 0, "dead": 0}

# ✅ 전역 변수 (상태별 마지막 보고 시각 기록)
last_report_time = {
    "golden": None,
    "dead": None
}

def analyze_crossover(
    rates, prev_short_avg, prev_long_avg,
    prev_signal_type=None, prev_price=None, current_price=None
):
    """
    골든/데드크로스 감지 및 메시지 생성 (운영용 최종 버전)
    - 전환 발생 시 즉시 메시지
    - 유지 상태는 의미 있는 변화 발생 시 15분 간격 발송
    - 변화 없으면 1시간마다 리마인드
    """
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_short_avg, prev_long_avg, prev_signal_type

    short_ma = mean(rates[-SHORT_TERM_PERIOD:])
    long_ma = mean(rates[-LONG_TERM_PERIOD:])
    spread_now = short_ma - long_ma
    now = now_kst()

    # 의미있는 전환 판정: 부호 변환 + 스프레드 크기 + 가격 조건
    spread_prev = None
    if prev_short_avg is not None and prev_long_avg is not None:
        spread_prev = (prev_short_avg - prev_long_avg)

    price_ok_g = (current_price is None) or (current_price >= long_ma + DIST_MIN)
    price_ok_d = (current_price is None) or (current_price <= long_ma - DIST_MIN)

    crossed_up_raw = (
        spread_prev is not None and spread_prev <= 0 and spread_now > 0
    )
    crossed_down_raw = (
        spread_prev is not None and spread_prev >= 0 and spread_now < 0
    )

    crossed_up = crossed_up_raw and (abs(spread_now) >= SPREAD_MIN) and price_ok_g
    crossed_down = crossed_down_raw and (abs(spread_now) >= SPREAD_MIN) and price_ok_d

    signal_type = None
    signal = None

    # ✅ 부등호 표시
    if abs(short_ma - long_ma) <= EPSILON:
        relation = "="
    elif short_ma > long_ma:
        relation = ">"
    else:
        relation = "<"

    # ✅ 환율 변화 요약
    rate_change_info = ""
    if current_price and prev_price:
        diff = round(current_price - prev_price, 2)
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "→"
        rate_change_info = f"\n💱 현재 환율: {current_price:.2f}원 ({arrow} {abs(diff):.2f}원)"

    # ✅ 전환 발생 시 즉시 발송
    if crossed_up:
        # 전환 확정: N틱 유지 시에만 알림
        _confirm_counts["golden"] += 1
        _confirm_counts["dead"] = 0
        if _confirm_counts["golden"] < CONFIRM_BARS:
            return None, short_ma, long_ma, "golden"

        signal_type = "golden"
        signal = (
            "🟡 *골든크로스 확정!* 장기 상승 전환 신호입니다.\n"
            "📈 단기 평균선이 장기 평균선을 상향 돌파했고 조건을 충족했습니다.\n"
            f"📎 스프레드: {spread_now:.2f}, 가격-장기MA: {(current_price - long_ma) if current_price else 0:+.2f}\n"
            "💡 *매수(상승) 시그널입니다.*"
        )
        last_report_time["golden"] = now

    elif crossed_down:
        # 전환 확정: N틱 유지 시에만 알림
        _confirm_counts["dead"] += 1
        _confirm_counts["golden"] = 0
        if _confirm_counts["dead"] < CONFIRM_BARS:
            return None, short_ma, long_ma, "dead"

        signal_type = "dead"
        signal = (
            "⚫️ *데드크로스 확정!* 하락 전환 가능성이 있습니다.\n"
            "📉 단기 평균선이 장기 평균선을 하향 돌파했고 조건을 충족했습니다.\n"
            f"📎 스프레드: {spread_now:.2f}, 가격-장기MA: {(current_price - long_ma) if current_price else 0:+.2f}\n"
            "💡 *매도(하락) 시그널입니다.*"
        )
        last_report_time["dead"] = now

    else:
        # ✅ 유지 상태 처리
        if short_ma > long_ma:
            signal_type = "golden"
        elif short_ma < long_ma:
            signal_type = "dead"

        if signal_type == "golden":
            _confirm_counts["dead"] = 0
        elif signal_type == "dead":
            _confirm_counts["golden"] = 0

        if signal_type:
            last_time = last_report_time.get(signal_type)
            elapsed = (now - last_time).total_seconds() if last_time else None

            prev_spread = prev_short_avg - prev_long_avg if (prev_short_avg and prev_long_avg) else 0
            spread_diff = spread_now - prev_spread if prev_spread else 0
            price_diff = current_price - prev_price if (prev_price and current_price) else 0

            # ✅ 상태 전환 태그
            if prev_signal_type != signal_type:
                tag = "🔄 상태 전환"
                explain = f"{'상승' if signal_type == 'golden' else '하락'} 상태로 전환되었습니다."
                last_report_time[signal_type] = now

            # ✅ 의미 있는 변화 발생 시 (15분 간격)
            elif elapsed is None or elapsed >= MIN_REPORT_INTERVAL:
                if abs(spread_diff) >= SPREAD_DIFF_THRESHOLD or abs(price_diff) >= PRICE_GAP_THRESHOLD:
                    if spread_diff > 0 or (
                        signal_type == "golden" and price_diff > 0
                    ) or (
                        signal_type == "dead" and price_diff < 0
                    ):
                        tag = "⏫ 추세 강화 신호"
                        explain = f"{'상승' if signal_type == 'golden' else '하락'} 흐름이 더 강해지고 있습니다."
                    elif abs(spread_diff) >= 0.15:
                        tag = "⏬ 추세 약화 조짐"
                        explain = f"{'상승' if signal_type == 'golden' else '하락'} 흐름이 약해지고 있습니다."
                    else:
                        return None, short_ma, long_ma, signal_type
                    last_report_time[signal_type] = now

                # ✅ 리마인드 (1시간마다 1회)
                elif elapsed >= REMINDER_INTERVAL:
                    tag = "ℹ️ 상태 지속 리마인드"

                    if signal_type == "golden":
                        if price_diff < 0:
                            explain = "중기 상승 추세는 유지되지만 단기적으로 조정(하락) 중입니다."
                        else:
                            explain = "상승 상태가 유지되고 있습니다."
                    else:  # dead 상태
                        if price_diff > 0:
                            explain = "중기 하락 추세는 유지되지만 단기적으로 반등 중입니다."
                        else:
                            explain = "하락 상태가 유지되고 있습니다."

                    last_report_time[signal_type] = now

                else:
                    return None, short_ma, long_ma, signal_type
            else:
                return None, short_ma, long_ma, signal_type

            signal = (
                f"{'🟡' if signal_type == 'golden' else '⚫️'} *{signal_type.capitalize()} 상태 유지 중*\n"
                f"{tag}\n"
                f"{'📈' if signal_type == 'golden' else '📉'} 단기 평균선이 장기 평균선보다 {'높습니다' if signal_type == 'golden' else '낮습니다'}.\n"
                f"💡 {explain}"
            )

    if signal:
        signal += f"\n📊 이동평균선 비교\n단기: {short_ma:.2f} {relation} 장기: {long_ma:.2f}"
        signal += rate_change_info

    return signal, short_ma, long_ma, signal_type