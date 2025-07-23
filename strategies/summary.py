from datetime import datetime, timedelta
from statistics import mean
from config import MOVING_AVERAGE_PERIOD
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm


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
        WHERE timestamp >= $1
        ORDER BY timestamp ASC
    """
    rows = await conn.fetch(query, cutoff_time)

    events = []
    for row in rows:
        etype = row["event_type"]
        ts = row["timestamp"].astimezone()
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
    30분 간 환율 요약 메시지 생성 (혼조/횡보 세분화 버전)
    """
    if not rates:
        return "⏱️ 최근 30분 데이터가 없습니다."

    sorted_rates = sorted(rates, key=lambda x: x[0])
    start_rate = sorted_rates[0][1]
    end_rate = sorted_rates[-1][1]
    high = max(r[1] for r in sorted_rates)
    low = min(r[1] for r in sorted_rates)
    diff = round(end_rate - start_rate, 2)
    volatility = classify_volatility(high, low)

    high_diff = round(high - end_rate, 2)
    low_diff = round(end_rate - low, 2)
    band_width = round(high - low, 2)

    # ✅ 세분화된 추세 분류
    if band_width <= 0.2:
        trend = "횡보"
    elif diff > 0.05 and high > start_rate and low >= start_rate - 0.05:
        trend = "상승"
    elif diff < -0.05 and low < start_rate and high <= start_rate + 0.05:
        trend = "하락"
    elif abs(diff) < 0.1 and high_diff > 0.2:
        trend = "급등 후 조정"
    elif abs(diff) < 0.1 and low_diff > 0.2:
        trend = "급락 후 반등"
    else:
        trend = "혼조"

    # ✅ 주요 이벤트 요약
    events_text = "\n".join([f"- {e}" for e in major_events]) if major_events else "해당 없음"

    # ✅ 종합 해석
    if trend == "상승":
        advice = "상승 흐름 유지 → 관망 후 소량 매수 고려"
    elif trend == "하락":
        advice = "하락 흐름 유지 → 관망 권장"
    elif trend == "급등 후 조정":
        advice = "급등 이후 되돌림 진행 중 → 추세 전환 가능성 주의"
    elif trend == "급락 후 반등":
        advice = "급락 이후 단기 반등 → 추세 지속 여부 확인 필요"
    elif trend == "혼조":
        advice = "단기 등락 반복 → 관망 우선"
    else:  # 횡보
        advice = "변동성 낮음 → 관망 유지"

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

def generate_30min_chart(rates: list[tuple[datetime, float]]) -> BytesIO:
    """
    30분간 환율 추이 그래프 생성 (영문 only)
    - 상승=빨강, 하락=파랑, 횡보=회색
    - 첫 환율, 마지막 환율만 강조 표시
    """
    if not rates:
        return None

    times = [r[0].strftime("%H:%M") for r in rates]
    values = [r[1] for r in rates]

    # ✅ 추세 색상
    if values[-1] > values[0]:
        color = "red"
    elif values[-1] < values[0]:
        color = "blue"
    else:
        color = "gray"

    plt.figure(figsize=(6, 3))
    plt.plot(times, values, marker="o", linewidth=2, color=color)
    plt.xticks(rotation=45)
    plt.title("USD/KRW Last 30 min")
    plt.xlabel("Time")
    plt.ylabel("KRW")
    plt.grid(True)

    # ✅ 첫 환율(시작점) 강조
    plt.scatter(times[0], values[0], color=color, s=60, edgecolors="black", zorder=5)
    plt.text(
        times[0],
        values[0],
        f"{values[0]:.2f}",
        fontsize=8,
        color="black",
        ha="right",
        va="bottom",
        bbox=dict(facecolor="white", edgecolor="gray", boxstyle="round,pad=0.2")
    )

    # ✅ 마지막 환율(현재가) 강조
    plt.scatter(times[-1], values[-1], color=color, s=80, edgecolors="black", zorder=5)
    plt.text(
        times[-1],
        values[-1],
        f"{values[-1]:.2f}",
        fontsize=9,
        color="black",
        ha="left",
        va="bottom",
        bbox=dict(facecolor="white", edgecolor="gray", boxstyle="round,pad=0.2")
    )

    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf