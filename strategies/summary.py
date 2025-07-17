from datetime import datetime, timedelta
from statistics import mean
from config import MOVING_AVERAGE_PERIOD

def classify_volatility(high: float, low: float) -> str:
    """변동폭에 따른 간단한 변동성 평가"""
    width = high - low
    if width < 1:
        return f"{width:.2f}원 (매우 좁은 변동성)"
    elif width < 2:
        return f"{width:.2f}원 (보통 수준의 변동성)"
    else:
        return f"{width:.2f}원 (상대적으로 넓은 변동성)"
    

async def get_recent_major_events(conn, current_time) -> list[str]:
    """
    breakout_events 테이블 기반 최근 30분 주요 이벤트 요약
    - 상단 돌파 / 하단 이탈 발생 시간과 기준선 정보 표시
    """
    cutoff_time = current_time - timedelta(minutes=30)
    query = """
        SELECT event_type, timestamp, threshold
        FROM breakout_events
        WHERE timestamp >= %s
        ORDER BY timestamp ASC
    """
    rows = await conn.fetch(query, cutoff_time)

    events = []
    for row in rows:
        etype = row["event_type"]
        ts = row["timestamp"].astimezone()  # KST 변환은 필요 시 utils 활용
        hhmm = ts.strftime("%H:%M")
        if etype == "upper_breakout":
            events.append(f"{hhmm} 볼린저 상단 돌파 (기준선 {row['threshold']:.2f})")
        elif etype == "lower_breakout":
            events.append(f"{hhmm} 볼린저 하단 이탈 (기준선 {row['threshold']:.2f})")
    return events


def generate_30min_summary(
    start_time: datetime,
    end_time: datetime,
    rates: list[tuple[datetime, float]],
    major_events: list[str] = None
) -> str:
    """
    30분 간 환율 요약 메시지 생성
    :param start_time: 30분 시작 시각
    :param end_time: 30분 종료 시각
    :param rates: [(timestamp, rate), ...]
    :param major_events: 주요 이벤트 리스트 (문자열)
    """
    if not rates:
        return "⏱️ 최근 30분 데이터가 없습니다."

    sorted_rates = sorted(rates, key=lambda x: x[0])
    start_rate = sorted_rates[0][1]
    end_rate = sorted_rates[-1][1]
    high = max(r[1] for r in sorted_rates)
    low = min(r[1] for r in sorted_rates)
    diff = round(end_rate - start_rate, 2)

    # 추세 분류
    if diff > 0.05:
        trend = "상승"
    elif diff < -0.05:
        trend = "하락"
    else:
        trend = "횡보"

    volatility = classify_volatility(high, low)

    # 주요 이벤트 요약
    events_text = "\n".join([f"- {e}" for e in major_events]) if major_events else "해당 없음"

    # 간단한 해석 (임시 규칙)
    if trend == "상승" and diff > 0.5:
        advice = "상승세 지속 → 소량 매수 가능"
    elif trend == "하락" and abs(diff) > 0.5:
        advice = "단기 하락세 → 관망 권장"
    else:
        advice = "추세 혼조 → 관망 우선"

    return (
        f"⏱️ *최근 30분 환율 요약 ({start_time.strftime('%H:%M')} ~ {end_time.strftime('%H:%M')})*\n\n"
        f"📈 *추세*: {trend}\n"
        f"- 30분 전: {start_rate:.2f} → 현재: {end_rate:.2f}원 ({'+' if diff > 0 else ''}{diff:.2f}원)\n\n"
        f"📊 *변동폭*: 최고 {high:.2f} / 최저 {low:.2f}\n"
        f"- 변동 폭: {volatility}\n\n"
        f"📌 *주요 이벤트*\n"
        f"{events_text}\n\n"
        f"💡 *종합 해석*: {advice}"
    )